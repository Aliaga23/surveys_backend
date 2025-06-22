# app/routers/pdf_router.py
"""
Genera formularios PDF para encuestas en papel con un diseño **compacto y formal** que cabe, en lo posible, en **una sola hoja A4**.

•  GET /entregas/{entrega_id}/formulario.pdf → PDF individual con QR + preguntas/opciones
•  GET /entregas/campanas/{campana_id}/formularios.zip → ZIP con un PDF por entrega (canal papel)
•  GET /entregas/campanas/{campana_id}/formularios.pdf → PDF combinado con todas las encuestas
"""

from uuid import UUID
from typing import List
import io, zipfile, qrcode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

from app.core.database import get_db
from app.models.survey import EntregaEncuesta, PreguntaEncuesta

router = APIRouter(prefix="/entregas", tags=["PDF / Formularios"])

PAGE_W, PAGE_H = A4
TOP_MARGIN      = 20 * mm
BOTTOM_MARGIN   = 20 * mm
QR_SIZE         = 45 * mm
LINE_HEIGHT     = 5  * mm
BOX_SIZE        = 4  * mm
TEXT_SIZE       = 9
TITLE_SIZE      = 14


def _draw_checkbox(c: Canvas, x: float, baseline_y: float):
    c.rect(x, baseline_y - BOX_SIZE + 1, BOX_SIZE, BOX_SIZE, stroke=1, fill=0)


def _build_pdf(entrega: EntregaEncuesta, preguntas: List[PreguntaEncuesta]) -> io.BytesIO:
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=A4)
    
    _render_survey_page(c, entrega, preguntas)
    
    c.save()
    buf.seek(0)
    return buf


@router.get("/{entrega_id}/formulario.pdf")
async def pdf_por_entrega(entrega_id: UUID, db: Session = Depends(get_db)):
    ent = (
        db.query(EntregaEncuesta)
        .options(joinedload(EntregaEncuesta.campana))
        .filter(EntregaEncuesta.id == entrega_id)
        .first()
    )
    if not ent:
        raise HTTPException(404, "Entrega no encontrada")

    preguntas = (
        db.query(PreguntaEncuesta)
        .options(joinedload(PreguntaEncuesta.opciones))
        .filter(PreguntaEncuesta.plantilla_id == ent.campana.plantilla_id)
        .order_by(PreguntaEncuesta.orden)
        .all()
    )

    pdf = _build_pdf(ent, preguntas)
    headers = {"Content-Disposition": f'attachment; filename="{ent.id}.pdf"'}
    return StreamingResponse(pdf, media_type="application/pdf", headers=headers)


@router.get("/campanas/{campana_id}/formularios.zip")
async def pdf_bulk(campana_id: UUID, db: Session = Depends(get_db)):
    entregas = (
        db.query(EntregaEncuesta)
        .options(joinedload(EntregaEncuesta.campana))
        .filter(EntregaEncuesta.campana_id == campana_id)
        .order_by(EntregaEncuesta.id)
        .all()
    )
    if not entregas:
        raise HTTPException(404, "Sin entregas para esta campaña")

    plantilla_id = entregas[0].campana.plantilla_id
    preguntas = (
        db.query(PreguntaEncuesta)
        .options(joinedload(PreguntaEncuesta.opciones))
        .filter(PreguntaEncuesta.plantilla_id == plantilla_id)
        .order_by(PreguntaEncuesta.orden)
        .all()
    )

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        for ent in entregas:
            pdf_bytes = _build_pdf(ent, preguntas).getvalue()
            zf.writestr(f"{ent.id}.pdf", pdf_bytes)
    zip_buf.seek(0)

    headers = {"Content-Disposition": f'attachment; filename="formularios_{campana_id}.zip"'}
    return StreamingResponse(zip_buf, media_type="application/zip", headers=headers)


@router.get("/campanas/{campana_id}/formularios.pdf")
async def pdf_combined(campana_id: UUID, db: Session = Depends(get_db)):
    entregas = (
        db.query(EntregaEncuesta)
        .options(joinedload(EntregaEncuesta.campana))
        .filter(EntregaEncuesta.campana_id == campana_id)
        .order_by(EntregaEncuesta.id)
        .all()
    )
    if not entregas:
        raise HTTPException(404, "Sin entregas para esta campaña")

    plantilla_id = entregas[0].campana.plantilla_id
    preguntas = (
        db.query(PreguntaEncuesta)
        .options(joinedload(PreguntaEncuesta.opciones))
        .filter(PreguntaEncuesta.plantilla_id == plantilla_id)
        .order_by(PreguntaEncuesta.orden)
        .all()
    )

    buf = io.BytesIO()
    c = Canvas(buf, pagesize=A4)
    
    for i, entrega in enumerate(entregas):
        if i > 0:
            c.showPage()
        
        _render_survey_page(c, entrega, preguntas)
    
    c.save()
    buf.seek(0)

    headers = {"Content-Disposition": f'attachment; filename="formularios_{campana_id}.pdf"'}
    return StreamingResponse(buf, media_type="application/pdf", headers=headers)


def _render_survey_page(c: Canvas, entrega: EntregaEncuesta, preguntas: List[PreguntaEncuesta]):
    y = PAGE_H - TOP_MARGIN  

    qr_img = qrcode.make(str(entrega.id))
    qr_buf = io.BytesIO()
    qr_img.save(qr_buf, format="PNG")
    qr_buf.seek(0)
    qr_reader = ImageReader(qr_buf)
    c.drawImage(qr_reader, (PAGE_W - QR_SIZE) / 2, y - QR_SIZE, QR_SIZE, QR_SIZE)
    y -= QR_SIZE + 8 * mm

    c.setFont("Helvetica-Bold", TITLE_SIZE)
    c.drawCentredString(PAGE_W / 2, y, entrega.campana.nombre)
    y -= TITLE_SIZE
    
    y -= LINE_HEIGHT * 3

    c.setFont("Helvetica", TEXT_SIZE)

    for p in preguntas:
        c.drawString(15 * mm, y, f"{p.orden}. {p.texto}")
        y -= LINE_HEIGHT

        if p.tipo_pregunta_id == 3:
            c.setFont("Helvetica", TEXT_SIZE - 1)
            c.drawString(17 * mm, y, "(una opción)")
            c.setFont("Helvetica", TEXT_SIZE)
            y -= LINE_HEIGHT
        elif p.tipo_pregunta_id == 4:
            c.setFont("Helvetica", TEXT_SIZE - 1)
            c.drawString(17 * mm, y, "(varias opciones)")
            c.setFont("Helvetica", TEXT_SIZE)
            y -= LINE_HEIGHT

        if p.tipo_pregunta_id in (3, 4):
            for opt in p.opciones:
                _draw_checkbox(c, 20 * mm, y + BOX_SIZE / 2)
                c.drawString(25 * mm, y, opt.texto)
                y -= LINE_HEIGHT

        elif p.tipo_pregunta_id == 1:
            y -= LINE_HEIGHT * 0.5
            
            for _ in range(2):
                c.line(20 * mm, y, PAGE_W - 20 * mm, y)
                y -= LINE_HEIGHT * 1.5

        elif p.tipo_pregunta_id == 2:
            y -= LINE_HEIGHT * 0.5
            
            c.line(20 * mm, y, 70 * mm, y)
            y -= LINE_HEIGHT * 1.5

        y -= LINE_HEIGHT * 0.5  

        if y < BOTTOM_MARGIN + 20 * mm:
            break
