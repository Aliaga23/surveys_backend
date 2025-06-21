from __future__ import annotations

from typing import Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)


def _extract_text_and_payload(msg: Dict[str, Any]) -> Tuple[str, str]:
    """
    Devuelve (texto_visible, id_payload) para cualquier tipo de mensaje.
    """
    mtype = msg.get("type")
    if mtype == "button":  # quick-reply (botones “Sí/No”)
        btn = msg.get("button", {})
        return btn.get("text", ""), btn.get("payload", "")
    if mtype == "interactive":  # reply-button o lista
        data = msg.get("interactive", {})
        if data.get("type") == "button_reply":
            br = data.get("button_reply", {})
            return br.get("title", ""), br.get("id", "")
        if data.get("type") == "list_reply":
            lr = data.get("list_reply", {})
            return lr.get("title", ""), lr.get("id", "")
    if mtype == "text":
        return msg.get("text", {}).get("body", ""), ""
    # Cualquier otro tipo (audio, imagen, documento…)
    return "", ""


def parse_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza el webhook recibido de Whapi.

    Ejemplo mínimo de uso:
    >>> data = parse_webhook(payload)
    >>> if data["kind"] == "message":
    ...     process_incoming(data)

    No lanza excepciones: en caso de error devuelve kind == "error".
    """
    try:
        # 1) Webhook de estados de entrega/lectura
        if "statuses" in payload:
            return {
                "kind": "status",
                "status": payload.get("statuses", [{}])[0],
                "raw": payload,
            }

        # 2) Nada interesante
        if "messages" not in payload or not payload["messages"]:
            return {"kind": "unknown", "raw": payload}

        msg = payload["messages"][0]

        # 3) Mensaje enviado por nosotros mismos
        if msg.get("from_me", False):
            return {"kind": "own", "raw": payload}

        # 4) Extraer texto y/o payload
        text, payload_id = _extract_text_and_payload(msg)

        # 5) Si no hay texto ni payload -> lo tratamos como no-texto
        if not text and not payload_id:
            return {
                "kind": "non_text",
                "subtype": msg.get("type", "unknown"),
                "raw": payload,
            }

        return {
            "kind": "message",
            "from_number": msg.get("from", "").split("@")[0],
            "text": text or payload_id,   # prioriza texto visible
            "payload_id": payload_id,
            "message_id": msg.get("id"),
            "timestamp": msg.get("timestamp"),
            "interactive": msg.get("type") in ("button", "interactive"),
            "raw": payload,
        }

    except Exception as exc:  # pragma: no cover
        logger.exception("Error al parsear webhook: %s", exc)
        return {"kind": "error", "error": str(exc), "raw": payload}