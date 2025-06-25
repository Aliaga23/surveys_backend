# app/services/dashboard_service.py
from __future__ import annotations

import json
from decimal import Decimal
from typing import Dict, List
from uuid import UUID

from fastapi import HTTPException, status
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, Extra
from sqlalchemy.orm import Session

from app.services.campanas_service import get_campana_full_detail


# ──────────────────────────   DTOs ricos   ─────────────────────────── #

class ExecutiveSummary(BaseModel):
    texto: str                                 # 2-3 párrafos

class TemaClave(BaseModel):
    tema: str                                  # “Servicio al cliente”, “Precio”, …
    categoria: str                             # fortaleza | debilidad | oportunidad | amenaza
    sentimiento: float                         # −100 → 100
    evidencia: List[str]                       # citas textuales resumidas

class AccionPrioritaria(BaseModel):
    accion: str
    impacto: str                               # alto | medio | bajo
    dificultad: str                            # baja | media | alta

class QuestionFeedback(BaseModel):
    fortalezas: List[str] = []
    debilidades: List[str] = []
    recomendaciones: List[str] = []

class QuestionMetrics(BaseModel, extra=Extra.allow):
    question_id: str
    chart_type: str
    data: Dict
    feedback: QuestionFeedback

class CampaignAnalysis(BaseModel):
    executive_summary: ExecutiveSummary
    temas_clave: List[TemaClave]
    acciones_prioritarias: List[AccionPrioritaria]
    questions: List[QuestionMetrics]


# ────────────────────────  Servicio principal  ──────────────────────── #

class DashboardService:
    """
    Analiza encuestas de cualquier temática y genera insights
    sustanciales más métricas por pregunta.
    """

    def __init__(self, openai_key: str) -> None:
        self.client = AsyncOpenAI(api_key=openai_key)

    # ------------- utilidades ------------- #
    @staticmethod
    def _to_float(val):
        if val is None or isinstance(val, float):
            return val
        if isinstance(val, Decimal):
            return float(val)
        return val

    @staticmethod
    def _build_prompt(campaign_data: Dict) -> str:
        """
        Prompt que instruye a GPT para crear un insight empresarial:
        summary, temas clave (SWOT), acciones y métricas por pregunta.
        """
        example = {
            "executive_summary": {
                "texto": (
                    "En general, la percepción sobre la nueva plataforma "
                    "es positiva (68 % de comentarios favorables). Los "
                    "usuarios destacan la facilidad de uso, aunque exigen "
                    "mejoras en tiempos de entrega."
                )
            },
            "temas_clave": [
                {
                    "tema": "Facilidad de uso",
                    "categoria": "fortaleza",
                    "sentimiento": 82.0,
                    "evidencia": ["“La app es muy intuitiva”", "“Encontré todo rápido”"]
                },
                {
                    "tema": "Tiempo de entrega",
                    "categoria": "debilidad",
                    "sentimiento": -56.5,
                    "evidencia": ["“Tardó más de una semana”"]
                }
            ],
            "acciones_prioritarias": [
                {"accion": "Optimizar logística de envíos", "impacto": "alto", "dificultad": "media"},
                {"accion": "Mantener simplicidad de la app", "impacto": "medio", "dificultad": "baja"}
            ],
            "questions": [
                {
                    "question_id": "uuid-1",
                    "chart_type": "bar",
                    "data": {"Sí": 72.3, "No": 27.7},
                    "feedback": {
                        "fortalezas": ["Alta aceptación general"],
                        "debilidades": ["Segmento 55+ menos entusiasta"],
                        "recomendaciones": ["Añadir tutorial para mayores"]
                    }
                }
            ]
        }

        return (
            "Eres un consultor senior de investigación de mercados.\n\n"
            "Con el JSON de resultados que aparece al final, genera un "
            "informe JSON **sin comentarios** que siga ESTA plantilla:\n\n"
            f"{json.dumps(example, ensure_ascii=False, indent=2)}\n\n"
            "Reglas:\n"
            "1. `executive_summary.texto` debe tener 2-3 párrafos.\n"
            "2. Identifica de 3 a 7 `temas_clave` y clasifícalos como "
            "fortaleza, debilidad, oportunidad o amenaza.\n"
            "3. Propón 3-5 `acciones_prioritarias` con impacto y dificultad.\n"
            "4. En `questions` elige el chart_type más adecuado "
            "(pie, bar, histogram, stat_summary…).\n"
            "5. Devuelve SOLO el objeto JSON.\n\n"
            "Datos de la campaña:\n"
            f"{json.dumps(campaign_data, ensure_ascii=False)}"
        )

    async def _call_gpt(self, campaign_data: Dict) -> Dict:
        prompt = self._build_prompt(campaign_data)
        try:
            chat = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"},
                max_tokens=1400,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Error llamando a OpenAI: {exc}",
            ) from exc

        try:
            return json.loads(chat.choices[0].message.content)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"JSON inválido de GPT: {exc}",
            ) from exc

    # ------------- API pública ------------- #
    async def get_campaign_analysis(
        self, db: Session, campaign_id: UUID
    ) -> Dict[str, CampaignAnalysis]:
        campana = get_campana_full_detail(db, campaign_id)
        if not campana:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Campaña no encontrada",
            )

        # --- Serializa campaña --- #
        camp_dict: Dict = {
            "id": str(campana.id),
            "nombre": campana.nombre,
            "total_entregas": campana.total_entregas,
            "total_respondidas": campana.total_respondidas,
            "preguntas": [],
        }

        if campana.plantilla:
            for preg in campana.plantilla.preguntas:
                resp_list: List[Dict] = []
                for ent in campana.entregas:
                    for resp_enc in ent.respuestas:
                        for resp_preg in resp_enc.respuestas_preguntas:
                            if resp_preg.pregunta_id != preg.id:
                                continue
                            # opción_id → texto legible
                            opcion_txt = None
                            if resp_preg.opcion_id:
                                opcion_txt = next(
                                    (o.texto for o in preg.opciones if o.id == resp_preg.opcion_id),
                                    None
                                )
                            resp_list.append(
                                {
                                    "texto": resp_preg.texto,
                                    "numero": self._to_float(resp_preg.numero),
                                    "opcion": opcion_txt,
                                }
                            )
                camp_dict["preguntas"].append(
                    {
                        "id": str(preg.id),
                        "texto": preg.texto,
                        "tipo": preg.tipo_pregunta_id,
                        "respuestas": resp_list,
                    }
                )

        # --- GPT → insights --- #
        raw = await self._call_gpt(camp_dict)

        try:
            analysis = CampaignAnalysis(**raw)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Estructura inesperada de GPT: {exc}",
            ) from exc

        return {"campaign_id": str(campaign_id), "analysis": analysis}
