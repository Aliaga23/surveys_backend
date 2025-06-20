import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple, Any
from uuid import UUID
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from datetime import datetime, timedelta
import spacy
import nltk
from nltk.sentiment import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.decomposition import LatentDirichletAllocation, NMF
from sklearn.cluster import KMeans
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import io
import base64
from collections import Counter

# Inicializar modelos de NLP
try:
    nlp = spacy.load("es_core_news_md")
except:
    import sys
    import subprocess
    subprocess.check_call([sys.executable, "-m", "spacy", "download", "es_core_news_md"])
    nlp = spacy.load("es_core_news_md")

try:
    nltk.data.find('sentiment/vader_lexicon.zip')
except LookupError:
    nltk.download('vader_lexicon')
    nltk.download('punkt')
    nltk.download('stopwords')

from app.models.survey import (
    CampanaEncuesta, EntregaEncuesta, RespuestaEncuesta, 
    RespuestaPregunta, PreguntaEncuesta, OpcionEncuesta
)
from app.models.suscriptor import Suscriptor
from app.schemas.nlp_schema import (
    NLPAnalysisRequest, NLPAnalysisResponse, 
    SentimentAnalysis, TopicAnalysis, 
    KeywordAnalysis, ClusterAnalysis
)

class NLPAnalysisService:
    """Servicio para análisis de respuestas usando NLP y ML"""
    
    def __init__(self, db: Session):
        self.db = db
        self.sia = SentimentIntensityAnalyzer()
        self.spanish_stopwords = set(nltk.corpus.stopwords.words('spanish'))
        # Palabras adicionales para eliminar en español
        self.spanish_stopwords.update(["si", "no", "tal", "vez", "quizás", "gracias", "ok", "bueno", "buenos", "bien"])

    def get_respuestas_by_suscriptor(
        self, 
        suscriptor_id: UUID, 
        start_date: Optional[datetime] = None, 
        end_date: Optional[datetime] = None,
        campana_id: Optional[UUID] = None
    ) -> List[Dict]:
        """Obtiene todas las respuestas textuales para un suscriptor en un periodo"""
        
        # Base query
        query = (
            self.db.query(
                RespuestaPregunta.texto,
                PreguntaEncuesta.texto.label("pregunta_texto"),
                PreguntaEncuesta.id.label("pregunta_id"),
                PreguntaEncuesta.tipo_pregunta_id,
                RespuestaPregunta.numero,
                OpcionEncuesta.texto.label("opcion_texto"),
                RespuestaEncuesta.id.label("respuesta_id"),
                RespuestaEncuesta.entrega_id,
                RespuestaEncuesta.recibido_en,
                CampanaEncuesta.nombre.label("campana_nombre"),
                CampanaEncuesta.id.label("campana_id")
            )
            .join(RespuestaEncuesta, RespuestaPregunta.respuesta_id == RespuestaEncuesta.id)
            .join(EntregaEncuesta, RespuestaEncuesta.entrega_id == EntregaEncuesta.id)
            .join(CampanaEncuesta, EntregaEncuesta.campana_id == CampanaEncuesta.id)
            .join(PreguntaEncuesta, RespuestaPregunta.pregunta_id == PreguntaEncuesta.id)
            .outerjoin(OpcionEncuesta, RespuestaPregunta.opcion_id == OpcionEncuesta.id)
            .filter(CampanaEncuesta.suscriptor_id == suscriptor_id)
        )
        
        # Filtrar por rango de fechas
        if start_date:
            query = query.filter(RespuestaEncuesta.recibido_en >= start_date)
        if end_date:
            query = query.filter(RespuestaEncuesta.recibido_en <= end_date)
            
        # Filtrar por campaña específica
        if campana_id:
            query = query.filter(CampanaEncuesta.id == campana_id)
            
        return query.all()
    
    def analyze_sentiment(self, textos: List[str]) -> Dict[str, Any]:
        """Realiza análisis de sentimiento sobre respuestas textuales"""
        if not textos:
            return {
                "promedio": 0,
                "positivo": 0,
                "negativo": 0,
                "neutro": 0,
                "distribucion": {"positivo": 0, "neutro": 0, "negativo": 0}
            }
        
        sentiments = []
        categorias = {"positivo": 0, "neutro": 0, "negativo": 0}
        
        for texto in textos:
            if not texto or not isinstance(texto, str):
                continue
                
            sentiment = self.sia.polarity_scores(texto)
            compound = sentiment["compound"]
            sentiments.append(compound)
            
            # Categorizar sentimiento
            if compound >= 0.05:
                categorias["positivo"] += 1
            elif compound <= -0.05:
                categorias["negativo"] += 1
            else:
                categorias["neutro"] += 1
        
        total = sum(categorias.values()) or 1  # Evitar división por cero
        distribucion = {k: round(v/total*100, 2) for k, v in categorias.items()}
        
        return {
            "promedio": round(sum(sentiments)/len(sentiments), 3) if sentiments else 0,
            "positivo": categorias["positivo"],
            "negativo": categorias["negativo"],
            "neutro": categorias["neutro"],
            "distribucion": distribucion
        }
    
    def extract_keywords(self, textos: List[str], top_n: int = 15) -> Dict[str, Any]:
        """Extrae palabras clave de las respuestas textuales"""
        if not textos:
            return {"keywords": [], "word_cloud": None}
            
        # Preprocesamiento
        processed_texts = []
        for texto in textos:
            if not texto or not isinstance(texto, str):
                continue
                
            doc = nlp(texto.lower())
            # Filtrar palabras relevantes (sustantivos, verbos, adjetivos) y eliminar stopwords
            tokens = [token.lemma_ for token in doc 
                     if token.is_alpha and 
                     not token.is_stop and
                     token.lemma_ not in self.spanish_stopwords and
                     len(token.lemma_) > 2 and
                     (token.pos_ in ["NOUN", "VERB", "ADJ"])]
            processed_texts.append(" ".join(tokens))
        
        if not processed_texts:
            return {"keywords": [], "word_cloud": None}
        
        # Extraer keywords con TF-IDF
        vectorizer = TfidfVectorizer(
            max_df=0.9, min_df=2, max_features=200, 
            stop_words=list(self.spanish_stopwords)
        )
        
        try:
            tfidf_matrix = vectorizer.fit_transform(processed_texts)
            feature_names = vectorizer.get_feature_names_out()
            
            # Sumar pesos TF-IDF por término
            tfidf_sums = np.array(tfidf_matrix.sum(axis=0)).flatten()
            top_indices = tfidf_sums.argsort()[-top_n:][::-1]
            top_keywords = [(feature_names[i], float(tfidf_sums[i])) for i in top_indices]
            
            # Generar nube de palabras
            wordcloud_img = None
            if processed_texts:
                all_text = " ".join(processed_texts)
                wordcloud = WordCloud(
                    width=800, height=400,
                    background_color="white",
                    max_words=100,
                    contour_width=3,
                    contour_color='steelblue'
                ).generate(all_text)
                
                img_data = io.BytesIO()
                plt.figure(figsize=(10, 5))
                plt.imshow(wordcloud, interpolation='bilinear')
                plt.axis("off")
                plt.tight_layout(pad=0)
                plt.savefig(img_data, format='png')
                img_data.seek(0)
                wordcloud_img = base64.b64encode(img_data.getvalue()).decode()
                plt.close()
            
            return {
                "keywords": top_keywords,
                "word_cloud": wordcloud_img
            }
                
        except Exception as e:
            print(f"Error en extract_keywords: {str(e)}")
            return {"keywords": [], "word_cloud": None}
    
    def discover_topics(self, textos: List[str], n_topics: int = 3) -> List[Dict[str, Any]]:
        """Descubre temas principales usando LDA o NMF"""
        if not textos or len(textos) < n_topics * 2:  # Necesitamos suficientes textos
            return []
            
        # Preprocesamiento
        processed_texts = []
        for texto in textos:
            if not texto or not isinstance(texto, str):
                continue
                
            doc = nlp(texto.lower())
            tokens = [token.lemma_ for token in doc 
                     if token.is_alpha and 
                     not token.is_stop and
                     token.lemma_ not in self.spanish_stopwords and
                     len(token.lemma_) > 2]
            processed_texts.append(" ".join(tokens))
        
        if not processed_texts or len(processed_texts) < n_topics:
            return []
        
        try:
            # Vectorización
            vectorizer = CountVectorizer(
                max_df=0.9, min_df=2, max_features=300, 
                stop_words=list(self.spanish_stopwords)
            )
            
            dtm = vectorizer.fit_transform(processed_texts)
            feature_names = vectorizer.get_feature_names_out()
            
            # Usar NMF que suele funcionar mejor para textos cortos como respuestas de encuestas
            nmf_model = NMF(n_components=n_topics, random_state=42)
            nmf_model.fit(dtm)
            
            topics = []
            for topic_idx, topic in enumerate(nmf_model.components_):
                top_words_idx = topic.argsort()[:-11:-1]  # 10 palabras principales
                top_words = [(feature_names[i], float(topic[i])) for i in top_words_idx]
                topics.append({
                    "id": topic_idx,
                    "palabras_clave": top_words,
                    "peso": float(topic.sum())
                })
            
            return topics
                
        except Exception as e:
            print(f"Error en discover_topics: {str(e)}")
            return []
    
    def cluster_responses(self, textos: List[str], n_clusters: int = 3) -> Dict[str, Any]:
        """Agrupa respuestas similares usando K-means"""
        if not textos or len(textos) < n_clusters * 2:
            return {"clusters": [], "silhouette": 0}
        
        try:
            # Vectorización con TF-IDF
            vectorizer = TfidfVectorizer(
                max_df=0.9, min_df=2, max_features=200,
                stop_words=list(self.spanish_stopwords)
            )
            
            tfidf_matrix = vectorizer.fit_transform(textos)
            
            # Ajustar K-means
            kmeans = KMeans(n_clusters=min(n_clusters, len(textos)//2), random_state=42)
            clusters = kmeans.fit_predict(tfidf_matrix)
            
            # Organizar respuestas por cluster
            cluster_responses = {}
            for i, cluster_id in enumerate(clusters):
                if cluster_id not in cluster_responses:
                    cluster_responses[cluster_id] = []
                cluster_responses[cluster_id].append(textos[i])
            
            # Determinar palabras clave por cluster
            cluster_keywords = {}
            for cluster_id, resp in cluster_responses.items():
                text = " ".join(resp)
                doc = nlp(text.lower())
                # Extraer sustantivos y adjetivos principales
                tokens = [token.lemma_ for token in doc 
                         if token.is_alpha and 
                         not token.is_stop and
                         token.lemma_ not in self.spanish_stopwords and
                         (token.pos_ in ["NOUN", "ADJ"])]
                
                # Contar frecuencia
                word_freq = Counter(tokens)
                cluster_keywords[cluster_id] = word_freq.most_common(5)
            
            # Preparar resultados
            clusters_info = []
            for cluster_id in sorted(cluster_responses.keys()):
                clusters_info.append({
                    "id": int(cluster_id),
                    "tamaño": len(cluster_responses[cluster_id]),
                    "keywords": cluster_keywords.get(cluster_id, []),
                    "muestras": cluster_responses[cluster_id][:3]  # Primeras 3 respuestas como muestra
                })
            
            return {
                "clusters": clusters_info,
                "total_clusters": len(clusters_info)
            }
                
        except Exception as e:
            print(f"Error en cluster_responses: {str(e)}")
            return {"clusters": [], "total_clusters": 0}
    
    def analisis_por_pregunta(self, respuestas: List, pregunta_id: UUID) -> Dict[str, Any]:
        """Realiza análisis específico por pregunta"""
        # Filtrar respuestas para esta pregunta
        resp_pregunta = [r for r in respuestas if str(r.pregunta_id) == str(pregunta_id)]
        
        if not resp_pregunta:
            return {
                "pregunta_id": str(pregunta_id),
                "total_respuestas": 0,
                "sentiment": None,
                "keywords": None,
                "tipo_pregunta": None
            }
        
        # Determinar tipo de pregunta y extraer texto relevante
        tipo_pregunta = resp_pregunta[0].tipo_pregunta_id
        
        textos = []
        numeros = []
        opciones = {}
        
        for r in resp_pregunta:
            # Para preguntas de texto
            if tipo_pregunta == 1 and r.texto:
                textos.append(r.texto)
            
            # Para preguntas numéricas
            elif tipo_pregunta == 2 and r.numero is not None:
                numeros.append(float(r.numero))
                
            # Para preguntas de selección única o múltiple
            elif tipo_pregunta in [3, 4] and r.opcion_texto:
                opcion = r.opcion_texto
                if opcion in opciones:
                    opciones[opcion] += 1
                else:
                    opciones[opcion] = 1
        
        result = {
            "pregunta_id": str(pregunta_id),
            "pregunta_texto": resp_pregunta[0].pregunta_texto if resp_pregunta else None,
            "total_respuestas": len(resp_pregunta),
            "tipo_pregunta": tipo_pregunta
        }
        
        # Análisis según tipo de pregunta
        if tipo_pregunta == 1:  # Texto
            result["sentiment"] = self.analyze_sentiment(textos)
            result["keywords"] = self.extract_keywords(textos, top_n=10)
            if len(textos) >= 6:
                result["topics"] = self.discover_topics(textos, n_topics=min(3, len(textos)//2))
            
        elif tipo_pregunta == 2:  # Numérico
            if numeros:
                result["estadisticas"] = {
                    "promedio": round(sum(numeros)/len(numeros), 2),
                    "mediana": round(np.median(numeros), 2),
                    "min": min(numeros),
                    "max": max(numeros),
                    "desviacion": round(np.std(numeros), 2) if len(numeros) > 1 else 0,
                    "distribucion": self._histogram_data(numeros)
                }
            
        elif tipo_pregunta in [3, 4]:  # Opciones
            total = sum(opciones.values())
            result["opciones"] = {
                "conteo": opciones,
                "porcentajes": {k: round(v/total*100, 1) for k, v in opciones.items()}
            }
            
        return result
    
    def _histogram_data(self, valores: List[float]) -> Dict[str, List]:
        """Genera datos para histograma de valores numéricos"""
        if not valores:
            return {"bins": [], "counts": []}
            
        try:
            counts, bins = np.histogram(valores, bins=5)
            return {
                "bins": bins.tolist(),
                "counts": counts.tolist()
            }
        except Exception as e:
            print(f"Error generando histograma: {str(e)}")
            return {"bins": [], "counts": []}
    
    async def analyze_responses(
        self, 
        suscriptor_id: UUID, 
        params: NLPAnalysisRequest
    ) -> NLPAnalysisResponse:
        """Punto de entrada principal para el análisis de respuestas"""
        
        # Verificar cantidad de datos antes de proceder
        respuestas = self.get_respuestas_by_suscriptor(
            suscriptor_id, 
            params.fecha_inicio, 
            params.fecha_fin,
            params.campana_id
        )
        
        if not respuestas:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No se encontraron respuestas para analizar"
            )
            
        # Extraer solo los textos para análisis global
        textos = [r.texto for r in respuestas if r.texto and isinstance(r.texto, str)]
        
        # Análisis global de sentimiento y keywords
        sentiment_global = self.analyze_sentiment(textos)
        keywords_global = self.extract_keywords(textos)
        
        # Encontrar preguntas únicas
        preguntas_ids = set(str(r.pregunta_id) for r in respuestas)
        
        # Análisis por pregunta
        analisis_preguntas = []
        for pregunta_id in preguntas_ids:
            analisis_preguntas.append(
                self.analisis_por_pregunta(respuestas, UUID(pregunta_id))
            )
            
        # Descubrir temas y clusters si hay suficientes datos
        topics = []
        clusters = {"clusters": [], "total_clusters": 0}
        if len(textos) >= 10:
            topics = self.discover_topics(textos, n_topics=min(params.num_topics, len(textos)//3))
            if len(textos) >= 15:
                clusters = self.cluster_responses(
                    textos, 
                    n_clusters=min(params.num_clusters, len(textos)//5)
                )
        
        # Información adicional
        campanas = {}
        for r in respuestas:
            campana_id = str(r.campana_id)
            if campana_id not in campanas:
                campanas[campana_id] = {
                    "id": campana_id,
                    "nombre": r.campana_nombre,
                    "total_respuestas": 0
                }
            campanas[campana_id]["total_respuestas"] += 1
            
        # Armar respuesta
        return {
            "suscriptor_id": str(suscriptor_id),
            "fecha_analisis": datetime.now(),
            "periodo": {
                "inicio": params.fecha_inicio,
                "fin": params.fecha_fin
            },
            "total_respuestas": len(respuestas),
            "total_respuestas_texto": len(textos),
            "sentiment_global": sentiment_global,
            "keywords_global": keywords_global,
            "topics": topics,
            "clusters": clusters,
            "analisis_por_pregunta": analisis_preguntas,
            "campanas": list(campanas.values())
        }

# Instancia del servicio para acceso directo
def get_nlp_service(db: Session) -> NLPAnalysisService:
    return NLPAnalysisService(db)