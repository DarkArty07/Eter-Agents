"""
Agora — Lado orchestrator (Hermes).

Registra la tool talk_to con siete acciones:
  discover  — lista agentes disponibles desde CARDS_DIR
  open      — crea sesión, lanza agente, crea inbox JSON
  message   — envía prompt via tmux, retorna inmediatamente (async)
  poll      — consulta estado, progreso, y respuesta si llegó
  wait      — bloquea hasta respuesta o timeout
  cancel    — aborta sesión y limpia
  close     — cierra canal y limpia

Arquitectura async: message no bloquea. Polling del inbox JSON para respuestas.
"""

import json
import logging
import subprocess
import os
import time
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

from ._registry import agora_registry, AgoraSession
from ._convo_log import log_sent, log_received, log_system
from ._paths import get_inbox_dir, get_cards_dir

logger = logging.getLogger(__name__)

INBOX_DIR = get_inbox_dir()
CARDS_DIR = get_cards_dir()

# defaults
_DEFAULT_WAIT_TIMEOUT = 120
_MAX_WAIT_TIMEOUT = 300

# ---------------------------------------------------------------------------
# Self-managed tmux state
# ---------------------------------------------------------------------------

_SESSION_NAME = "agora"
_pane_map: dict[str, str] = {}  # agent_name → tmux target (e.g. "agora:2")


# ---------------------------------------------------------------------------
# Schema OpenAI para la tool talk_to
# ---------------------------------------------------------------------------

TALK_TO_SCHEMA = {
    "name": "talk_to",
    "description": (
        "Canal de comunicación con sub-agentes. Flujo: discover → open → message → poll/wait → close. "
        "Message es async por defecto — usa poll para consultar progreso o wait para bloquear."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "agent": {
                "type": "string",
                "description": "Nombre del agente o '?' para discover",
            },
            "action": {
                "type": "string",
                "enum": ["discover", "open", "message", "poll", "wait", "cancel", "close"],
                "description": (
                    "Acción a ejecutar. "
                    "discover: lista agentes. open: crea canal. message: envía prompt (async). "
                    "poll: consulta estado. wait: bloquea hasta respuesta. "
                    "cancel: aborta sesión. close: cierra canal."
                ),
            },
            "prompt": {
                "type": "string",
                "description": "Mensaje. Solo con action=message",
            },
            "session_id": {
                "type": "string",
                "description": "ID de sesión (retornado por open). Requerido para poll, wait, cancel, close. Opcional para message.",
            },
            "timeout": {
                "type": "integer",
                "description": f"Timeout en segundos para wait. Default {_DEFAULT_WAIT_TIMEOUT}s, max {_MAX_WAIT_TIMEOUT}s.",
                "minimum": 1,
            },
        },
        "required": ["agent", "action"],
    },
}


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------


def register(ctx, timeout_seconds: int = 300):
    ctx.register_tool(
        name="talk_to",
        toolset="agora",
        schema=TALK_TO_SCHEMA,
        handler=_handle_talk_to,
    )


# ---------------------------------------------------------------------------
# Handler principal
# ---------------------------------------------------------------------------


def _handle_talk_to(args: dict, **kwargs) -> str:
    agent = args.get("agent", "").strip()
    action = args.get("action", "").strip()
    prompt = args.get("prompt", "")
    session_id = args.get("session_id", "")
    timeout = args.get("timeout", _DEFAULT_WAIT_TIMEOUT)

    if not agent:
        return json.dumps({"error": "Falta el parámetro 'agent'"})
    if not action:
        return json.dumps({"error": "Falta el parámetro 'action'"})

    # Validar self-talk
    hermes_home = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
    current_profile = hermes_home.name
    if action == "open" and agent == current_profile:
        return json.dumps({"error": "SelfTalkRejected", "detail": "No puedes hablar contigo mismo"})

    try:
        if action == "discover":
            return _action_discover(agent)
        elif action == "open":
            return _action_open(agent)
        elif action == "message":
            return _action_message(agent, prompt, session_id)
        elif action == "poll":
            return _action_poll(session_id, agent)
        elif action == "wait":
            return _action_wait(session_id, agent, timeout)
        elif action == "cancel":
            return _action_cancel(session_id, agent)
        elif action == "close":
            return _action_close(session_id, agent)
        else:
            return json.dumps({"error": f"action desconocida: {action}"})
    except Exception as exc:
        logger.exception("agora: error en talk_to(action=%s, agent=%s)", action, agent)
        return json.dumps({"error": str(exc), "action": action, "agent": agent})


# ---------------------------------------------------------------------------
# Helper: leer card
# ---------------------------------------------------------------------------


