"""
Agora — Path utilities with HERMES_HOME support.

Determina la raíz del ecosistema Hermes basado en HERMES_HOME:
- Si HERMES_HOME=~/.hermes/profiles/hermes (profile mode) → raíz=~/.hermes/
- Si HERMES_HOME=~/.hermes (direct mode) → raíz=~/.hermes/

La función get_hermes_root() devuelve la raíz del ecosistema (~/.hermes/).
"""

import os
from pathlib import Path


def get_hermes_root() -> Path:
    """
    Get the root of the Hermes ecosystem (~/.hermes/).
    
    HERMES_HOME logic:
    - If HERMES_HOME=~/.hermes/profiles/hermes (profile mode), root is HERMES_HOME.parent.parent
    - If HERMES_HOME=~/.hermes (direct mode), root is HERMES_HOME
    
    Returns:
        Path: The root directory of the Hermes ecosystem
    """
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser()
    
    # Check if HERMES_HOME is a profile directory (has parent named "profiles")
    if hermes_home.parent.name == "profiles":
        # Profile mode: ~/.hermes/profiles/<name> → root is ~/.hermes/
        return hermes_home.parent.parent
    else:
        # Direct mode: ~/.hermes → root is ~/.hermes/
        return hermes_home


def get_agora_dir() -> Path:
    """Get the Agora plugin directory: $HERMES_ROOT/agora/"""
    return get_hermes_root() / "agora"


def get_agora_plugin_dir() -> Path:
    """Get the Agora plugin code directory: $HERMES_ROOT/agora/plugin/"""
    return get_agora_dir() / "plugin"


def get_inbox_dir() -> Path:
    """Get the Agora inbox directory: $HERMES_ROOT/agora/inbox/"""
    return get_agora_dir() / "inbox"


def get_ipc_dir() -> Path:
    """Get the Agora IPC directory: $HERMES_ROOT/agora/ipc/"""
    return get_agora_dir() / "ipc"


def get_cards_dir() -> Path:
    """Get the Agora cards directory: $HERMES_ROOT/agora/plugin/cards/"""
    return get_agora_plugin_dir() / "cards"


def get_conversations_log() -> Path:
    """Get the conversations log path: $HERMES_ROOT/agora/conversations.log"""
    return get_agora_dir() / "conversations.log"
