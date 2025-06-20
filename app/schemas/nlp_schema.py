from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from uuid import UUID
from datetime import datetime

class NLPAnalysisRequest(BaseModel):
    """Parámetros para solicitar análisis NLP"""
    fecha_inicio: Optional[datetime] = None
    fecha_fin: Optional[datetime] = None
    campana_id: Optional[UUID] = None
    num_topics: int = Field(default=3, ge=1, le=5)
    num_clusters: int = Field(default=3, ge=1, le=5)

class SentimentAnalysis(BaseModel):
    """Resultados de análisis de sentimiento"""
    promedio: float
    positivo: int
    neutro: int
    negativo: int
    distribucion: Dict[str, float]

class KeywordPair(BaseModel):
    """Par palabra-valor para keywords"""
    palabra: str
    valor: float

class KeywordAnalysis(BaseModel):
    """Resultados de análisis de palabras clave"""
    keywords: List[KeywordPair]
    word_cloud: Optional[str] = None  # Base64 de la imagen

class TopicKeyword(BaseModel):
    """Palabra clave con peso para un tema"""
    palabra: str
    peso: float

class TopicAnalysis(BaseModel):
    """Tema descubierto en el análisis"""
    id: int
    palabras_clave: List[TopicKeyword]
    peso: float

class ClusterInfo(BaseModel):
    """Información de un cluster"""
    id: int
    tamaño: int
    keywords: List[tuple]
    muestras: List[str]

class ClusterAnalysis(BaseModel):
    """Resultados de análisis de clusters"""
    clusters: List[ClusterInfo]
    total_clusters: int

class PreguntaAnalisis(BaseModel):
    """Análisis de respuestas para una pregunta específica"""
    pregunta_id: str
    pregunta_texto: Optional[str] = None
    total_respuestas: int
    tipo_pregunta: Optional[int] = None
    sentiment: Optional[Dict[str, Any]] = None
    keywords: Optional[Dict[str, Any]] = None
    topics: Optional[List[Dict[str, Any]]] = None
    estadisticas: Optional[Dict[str, Any]] = None
    opciones: Optional[Dict[str, Any]] = None

class CampanaInfo(BaseModel):
    """Información básica de una campaña"""
    id: str
    nombre: str
    total_respuestas: int

class NLPAnalysisResponse(BaseModel):
    """Respuesta completa del análisis NLP"""
    suscriptor_id: str
    fecha_analisis: datetime
    periodo: Dict[str, Optional[datetime]]
    total_respuestas: int
    total_respuestas_texto: int
    sentiment_global: Dict[str, Any]
    keywords_global: Dict[str, Any]
    topics: List[Dict[str, Any]]
    clusters: Dict[str, Any]
    analisis_por_pregunta: List[Dict[str, Any]]
    campanas: List[Dict[str, Any]]