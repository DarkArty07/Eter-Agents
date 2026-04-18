"""
Agora — Conversation Log.

Append-only log de conversaciones Agora para observabilidad en tiempo real.
Escribe a ~/.hermes/agora/conversations.log — hacer `tail -f` para ver progreso.

Formato por línea:
  [TIMESTAMP] DIRECTION AGENT (session_id) │ MESSAGE

Donde:
  DIRECTION = → (enviado) | ← (recibido) | ⟳ (sistema)
  MESSAGE = preview truncado a 200 chars
"""

import os
import time
from pathlib import Path

from ._paths import get_conversations_log

CONVERSATIONS_LOG = get_conversations_log()
MAX_PREVIEW = 200


def _truncate(text: str, max_len: int = MAX_PREVIEW) -> str:
    """Truncar texto y agregar elipsis si es necesario."""
    if not text:
        return "(vacío)"
    # Reemplazar newlines para que sea una sola línea
    clean = text.replace("\n", "↵").strip()
    if len(clean) > max_len:
        return clean[:max_len - 3] + "..."
    return clean


def _timestamp() -> str:
    """ISO-like timestamp legible."""
    return time.strftime("%H:%M:%S", time.localtime())


def log_sent(agent: str, session_id: str, prompt: str) -> None:
    """Log cuando Hermes envía un mensaje a un agente."""
    _append(f"[{_timestamp()}] → {agent} ({session_id}) │ {_truncate(prompt)}")


def log_received(agent: str, session_id: str, response: str) -> None:
    """Log cuando Hermes recibe una respuesta de un agente."""
    _append(f"[{_timestamp()}] ← {agent} ({session_id}) │ {_truncate(response)}")


def log_system(agent: str, session_id: str, event: str) -> None:
    """Log eventos del sistema (open, close, error, timeout, etc.)."""
    _append(f"[{_timestamp()}] ⟳ {agent} ({session_id}) │ {event}")


def _append(line: str) -> None:
    """Append una línea al log. No bloquea, ignora errores.

    El flush() explícito garantiza que la línea llega al buffer del kernel
    inmediatamente — sin esperar a que Python vacíe su buffer interno.
    Esto es necesario para que `tail -f` y dashboards de polling detecten
    el evento en tiempo real, sin importar el tamaño del buffer de Python.
    """
    try:
        CONVERSATIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CONVERSATIONS_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    except OSError:
        pass  # Silently fail — logging never breaks the system