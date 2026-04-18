"""
Agora — Session Registry for async IPC.

Patrón singleton (como ProcessRegistry del SDK):
- Mantiene estado entre llamadas a talk_to
- Polling de inbox JSON para respuestas
- Thread-safe con locks

Acciones soportadas por el registry:
  poll, wait, cancel, close, cleanup
"""

import json
import logging
import os
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from ._convo_log import log_received, log_system
from ._paths import get_ipc_dir

logger = logging.getLogger(__name__)

IPC_DIR = get_ipc_dir()

# Limits
MAX_OUTPUT_CHARS = 50_000        # Rolling buffer for pane activity
FINISHED_TTL_SECONDS = 1800     # Keep finished sessions for 30 minutes
MAX_SESSIONS = 16               # Max concurrent sessions


@dataclass
class AgoraSession:
    """A tracked Agora IPC session with inbox polling."""
    id: str                                    # "agora_<uuid12>"
    agent: str                                 # "ariadna", "hefesto"
    status: str                                # "open" | "sent" | "working" | "done" | "error" | "cancelled" | "closed"
    inbox_path: Path                           # ~/.hermes/agora/ipc/<agent>.json
    tmux_target: str                           # "agora:2"
    prompt: str = ""                            # Last prompt sent
    response: str = ""                          # Worker response (empty until done)
    output_buffer: str = ""                     # Rolling pane activity buffer
    started_at: float = 0.0                     # time.time() of session creation
    response_at: Optional[float] = None         # time.time() when response arrived
    sent_at: float = 0.0                        # timestamp when message was sent
    last_polled_at: Optional[float] = None      # last poll timestamp
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class AgoraRegistry:
    """
    In-memory registry of Agora IPC sessions.

    Thread-safe. Accessed from:
      - Orchestrator tool handlers (talk_to actions)
      - Inbox polling for responses
    """

    def __init__(self):
        self._sessions: Dict[str, AgoraSession] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------------------
    # Session lifecycle
    # ---------------------------------------------------------------------------

    def create_session(self, agent: str, inbox_path: Path, tmux_target: str) -> AgoraSession:
        """Create a new session."""
        session = AgoraSession(
            id=f"agora_{uuid.uuid4().hex[:12]}",
            agent=agent,
            status="open",
            inbox_path=inbox_path,
            tmux_target=tmux_target,
            started_at=time.time(),
            sent_at=0.0,
        )

        with self._lock:
            self._prune_if_needed()
            self._sessions[session.id] = session

        logger.info("agora: session created: %s for agent %s", session.id, agent)
        return session

    def get(self, session_id: str) -> Optional[AgoraSession]:
        """Get a session by ID."""
        with self._lock:
            return self._sessions.get(session_id)

    def get_by_agent(self, agent: str) -> Optional[AgoraSession]:
        """Get the active (non-finished) session for an agent."""
        with self._lock:
            for session in self._sessions.values():
                if session.agent == agent and session.status in ("open", "sent", "working"):
                    return session
        return None

    # ---------------------------------------------------------------------------
    # Actions
    # ---------------------------------------------------------------------------

    def poll(self, session_id: str) -> dict:
        """Check session status, capture pane activity, read inbox if available."""
        session = self.get(session_id)
        if session is None:
            return {"error": "SessionNotFound", "session_id": session_id}

        # Capture pane activity OUTSIDE the lock (subprocess can take up to 5s)
        activity = ""
        with session._lock:
            status = session.status

        if status in ("sent", "working"):
            activity = self._capture_pane_activity(session)

        # Check inbox for new response
        with session._lock:
            if session.inbox_path.exists():
                try:
                    with open(session.inbox_path, "r") as f:
                        data = json.load(f)
                    written_at = data.get("written_at", 0)
                    if written_at > session.sent_at:
                        # New response found
                        session.sent_at = written_at
                        resp_status = data.get("status", "done")
                        resp_text = data.get("response", "")
                        if resp_status == "done":
                            session.status = "done"
                            session.response = resp_text
                            session.response_at = time.time()
                        elif resp_status == "error":
                            session.status = "error"
                            session.response = resp_text
                except (json.JSONDecodeError, OSError, KeyError) as exc:
                    logger.debug("agora: error reading inbox for %s: %s", session.id, exc)

            session.last_polled_at = time.time()
            elapsed = int(time.time() - session.started_at)
            result = {
                "session_id": session.id,
                "agent": session.agent,
                "status": session.status,
                "elapsed_seconds": elapsed,
            }

            # Include activity if captured
            if activity and session.status in ("sent", "working"):
                result["activity"] = activity
                result["hint"] = f"{session.agent} está trabajando"

            # Include response if done
            if session.status == "done":
                result["response"] = session.response
                log_received(session.agent, session.id, session.response)
            elif session.status == "error":
                result["response"] = session.response
                result["hint"] = f"{session.agent} reportó un error"
                log_system(session.agent, session.id, f"ERROR: {session.response[:100]}")

        return result

    def wait(self, session_id: str, timeout: int = 120) -> dict:
        """Block until session is done/error/cancelled or timeout expires using inbox polling."""
        max_timeout = 300
        if timeout > max_timeout:
            timeout = max_timeout

        session = self.get(session_id)
        if session is None:
            return {"error": "SessionNotFound", "session_id": session_id}

        deadline = time.time() + timeout

        while time.time() < deadline:
            session = self.get(session_id)
            if session is None:
                return {"error": "SessionNotFound", "session_id": session_id}

            # Check inbox for new response
            if session.inbox_path.exists():
                try:
                    with open(session.inbox_path, "r") as f:
                        data = json.load(f)
                    written_at = data.get("written_at", 0)
                    if written_at > session.sent_at:
                        # New response found
                        with session._lock:
                            session.sent_at = written_at
                            resp_status = data.get("status", "done")
                            resp_text = data.get("response", "")
                            if resp_status == "done":
                                session.status = "done"
                                session.response = resp_text
                                session.response_at = time.time()
                            elif resp_status == "error":
                                session.status = "error"
                                session.response = resp_text
                except (json.JSONDecodeError, OSError, KeyError) as exc:
                    logger.debug("agora: error reading inbox for %s: %s", session.id, exc)

            # Check if session reached terminal state
            if session.status in ("done", "error", "cancelled", "closed"):
                with session._lock:
                    if session.status == "done":
                        log_received(session.agent, session_id, session.response)
                    elif session.status == "error":
                        log_system(session.agent, session_id, f"ERROR: {session.response[:100]}")
                    return {
                        "session_id": session.id,
                        "agent": session.agent,
                        "status": session.status,
                        "response": session.response,
                        "elapsed_seconds": int(time.time() - session.started_at),
                    }

            time.sleep(1)

        # Timeout
        session = self.get(session_id)
        if session is None:
            return {"error": "SessionNotFound", "session_id": session_id}

        log_system(session.agent, session_id, f"TIMEOUT tras {timeout}s — sin respuesta")

        with session._lock:
            return {
                "session_id": session.id,
                "agent": session.agent,
                "status": "timeout",
                "elapsed_seconds": int(time.time() - session.started_at),
                "hint": f"Esperando respuesta de {session.agent} tras {timeout}s",
            }

    def cancel(self, session_id: str) -> dict:
        """Cancel a session."""
        session = self.get(session_id)
        if session is None:
            return {"error": "SessionNotFound", "session_id": session_id}

        with session._lock:
            session.status = "cancelled"

        logger.info("agora: session cancelled: %s", session_id)
        log_system(session.agent, session_id, "sesión cancelada")
        return {"session_id": session.id, "agent": session.agent, "status": "cancelled"}

    def close_session(self, session_id: str) -> dict:
        """Close a session and remove from registry."""
        session = self.get(session_id)
        if session is None:
            return {"error": "SessionNotFound", "session_id": session_id}

        with session._lock:
            session.status = "closed"

        # Remove from registry
        with self._lock:
            self._sessions.pop(session_id, None)

        logger.info("agora: session closed: %s", session_id)
        log_system(session.agent, session_id, "sesión cerrada")
        return {"session_id": session.id, "agent": session.agent, "status": "closed"}

    # ---------------------------------------------------------------------------
    # Pane activity capture
    # ---------------------------------------------------------------------------

    def _capture_pane_activity(self, session: AgoraSession) -> str:
        """Capture recent activity from the agent's tmux pane."""
        try:
            result = subprocess.run(
                ["tmux", "capture-pane", "-t", session.tmux_target, "-p", "-S", "-20"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return ""

            lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
            # Take last 5 lines with content
            relevant = lines[-5:] if len(lines) > 5 else lines

            # Basic ANSI stripping
            import re
            activity = "\n".join(relevant)
            activity = re.sub(r'\x1b\[[0-9;]*m', '', activity)  # Remove ANSI escape codes

            # Update rolling buffer — caller (poll) already holds session._lock,
            # do NOT acquire it here or we deadlock (threading.Lock is not reentrant)
            session.output_buffer += activity + "\n"
            if len(session.output_buffer) > MAX_OUTPUT_CHARS:
                session.output_buffer = session.output_buffer[-MAX_OUTPUT_CHARS:]

            return activity

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.debug("agora: pane capture failed for %s: %s", session.agent, exc)
            return ""

    # ---------------------------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------------------------

    def _prune_if_needed(self) -> None:
        """Remove old finished sessions if we're at the limit."""
        if len(self._sessions) < MAX_SESSIONS:
            return

        # Remove oldest finished sessions first
        finished = [
            (sid, s) for sid, s in self._sessions.items()
            if s.status in ("done", "error", "cancelled", "closed")
        ]
        finished.sort(key=lambda x: x[1].started_at)

        for sid, _ in finished:
            self._sessions.pop(sid, None)
            if len(self._sessions) < MAX_SESSIONS:
                break

    def cleanup_old_sessions(self) -> None:
        """Remove sessions older than FINISHED_TTL_SECONDS."""
        now = time.time()
        with self._lock:
            to_remove = []
            for sid, session in self._sessions.items():
                if session.status in ("done", "error", "cancelled", "closed"):
                    if session.response_at and (now - session.response_at) > FINISHED_TTL_SECONDS:
                        to_remove.append(sid)
                    elif not session.response_at and (now - session.started_at) > FINISHED_TTL_SECONDS:
                        to_remove.append(sid)
            for sid in to_remove:
                self._sessions.pop(sid, None)

    def list_sessions(self) -> list:
        """List all sessions (for debugging)."""
        with self._lock:
            return [
                {
                    "id": s.id,
                    "agent": s.agent,
                    "status": s.status,
                    "started_at": s.started_at,
                    "elapsed": int(time.time() - s.started_at),
                }
                for s in self._sessions.values()
            ]


# Singleton instance
agora_registry = AgoraRegistry()