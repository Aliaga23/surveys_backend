from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from uuid import UUID
from datetime import datetime


# ───────── Petición ──────────────────────────────────────────────────────
class NLPAnalysisRequest(BaseModel):
    fecha_inicio: Optional[datetime] = None
    fecha_fin:    Optional[datetime] = None
    campana_id:   Optional[UUID]     = None
    num_topics:   int = Field(default=3, ge=1, le=5)
    num_clusters: int = Field(default=3, ge=1, le=5)


# ───────── Entidades auxiliares ──────────────────────────────────────────
class KeywordPair(BaseModel):
    palabra: str
    valor:   float

class TopicKeyword(BaseModel):
    palabra: str
    peso:    float

class TrendPoint(BaseModel):
    fecha: datetime
    valor: float


# ───────── Resultados parciales ──────────────────────────────────────────
class SentimentAnalysis(BaseModel):
    promedio: float
    positivo: int
    neutro:   int
    negativo: int
    distribucion: Dict[str, float]          # ej. {"positivo": 32.1, ...}
    # KPIs adicionales
    kpis: Optional[Dict[str, Optional[float]]] = None  # {"nps": 12.5, "csat": 84.3}
    trend: Optional[List[TrendPoint]]         = None   # rolling weekly NPS

class KeywordAnalysis(BaseModel):
    keywords:   List[KeywordPair]
    word_cloud: Optional[str] = None           # PNG base64

class TopicAnalysis(BaseModel):
    id:             int
    palabras_clave: List[TopicKeyword]
    peso:           float

class ClusterInfo(BaseModel):
    id:       int
    tamaño:   int
    keywords: List[KeywordPair]
    muestras: List[str]

class ClusterAnalysis(BaseModel):
    clusters:       List[ClusterInfo]
    total_clusters: int


# ───────── Análisis por pregunta ─────────────────────────────────────────
class PreguntaAnalisis(BaseModel):
    pregunta_id:      str
    pregunta_texto:   Optional[str] = None
    total_respuestas: int
    tipo_pregunta:    Optional[int] = None
    sentiment:        Optional[SentimentAnalysis] = None
    keywords:         Optional[KeywordAnalysis]   = None
    topics:           Optional[List[TopicAnalysis]] = None
    estadisticas:     Optional[Dict[str, Any]]    = None
    opciones:         Optional[Dict[str, Any]]    = None


# ───────── Información de campaña ────────────────────────────────────────
class CampanaInfo(BaseModel):
    id:                str
    nombre:            str
    total_respuestas:  int


# ───────── Respuesta completa ────────────────────────────────────────────
class NLPAnalysisResponse(BaseModel):
    suscriptor_id:            str
    fecha_analisis:           datetime
    periodo:                  Dict[str, Optional[datetime]]
    total_respuestas:         int
    total_respuestas_texto:   int

    sentiment_global: SentimentAnalysis
    topics:           List[TopicAnalysis]
    clusters:         ClusterAnalysis

    analisis_por_pregunta: List[PreguntaAnalisis]
    campanas:              List[CampanaInfo]

    # Campo opcional con el texto generado por el LLM
    recommendations: Optional[str] = None
