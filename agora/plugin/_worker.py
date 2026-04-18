"""
Agora — Lado worker (Ariadna y futuros agentes).

Registra un hook:
  post_llm_call    — escribe la respuesta del LLM a inbox JSON atómico

El watchdog ha sido eliminado. Las respuestas se escriben ahora a archivos
JSON en ~/.hermes/agora/inbox/ usando escritura atómica (temp + rename).
"""

import json
import logging
import os
import time
from pathlib import Path

from ._convo_log import log_received, log_system
from ._paths import get_ipc_dir, get_inbox_dir

logger = logging.getLogger(__name__)

IPC_DIR = get_ipc_dir()
INBOX_DIR = get_inbox_dir()


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------


def register(ctx):
    ctx.register_hook("post_llm_call", _on_response_complete)


# ---------------------------------------------------------------------------
# Hook: post_llm_call — escribe respuesta a inbox JSON atómico
# ---------------------------------------------------------------------------


def _on_response_complete(assistant_response: str, **kwargs):
    """Write response to inbox file atomically (replaces FIFO)."""
    profile_name = _get_profile_name()
    if not profile_name:
        return
    
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    
    payload = {
        "written_at": time.time(),
        "response": assistant_response or "",
        "profile_name": profile_name,
    }
    
    # Atomic write: write to temp, then rename
    tmp_path = INBOX_DIR / f"{profile_name}.tmp"
    final_path = INBOX_DIR / f"{profile_name}.json"
    
    try:
        tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp_path.rename(final_path)  # Atomic on same device
        log_received(profile_name, "", assistant_response or "")
        logger.info("agora: response written to inbox: %s (%d chars)", final_path, len(assistant_response or ""))
    except OSError as exc:
        log_system(profile_name, "", f"ERROR writing inbox: {exc}")
        logger.warning("agora: error writing inbox %s: %s", final_path, exc)


# ---------------------------------------------------------------------------
# Helper: obtener nombre del profile desde HERMES_HOME
# ---------------------------------------------------------------------------


def _get_profile_name() -> str:
    """Retorna el nombre del profile (último componente de HERMES_HOME)."""
    hermes_home = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
    return hermes_home.name
