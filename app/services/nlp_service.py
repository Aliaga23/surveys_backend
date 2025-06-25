# app/services/nlp_service.py
from __future__ import annotations
import os, uuid, json, re, functools, itertools
from datetime import datetime
from collections import Counter, defaultdict, OrderedDict
from typing import List, Dict, Any, Optional

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from fastapi import HTTPException
from openai import OpenAI
from pysentimiento import create_analyzer
from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.decomposition import NMF
from sklearn.cluster import MiniBatchKMeans          # ➜ más estable con muchos textos

from app.models.survey import (
    CampanaEncuesta, EntregaEncuesta, RespuestaEncuesta,
    RespuestaPregunta, PreguntaEncuesta, OpcionEncuesta
)
from app.schemas.nlp_schema import NLPAnalysisRequest, NLPAnalysisResponse

# ─────────────────── Recursos globales ────────────────────
client       = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
sentiment_es = create_analyzer(task="sentiment", lang="es")

STOP_ES = {
    "si","no","tal","vez","quizás","gracias","ok","bueno","buenos",
    "bien","hola","buenas","nos","usted","ustedes","muy","solo","sólo"
}
DEMOGRAPHIC_HINTS = {
    "edad","años","género","genero","sexo","ciudad","región","region",
    "departamento","pais","país","provincia"
}
SCALE_5_TO_NPS = {5: "promotor", 4: "promotor", 3: "pasivo", 2: "detractor", 1: "detractor"}

# ═══════════════════════════════════════════════════════════
#                          HELPERS
# ═══════════════════════════════════════════════════════════
class _Utils:

    # --------------- KPIs ---------------
    @staticmethod
    def nps_weighted(nums: list[int], cats: list[str]) -> Optional[float]:
        """
        Conversión clásica:
        • 9-10 (o “promotor”) = +1
        • 7-8 (o “pasivo”)   = 0
        • 0-6 (o “detractor”) = -1
        """
        if not nums and not cats:
            return None
        score_num = sum(+1 if v >= 9 else -1 if v <= 6 else 0 for v in nums)
        weight    = {"promotor": 1, "detractor": -1, "pasivo": 0}
        score_txt = sum(weight[c] for c in cats)
        total     = len(nums) + len(cats)
        return round((score_num + score_txt) / total * 100, 1)

    @staticmethod
    def csat(nums: list[int]) -> Optional[float]:
        """% de respuestas 4-5 en escala 1-5 ó 8-10 en escala 1-10"""
        if not nums:
            return None
        nums_arr = np.array(nums)
        if nums_arr.max() <= 5:   # escala corta
            good = nums_arr >= 4
        else:
            good = nums_arr >= 8
        return round(good.mean() * 100, 1)

    # --------------- Series temporales ---------------
    @staticmethod
    def week_trend(df: pd.DataFrame, col: str, win: int = 4):
        """Media móvil semanal `win` semanas."""
        if df.empty:
            return []
        ts = (
            df.set_index("fecha")[col]
              .resample("W")
              .mean()
              .rolling(win)
              .mean()
              .dropna()
        )
        return ts.reset_index().to_dict("records")

    # --------------- LLM helpers ---------------
    @staticmethod
    def _chat(model: str, prompt: str) -> str:
        return (
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                timeout=20,
            )
            .choices[0]
            .message
            .content
            .strip()
        )

    @classmethod
    def recommendations(cls, resume: str) -> str:
        prompt = (
            "Eres consultor de customer experience.\n\n"
            f"Resumen analítico:\n{resume}\n\n"
            "Devuelve EXACTAMENTE 5 acciones SMART (específicas, medibles, alcanzables, "
            "relevantes y acotadas en el tiempo) que la empresa debe realizar para mejorar. "
            "Usa un lenguaje sencillo, directo y empático. "
            "Respuesta en lista numerada.\n"
        )
        return cls._chat("gpt-4o", prompt)

    # --------------- Clasificación de preguntas ---------------
    @classmethod
    @functools.lru_cache(maxsize=256)
    def classify_question(cls, texto: str) -> str:
        """Clasifica ajustado localmente para evitar coste alto de llamadas."""
        txt = texto.lower()
        if any(h in txt for h in DEMOGRAPHIC_HINTS):
            return "demografica"
        if re.search(r"recom(endar|endarías|endarías)|nps|volverías", txt):
            return "recomendacion"
        if re.search(r"satisf[aá]cci[oó]n|agrado|content[ao]", txt):
            return "satisfaccion"
        if re.search(r"mejorar|cambiar|suger", txt):
            return "mejoras"
        if re.search(r"^.*(escala|califica|calificalo).*", txt):
            return "escala"
        return "libre"