def _load_card(agent_name: str) -> dict | None:
    card_path = CARDS_DIR / f"{agent_name}.yaml"
    if not card_path.exists():
        return None
    if yaml is None:
        return None
    try:
        return yaml.safe_load(card_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("agora: error leyendo card de %s: %s", agent_name, exc)
        return None


# ---------------------------------------------------------------------------
# action: discover
# ---------------------------------------------------------------------------


def _action_discover(agent: str) -> str:
    if agent == "?":
        agents = []
        try:
            for card_path in sorted(CARDS_DIR.glob("*.yaml")):
                agent_name = card_path.stem
                if yaml is None:
                    continue
                try:
                    card = yaml.safe_load(card_path.read_text(encoding="utf-8")) or {}
                except Exception as exc:
                    logger.warning("agora: error leyendo %s: %s", card_path, exc)
                    continue
                if card.get("available", False):
                    agents.append({
                        "name": card.get("name", agent_name),
                        "role": card.get("role", ""),
                        "description": card.get("description", ""),
                        "capabilities": card.get("capabilities", []),
                        "available": True,
                    })
        except Exception as exc:
            return json.dumps({"error": f"Error escaneando cards: {exc}"})
        return json.dumps({"agents": agents, "count": len(agents)})
    else:
        card = _load_card(agent)
        if card is None:
            return json.dumps({"error": "AgentNotFound", "agent": agent})
        return json.dumps({
            "name": card.get("name", agent),
            "role": card.get("role", ""),
            "description": card.get("description", ""),
            "capabilities": card.get("capabilities", []),
            "available": card.get("available", False),
        })


# ---------------------------------------------------------------------------
# Tmux helpers: self-managed session
# ---------------------------------------------------------------------------


def _check_tmux_available() -> bool:
    """Verifica que el binario tmux esté instalado."""
    try:
        result = subprocess.run(
            ["tmux", "-V"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _ensure_session() -> str | None:
    """Ensure the 'agora' tmux session exists, creating it on demand."""
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", _SESSION_NAME],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return _SESSION_NAME
        result = subprocess.run(
            ["tmux", "new-session", "-d", "-s", _SESSION_NAME],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            logger.info("agora: sesión tmux '%s' creada", _SESSION_NAME)
            return _SESSION_NAME
        logger.warning("agora: no se pudo crear sesión '%s': %s",
                        _SESSION_NAME, result.stderr.strip())
        return None
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None


def _ensure_pane_for_agent(agent: str) -> str | None:
    """Get or create a window (pane) for the agent in the 'agora' session."""
    if agent in _pane_map:
        return _pane_map[agent]

    session = _ensure_session()
    if not session:
        return None

    window_name = f"agora-{agent}"

    try:
        # Check existing windows
        result = subprocess.run(
            ["tmux", "list-windows", "-t", session, "-F",
             "#{window_index} #{window_name}"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                parts = line.split(" ", 1)
                idx = parts[0]
                name = parts[1] if len(parts) > 1 else ""
                if name == window_name:
                    target = f"{session}:{idx}"
                    _pane_map[agent] = target
                    logger.info("agora: pane existente para '%s' → %s", agent, target)
                    return target

        # Create a new window
        result = subprocess.run(
            ["tmux", "new-window", "-t", session, "-n", window_name,
             "-P", "-F", "#{window_index}"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            logger.warning("agora: no se pudo crear window para '%s': %s",
                           agent, result.stderr.strip())
            return None
        window_index = result.stdout.strip()
        if not window_index:
            logger.warning("agora: no se recibió window_index para '%s'", agent)
            return None
        target = f"{session}:{window_index}"
        _pane_map[agent] = target
        logger.info("agora: pane creado para '%s' → %s", agent, target)
        return target
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("agora: error creando pane para '%s': %s", agent, exc)
        return None


def _ensure_agent_running(card: dict) -> bool:
    """Verifica si el agente corre en su pane. Si no, lo lanza."""
    agent = card.get("name", "")
    launch_cmd = card.get("launch_command", "")

    target = _ensure_pane_for_agent(agent)
    if not target:
        return False

    if not launch_cmd:
        logger.info("agora: sin launch_command para '%s', pane listo", agent)
        return True

    try:
        proc_result = subprocess.run(
            ["tmux", "display-message", "-t", target, "-p", "#{pane_current_command}"],
            capture_output=True, text=True, timeout=5
        )

        if proc_result.returncode != 0:
            logger.warning("agora: tmux display-message failed (rc=%d): %s",
                           proc_result.returncode, proc_result.stderr.strip())
            return False

        current_cmd = proc_result.stdout.strip().lower()
        logger.debug("agora: pane_current_command para '%s': '%s'", agent, current_cmd)

        agent_processes = {"hermes", "python", "python3"}
        shell_processes = {"bash", "sh", "zsh", "fish", ""}

        is_running = current_cmd in agent_processes or (
            current_cmd not in shell_processes and current_cmd != ""
        )

        if is_running:
            logger.info("agora: agente '%s' confirmado corriendo (cmd=%s)", agent, current_cmd)
            return True

        # Launch the agent
        logger.info("agora: lanzando agente '%s' en %s (cmd=%s)", agent, target, current_cmd)
        subprocess.run(
            ["tmux", "send-keys", "-t", target, launch_cmd, "Enter"],
            timeout=5
        )

        # Wait for startup with polling — two phases:
        # Phase 1: process appears (up to 12s)
        # Phase 2: framework ready — detect prompt in pane output (up to 30s)
        startup_deadline = time.time() + 12
        verify_cmd = ""
        while time.time() < startup_deadline:
            time.sleep(1)
            verify = subprocess.run(
                ["tmux", "display-message", "-t", target, "-p", "#{pane_current_command}"],
                capture_output=True, text=True, timeout=5
            )
            if verify.returncode != 0:
                return False
            verify_cmd = verify.stdout.strip().lower()
            if verify_cmd in agent_processes:
                logger.info("agora: agente '%s' proceso detectado (cmd=%s), esperando framework...", agent, verify_cmd)
                break

        if verify_cmd not in agent_processes:
            logger.warning("agora: agente lanzado pero proceso no detectado tras espera (cmd=%s)", verify_cmd)
            return False

        # Phase 2: Wait for framework ready prompt in pane output
        # Hermes prints various ready indicators depending on config:
        #   - "◈" (skin prompt character)
        #   - "Ready." or "ready" 
        #   - A prompt line waiting for input (prompt char at end of last line)
        ready_deadline = time.time() + 30
        ready_patterns = ["◈", "ready", "◆", "▸", "❯", "⟩"]
        while time.time() < ready_deadline:
            time.sleep(2)
            try:
                capture = subprocess.run(
                    ["tmux", "capture-pane", "-t", target, "-p", "-S", "-50"],
                    capture_output=True, text=True, timeout=5
                )
                if capture.returncode == 0:
                    pane_output = capture.stdout.lower()
                    for pattern in ready_patterns:
                        if pattern in pane_output:
                            logger.info("agora: framework '%s' listo (detectado '%s' en output)", agent, pattern)
                            # Small extra grace period for first prompt processing
                            time.sleep(1)
                            return True
            except Exception:
                pass

        # If we couldn't detect ready but process is running, assume ready after timeout
        logger.warning("agora: no se detectó ready prompt para '%s', asumiendo listo por timeout", agent)
        return True

    except FileNotFoundError:
        logger.warning("agora: tmux binary not found")
        return False
    except subprocess.TimeoutExpired:
        logger.warning("agora: timeout verificando/lanzando agente")
        return False
    except Exception as exc:
        logger.warning("agora: no se pudo verificar/lanzar agente: %s", exc)
        return False


# ---------------------------------------------------------------------------
# action: open
# ---------------------------------------------------------------------------


def _action_open(agent: str) -> str:
    existing = agora_registry.get_by_agent(agent)
    if existing:
        return json.dumps({
            "error": "SessionAlreadyActive",
            "detail": f"Ya hay una sesión activa con {agent}. Ciérrala antes de abrir una nueva.",
            "session_id": existing.id,
            "status": existing.status,
        })

    card = _load_card(agent)
    if card is None:
        return json.dumps({"error": "AgentNotFound", "agent": agent})
    if not card.get("available", False):
        return json.dumps({"error": "AgentNotAvailable", "agent": agent})

    if not _check_tmux_available():
        return json.dumps({"error": "TmuxNotAvailable", "detail": "tmux is not installed"})

    if not _ensure_agent_running(card):
        return json.dumps({
            "error": "AgentNotReachable",
            "detail": f"No se pudo iniciar o verificar el agente '{agent}'",
            "agent": agent,
        })

    # Create inbox directory
    INBOX_DIR.mkdir(parents=True, exist_ok=True)

    inbox_path = INBOX_DIR / f"{agent}.json"

    # Clean up stale inbox file
    if inbox_path.exists():
        inbox_path.unlink()
        logger.debug("agora: inbox huérfano eliminado: %s", inbox_path)

    # Get tmux target
    tmux_target = _pane_map.get(agent, "")
    if not tmux_target:
        # Try to find it
        tmux_target = _ensure_pane_for_agent(agent) or ""

    # Create session in registry
    session = agora_registry.create_session(
        agent=agent,
        inbox_path=inbox_path,
        tmux_target=tmux_target,
    )

    log_system(agent, session.id, f"sesión abierta — inbox listo")

    return json.dumps({
        "session_id": session.id,
        "agent": agent,
        "status": "open",
        "inbox": str(inbox_path),
    })


# ---------------------------------------------------------------------------
# action: message
# ---------------------------------------------------------------------------


def _action_message(agent: str, prompt: str, session_id: str) -> str:
    if not prompt:
        return json.dumps({"error": "Falta el parámetro 'prompt'", "agent": agent})

    # Find session: by session_id or by agent name
    session = None
    if session_id:
        session = agora_registry.get(session_id)
        if session is None:
            return json.dumps({"error": "SessionNotFound", "session_id": session_id, "agent": agent})
        if session.agent != agent:
            return json.dumps({"error": "SessionAgentMismatch", "session_id": session_id, "expected": session.agent, "got": agent})
    else:
        session = agora_registry.get_by_agent(agent)

    if session is None:
        return json.dumps({
            "error": "CanalNoAbierto",
            "detail": "No hay sesión activa para este agente. Llama action='open' primero.",
            "agent": agent,
        })

    # Verify tmux target
    tmux_target = session.tmux_target or _pane_map.get(agent, "")
    if not tmux_target:
        return json.dumps({
            "error": "CanalNoAbierto",
            "detail": "No hay pane para este agente. Llama action='open' primero.",
            "agent": agent,
        })

    # Update session state
    with session._lock:
        session.prompt = prompt
        session.status = "sent"
        session.sent_at = time.time()

    # Send prompt to worker via tmux
    # Safety check: verify the target pane is actually ready (has a prompt)
    # This prevents the first message from getting stuck when framework
    # hasn't fully initialized yet even though the process exists.
    try:
        capture = subprocess.run(
            ["tmux", "capture-pane", "-t", tmux_target, "-p", "-S", "-5"],
            capture_output=True, text=True, timeout=5
        )
        if capture.returncode == 0:
            last_lines = capture.stdout.strip().lower()
            # If pane output looks like a shell waiting for input or framework prompt, it's ready
            ready_indicators = ["◈", "ready", "◆", "▸", "❯", "⟩", "hermes"]
            is_ready = any(ind in last_lines for ind in ready_indicators)
            if not is_ready:
                # Pane might still be initializing — wait a bit and re-check
                logger.info("agora: pane para '%s' no parece listo, esperando 3s...", agent)
                time.sleep(3)
    except Exception:
        pass  # Non-fatal — proceed with send-keys anyway

    try:
        subprocess.run(
            ["tmux", "send-keys", "-t", tmux_target, prompt, "Enter"],
            timeout=10
        )
    except Exception as exc:
        with session._lock:
            session.status = "error"
            session.response = f"tmux send-keys falló: {exc}"
        log_system(agent, session.id, f"ERROR: tmux send-keys falló — {exc}")
        return json.dumps({"error": f"tmux send-keys falló: {exc}", "agent": agent, "session_id": session.id})

    log_sent(agent, session.id, prompt)

    return json.dumps({
        "session_id": session.id,
        "agent": agent,
        "status": "sent",
    })


# ---------------------------------------------------------------------------
# action: poll
# ---------------------------------------------------------------------------


def _action_poll(session_id: str, agent: str) -> str:
    if not session_id:
        return json.dumps({"error": "Falta el parámetro 'session_id'"})

    result = agora_registry.poll(session_id)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# action: wait
# ---------------------------------------------------------------------------


def _action_wait(session_id: str, agent: str, timeout) -> str:
    if not session_id:
        return json.dumps({"error": "Falta el parámetro 'session_id'"})

    # Ensure timeout is int
    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        timeout = _DEFAULT_WAIT_TIMEOUT

    result = agora_registry.wait(session_id, timeout=timeout)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# action: cancel
# ---------------------------------------------------------------------------


def _action_cancel(session_id: str, agent: str) -> str:
    if not session_id:
        return json.dumps({"error": "Falta el parámetro 'session_id'"})

    result = agora_registry.cancel(session_id)
    return json.dumps(result)


# ---------------------------------------------------------------------------
# action: close
# ---------------------------------------------------------------------------


def _action_close(session_id: str, agent: str) -> str:
    if not session_id:
        return json.dumps({"error": "Falta el parámetro 'session_id'"})

    # Also clean up pane_map for this agent
    # (pane persists in tmux for observability)
    result = agora_registry.close_session(session_id)

    # Clean pane_map if session was for this agent
    if "agent" in result:
        _pane_map.pop(result.get("agent", ""), None)

    return json.dumps(result)