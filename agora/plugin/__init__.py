"""Agora plugin v3 — entry point.

Detecta el rol (orchestrator o worker) basándose en el nombre del profile
(último componente de HERMES_HOME). Si es "hermes" → orchestrator.
Todo lo demás → worker.
"""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Ruta canónica del plugin — cualquier instancia cargada desde otro lugar
# es una copia desactualizada y debe advertirse al desarrollador.
from ._paths import get_agora_plugin_dir
_CANONICAL_DIR = get_agora_plugin_dir()


def _check_canonical_path() -> None:
    """Advierte si el plugin se cargó desde una copia en vez del master."""
    try:
        loaded_from = Path(__file__).parent.resolve()
        canonical = _CANONICAL_DIR.resolve()
        if loaded_from != canonical:
            logger.warning(
                "agora: plugin cargado desde ruta NO canónica: %s\n"
                "       Esperado: %s\n"
                "       El symlink puede estar roto o hay una copia desactualizada.",
                loaded_from, canonical,
            )
    except Exception:
        pass  # nunca debe romper el arranque


def register(ctx, timeout_seconds: int = 300):
    _check_canonical_path()

    hermes_home = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
    profile_name = hermes_home.name  # "hermes", "ariadna", etc.

    if profile_name == "hermes":
        # orchestrator side — registra la tool talk_to
        from . import _orchestrator

        _orchestrator.register(ctx, timeout_seconds)
    else:
        # worker side — registra hooks del worker
        from . import _worker

        _worker.register(ctx)