# ═══════════════════════════════════════════════════════════
#                        NLP SERVICE
# ═══════════════════════════════════════════════════════════
class NLPAnalysisService:

    # --------- singleton vectorizadores para rendimiento ---------
    _tfidf_vect = TfidfVectorizer(
        max_df=0.9,
        min_df=2,
        stop_words=list(STOP_ES),
        ngram_range=(1, 2)
    )
    _cnt_vect = CountVectorizer(
        max_df=0.9,
        min_df=2,
        stop_words=list(STOP_ES),
        ngram_range=(1, 2)
    )

    def __init__(self, db: Session):
        self.db = db
        self.ut = _Utils()

    # ────────────────────────────────────────────────────────────
    #                    1. QUERY SQL A MEDIDA
    # ────────────────────────────────────────────────────────────
    def _fetch_rows(
        self,
        suscriptor_id: uuid.UUID,
        start: Optional[datetime],
        end: Optional[datetime],
        campana_id: Optional[uuid.UUID],
    ):
        """Devuelve un listado ampliado con preguntas y opciones."""
        q = (
            self.db.query(
                RespuestaPregunta,
                PreguntaEncuesta.tipo_pregunta_id,
                PreguntaEncuesta.texto.label("pregunta_txt"),
                PreguntaEncuesta.id.label("pregunta_id"),
                OpcionEncuesta.texto.label("opcion_txt"),
                RespuestaEncuesta.recibido_en,
                CampanaEncuesta.id.label("campana_id"),
                CampanaEncuesta.nombre.label("campana_nombre"),
                CampanaEncuesta.canal_id.label("campana_canal"),
            )
            .join(RespuestaEncuesta, RespuestaPregunta.respuesta_id == RespuestaEncuesta.id)
            .join(EntregaEncuesta, RespuestaEncuesta.entrega_id == EntregaEncuesta.id)
            .join(CampanaEncuesta, EntregaEncuesta.campana_id == CampanaEncuesta.id)
            .join(PreguntaEncuesta, RespuestaPregunta.pregunta_id == PreguntaEncuesta.id)
            .outerjoin(OpcionEncuesta, RespuestaPregunta.opcion_id == OpcionEncuesta.id)
            .filter(CampanaEncuesta.suscriptor_id == suscriptor_id)
        )

        if start:
            q = q.filter(RespuestaEncuesta.recibido_en >= start)
        if end:
            q = q.filter(RespuestaEncuesta.recibido_en <= end)
        if campana_id:
            q = q.filter(CampanaEncuesta.id == campana_id)

        return q.all()

    # ────────────────────────────────────────────────────────────
    #                2. FUNCIONES DE CÁLCULO BÁSICO
    # ────────────────────────────────────────────────────────────
    @staticmethod
    def _sentiment_stats(texts: List[str]) -> Dict[str, Any]:
        cats, scores = Counter(), []
        for t in texts:
            r = sentiment_es.predict(t)
            cats[r.output] += 1
            scores.append(r.probas[r.output])
        total = sum(cats.values()) or 1
        return {
            "promedio": round(float(np.mean(scores)) if scores else 0, 3),
            "positivo": cats["POS"],
            "neutro": cats["NEU"],
            "negativo": cats["NEG"],
            "distribucion": {
                k.lower(): round(v / total * 100, 2) for k, v in cats.items()
            },
        }

    @staticmethod
    def _txt_to_nps_cat(text: str, ctx: str, pos_th: float = 0.4, neg_th: float = 0.4) -> str:
        """Heurística ligera → evita costo de LLM en inferencia."""
        BAD = {
            "regular", "meh", "más o menos", "mas o menos", "nada",
            "podría mejorar", "podria mejorar", "flojo", "insuficiente",
            "decepcionado", "decepcionante"
        }
        if ctx == "demografica":
            return "pasivo"

        txt = text.lower()
        if any(b in txt for b in BAD):
            return "detractor"

        r = sentiment_es.predict(text)
        pos, neg = r.probas["POS"], r.probas["NEG"]

        if ctx == "mejoras":
            return "detractor"
        if ctx in {"satisfaccion", "recomendacion", "escala"}:
            if pos >= pos_th:
                return "promotor"
            if neg >= neg_th:
                return "detractor"
            return "pasivo"

        # libre
        if pos - neg >= 0.25:
            return "promotor"
        if neg - pos >= 0.15:
            return "detractor"
        return "pasivo"

    # ---------------------- Palabras clave ----------------------
    def _keywords(self, texts: List[str], top: int = 20) -> Dict[str, Any]:
        if not texts:
            return {"keywords": []}
        try:
            tfidf = self._tfidf_vect.fit_transform(texts)
        except ValueError:          # poco texto
            tfidf = self._tfidf_vect.fit_transform(texts, )
        feats = self._tfidf_vect.get_feature_names_out()
        sums = np.asarray(tfidf.sum(axis=0)).ravel()
        idx = sums.argsort()[-top:][::-1]
        return {
            "keywords": [
                {"palabra": feats[i], "valor": float(sums[i])} for i in idx
            ]
        }

    # ---------------------- Tópicos NMF ------------------------
    def _topics(self, texts: List[str], n: int):
        if len(texts) < n * 2:
            return []
        dtm = self._cnt_vect.fit_transform(texts)
        try:
            nmf = NMF(n_components=n, random_state=42).fit(dtm)
        except Exception:
            n = 1
            nmf = NMF(n_components=1, random_state=42).fit(dtm)
        feats = self._cnt_vect.get_feature_names_out()
        topics = []
        for i, comp in enumerate(nmf.components_):
            idx = comp.argsort()[-10:][::-1]
            topics.append(
                {
                    "id": i,
                    "peso": float(comp.sum()),
                    "palabras_clave": [
                        {"palabra": feats[j], "peso": float(comp[j])} for j in idx
                    ],
                }
            )
        return topics

    # ---------------------- Clusters ---------------------------
    def _clusters(self, texts: List[str], k_req: int):
        if len(texts) < 4:
            return {"clusters": [], "total_clusters": 0}
        tfidf = self._tfidf_vect.fit_transform(texts)
        # buscamos el mejor k desde k_req hacia abajo
        for k in range(min(k_req, len(texts) // 2), 1, -1):
            try:
                labels = MiniBatchKMeans(
                    n_clusters=k, random_state=42, batch_size=32
                ).fit_predict(tfidf)
                break
            except Exception:
                continue
        else:
            return {"clusters": [], "total_clusters": 0}

        buckets = defaultdict(list)
        for t, l in zip(texts, labels):
            buckets[int(l)].append(t)

        clusters = []
        for lab, lst in buckets.items():
            word_cnt = Counter(" ".join(lst).split())
            top_words = word_cnt.most_common(7)
            clusters.append(
                {
                    "id": lab,
                    "tamaño": len(lst),
                    "keywords": [{"palabra": w, "valor": v} for w, v in top_words],
                    "muestras": lst[:3],
                }
            )
        return {"clusters": clusters, "total_clusters": len(clusters)}

    # ────────────────────────────────────────────────────────────
    #              3. ANÁLISIS DETALLADO POR PREGUNTA
    # ────────────────────────────────────────────────────────────
    def _analisis_pregunta(
        self,
        rows: List[Any],
        pid: str,
        ctx: str,
        p_dict: Dict[str, PreguntaEncuesta],
        pos_th: float,
        neg_th: float,
    ):
        sub = [r for r in rows if str(r.pregunta_id) == pid]
        p_obj = p_dict.get(pid)
        tipo = p_obj.tipo_pregunta_id if p_obj else (sub[0].tipo_pregunta_id if sub else None)

        res = OrderedDict(
            pregunta_id=pid,
            pregunta_texto=p_obj.texto if p_obj else "",
            total_respuestas=len(sub),
            tipo_pregunta=tipo,
            contexto=ctx,
        )

        # ► Texto libre
        if tipo == 1 and sub:
            txts = [r.RespuestaPregunta.texto for r in sub if r.RespuestaPregunta.texto]
            res["sentiment"] = self._sentiment_stats(txts)
            res["keywords"]  = self._keywords(txts)
            if len(txts) >= 6:
                res["topics"] = self._topics(txts, min(3, len(txts) // 2))

        # ► Numérica
        elif tipo == 2 and sub:
            nums = [
                float(r.RespuestaPregunta.numero)
                for r in sub
                if r.RespuestaPregunta.numero is not None
            ]
            if nums:
                res["estadisticas"] = {
                    "promedio": round(np.mean(nums), 2),
                    "mediana": round(np.median(nums), 2),
                    "min": min(nums),
                    "max": max(nums),
                    "desviacion": round(np.std(nums), 2),
                }

        # ► Selección única / múltiple
        elif tipo in {3, 4}:
            total_opts = [o.texto for o in p_obj.opciones] if p_obj else []
            if not total_opts:
                total_opts = [
                    o.texto
                    for (o,) in self.db.query(OpcionEncuesta.texto)
                    .filter(OpcionEncuesta.pregunta_id == uuid.UUID(pid))
                    .all()
                ]
            cnt = Counter(r.opcion_txt for r in sub if r.opcion_txt)
            tot = sum(cnt.values()) or 1
            res["opciones"] = {
                "conteo": {opt: cnt.get(opt, 0) for opt in total_opts},
                "porcentajes": {opt: round(cnt.get(opt, 0) / tot * 100, 1) for opt in total_opts},
                "opciones_totales": total_opts,
            }
        return res

    # ────────────────────────────────────────────────────────────
    #                      4. ENDPOINT PÚBLICO
    # ────────────────────────────────────────────────────────────
    async def analyze_responses(
        self,
        suscriptor_id: uuid.UUID,
        params: NLPAnalysisRequest,
    ) -> NLPAnalysisResponse:
        """Devuelve un JSON listo para API."""

        rows = self._fetch_rows(
            suscriptor_id, params.fecha_inicio, params.fecha_fin, params.campana_id
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Sin respuestas")

        # ---------- Parámetros dinámicos ----------
        pos_th      = getattr(params, "umbral_sent_pos", 0.40)
        neg_th      = getattr(params, "umbral_sent_neg", 0.40)
        escala_corta = getattr(params, "escala_corta", False)

        # ---------- Preguntas ----------
        p_objs = (
            self.db.query(PreguntaEncuesta)
            .filter(PreguntaEncuesta.id.in_({r.pregunta_id for r in rows}))
            .all()
        )
        p_dict = {str(p.id): p for p in p_objs}
        ctx_map = {str(p.id): _Utils.classify_question(p.texto) for p in p_objs}

        # ---------- Recorrido por filas ----------
        texts, nums, cats = [], [], []
        for r in rows:
            ctx = ctx_map.get(str(r.pregunta_id), "libre")

            # texto libre
            if r.RespuestaPregunta.texto:
                texts.append(r.RespuestaPregunta.texto)
                cats.append(self._txt_to_nps_cat(r.RespuestaPregunta.texto, ctx, pos_th, neg_th))

            # opción elegida ➜ también texto
            elif r.opcion_txt:
                cats.append(self._txt_to_nps_cat(r.opcion_txt, ctx, pos_th, neg_th))
                texts.append(r.opcion_txt)

            # numérico
            if r.tipo_pregunta_id == 2 and r.RespuestaPregunta.numero is not None:
                val = int(r.RespuestaPregunta.numero)
                if escala_corta and 1 <= val <= 5:
                    cats.append(SCALE_5_TO_NPS[val])
                else:
                    nums.append(val)

        # ---------- KPI GLOBAL ----------
        sentiment_global = self._sentiment_stats(texts)
        sentiment_global["kpis"] = {
            "nps":  self.ut.nps_weighted(nums, cats),
            "csat": self.ut.csat(nums),
        }
        sentiment_global["trend"] = self.ut.week_trend(
            pd.DataFrame(
                [
                    (r.recibido_en, int(r.RespuestaPregunta.numero))
                    for r in rows
                    if r.tipo_pregunta_id == 2
                    and r.RespuestaPregunta.numero is not None
                    and r.recibido_en
                ],
                columns=["fecha", "nps"],
            ),
            "nps",
        ) if nums else []

        # ---------- Insights de texto ----------
        topics   = self._topics(texts, max(1, min(3, params.num_topics)))
        clusters = self._clusters(texts, max(2, params.num_clusters))
        neg_kw   = [
            kw["palabra"] for kw in self._keywords(texts, top=25)["keywords"][:10]
            if kw["palabra"] not in STOP_ES
        ]

        # ---------- Recomendaciones (LLM) ----------
        resumen_llm = (
            f"NPS={sentiment_global['kpis']['nps']}; "
            f"CSAT={sentiment_global['kpis']['csat']}; "
            f"Top palabras negativas={', '.join(neg_kw)}; "
            f"Detractores={cats.count('detractor')}"
        )
        recs = self.ut.recommendations(resumen_llm)

        # ---------- Campañas resumen ----------
        campanas = [
            {
                "id": cid,
                "nombre": next(n for n in {x.campana_nombre for x in rows if str(x.campana_id) == cid}),
                "total_respuestas": tot,
            }
            for cid, tot in Counter(str(r.campana_id) for r in rows).items()
        ]

        # ---------- Análisis por pregunta ----------
        analisis_pregunta = [
            self._analisis_pregunta(rows, pid, ctx_map.get(pid, "libre"), p_dict, pos_th, neg_th)
            for pid in p_dict
        ]

        # ---------- Segmentación por canal ----------
        canales_cnt = Counter(r.campana_canal for r in rows)
        canales = {c: canales_cnt[c] for c in sorted(canales_cnt)}

        return {
            "suscriptor_id": str(suscriptor_id),
            "fecha_analisis": datetime.utcnow(),
            "periodo": {"inicio": params.fecha_inicio, "fin": params.fecha_fin},
            "total_respuestas": len(rows),
            "total_respuestas_texto": len(texts),
            "sentiment_global": sentiment_global,
            "topics": topics,
            "clusters": clusters,
            "analisis_por_pregunta": analisis_pregunta,
            "campanas": campanas,
            "canales": canales,
            "recommendations": recs,
        }


# ────────────────────────── Factory de dependencia ───────────────────────
def get_nlp_service(db: Session) -> NLPAnalysisService:
    """Dependency injection para FastAPI."""
    return NLPAnalysisService(db)
