from __future__ import annotations
from typing import Dict, Any, Tuple
import logging

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# HELPERS
# --------------------------------------------------------------------------- #

def _extract_text_and_payload(msg: Dict[str, Any]) -> Tuple[str, str]:
    """
    Devuelve (texto_visible, payload_id) a partir de un dict ``msg``.
    Si el mensaje no es texto / botón / lista, devuelve ("", "").
    """
    mtype = msg.get("type")

    # ---- 1) Botón “template” directo (API clásica) -------------------------
    if mtype == "button":                 # Android / iOS direct
        btn = msg.get("button", {})
        return btn.get("text", ""), btn.get("payload", "")

    # ---- 2) Formato “interactive” de la Cloud API --------------------------
    if mtype == "interactive":
        data = msg.get("interactive", {})
        if data.get("type") == "button_reply":
            br = data["button_reply"]
            return br.get("title", ""), br.get("id", "")
        if data.get("type") == "list_reply":
            lr = data["list_reply"]
            return lr.get("title", ""), lr.get("id", "")

    # ---- 3) NUEVO: Formato “reply” (UI móvil al pulsar botón / lista) ------
    if mtype == "reply":
        rep = msg.get("reply", {})
        if rep.get("type") == "buttons_reply":
            br = rep["buttons_reply"]
            return br.get("title", ""), br.get("id", "")
        if rep.get("type") == "list_reply":
            lr = rep["list_reply"]
            return lr.get("title", ""), lr.get("id", "")

    # ---- 4) iOS reenvía interactivo como “text” + context ------------------
    if mtype == "text" and msg.get("context", {}).get("id"):
        return msg["text"]["body"], ""            # payload vacío, texto visible

    # ---- 5) Texto plano normal --------------------------------------------
    if mtype == "text":
        return msg["text"]["body"], ""

    # ---- 6) Cualquier otro tipo (imagen, audio, etc.) ----------------------
    return "", ""


# --------------------------------------------------------------------------- #
# PARSER PRINCIPAL
# --------------------------------------------------------------------------- #

def parse_webhook(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza el webhook de Whapi y clasifica el contenido.

    Salida:
        kind = "message" | "status" | "own" | "non_text" | "unknown" | "error"
        + otros campos según corresponda.

    Nunca lanza excepción: ante error ⇒ kind == "error".
    """
    try:
        # 0) Notificaciones de entrega/lectura
        if "statuses" in payload:
            return {
                "kind": "status",
                "status": payload.get("statuses", [{}])[0],
                "raw": payload,
            }

        # 1) No hay mensajes
        if "messages" not in payload or not payload["messages"]:
            return {"kind": "unknown", "raw": payload}

        msg = payload["messages"][0]

        # 2) Mensaje enviado por nosotros
        if msg.get("from_me", False):
            return {"kind": "own", "raw": payload}

        # 3) Extraer texto y/o payload
        text, payload_id = _extract_text_and_payload(msg)

        # 4) Nada útil (p.e. sticker, imagen…)
        if not text and not payload_id:
            return {
                "kind": "non_text",
                "subtype": msg.get("type", "unknown"),
                "raw": payload,
            }

        # 5) Mensaje válido de usuario
        interactive_types = {"button", "interactive", "reply"}
        return {
            "kind": "message",
            "from_number": msg.get("from", "").split("@")[0],
            "text": text or payload_id,               # prioriza texto visible
            "payload_id": payload_id,
            "message_id": msg.get("id"),
            "timestamp": msg.get("timestamp"),
            "interactive": msg.get("type") in interactive_types,
            "raw": payload,
        }

    except Exception as exc:  # pragma: no cover
        logger.exception("Error al parsear webhook: %s", exc)
        return {"kind": "error", "error": str(exc), "raw": payload}
