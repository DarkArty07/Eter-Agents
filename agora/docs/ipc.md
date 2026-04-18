# Agora — Mecanismo IPC v5: Async con Inbox JSON

## Por qué Inbox JSON

El canal de comunicación entre el orchestrator y los workers necesita:
- Ser persistentes y debuggeables (`cat inbox/hefesto.json`)
- Funcionar entre dos procesos Python separados en el mismo host
- No requerir servicios externos
- Eliminar race conditions y threads innecesarios

Un archivo JSON escrito atómicamente (tmp + rename) cumple las cuatro.

---

## Por qué Async

El modelo v1-v3 era bloqueante: `message` retenía al agente Hermes hasta 300s.

Problemas:
- Hermes queda secuestrado — no puede hablar con otros agentes
- Timeout de 300s es demasiado largo si algo falla
- El watchdog de 90s solo ayuda si el LLM falla, no si tarda

v4 cambió a async: `message` retorna inmediatamente con un `session_id`.
v5 mantiene el modelo async pero elimina la complejidad de FIFOs.

---

## Ubicación y naming

```
~/.hermes/agora/inbox/
└── {agent_name}.json     # ej: ariadna.json, hefesto.json
```

- El directorio `inbox/` es compartido, accesible por todos los profiles
- El nombre del archivo es el nombre del agente worker (quien escribe)
- El orchestrator lee; el worker escribe

---

## Formato del inbox JSON

```json
{
  "written_at": 1713312000.123,
  "response": "Contenido de la respuesta del worker...",
  "profile_name": "ariadna"
}
```

- `written_at`: timestamp de cuando se escribió (gate de completitud)
- `response`: texto completo de la respuesta
- `profile_name`: nombre del perfil que escribió

---

## AgoraRegistry

Singleton de módulo que mantiene estado entre llamadas a `talk_to`:

```python
class AgoraSession:
    id: str                    # "agora_<uuid12>"
    agent: str                 # "ariadna"
    status: str                # open | sent | working | done | error | cancelled | closed
    inbox_path: Path           # ~/.hermes/agora/inbox/ariadna.json
    tmux_target: str           # "agora:2"
    prompt: str                # último prompt enviado
    response: str              # respuesta del worker
    output_buffer: str         # rolling buffer de pane activity
    sent_at: float             # timestamp de cuando se envió el mensaje
    last_polled_at: float      # timestamp del último poll
    started_at: float
    response_at: float
    _lock: Lock

class AgoraRegistry:
    _sessions: Dict[str, AgoraSession]
    _lock: Lock

    create_session(agent, inbox_path, tmux_target) -> AgoraSession
    get(session_id) -> AgoraSession | None
    get_by_agent(agent) -> AgoraSession | None
    poll(session_id) -> dict
    wait(session_id, timeout) -> dict
    cancel(session_id) -> dict
    close_session(session_id) -> dict
    _capture_pane_activity(session) -> str
```

---

## Ciclo de vida del inbox

```
talk_to(action="open")
  → _ensure_agent_running() ──────────→ lanza en tmux si no corre
  → crea archivo inbox en ~/.hermes/agora/inbox/ariadna.json
  → agora_registry.create_session() ──→ session_id: agora_abc123
  → retorna: {"session_id": "agora_abc123", "status": "open"}

talk_to(action="message", session_id="agora_abc123", prompt="...")
  → tmux send-keys -t agora:2 "Dame estado" Enter
  → session.sent_at = time.time()
  → session.status = "sent"
  → retorna INMEDIATAMENTE: {"session_id": "agora_abc123", "status": "sent"}

  [worker trabaja: LLM razona, llama tools, itera]
  [on_response_complete → escribe inbox JSON atómico: tmp + rename]

talk_to(action="poll", session_id="agora_abc123")
  → lee inbox JSON
  → inbox.written_at > session.sent_at?
    → SÍ: session.status = "done", session.response = inbox.response
          retorna: {"status": "done", "response": "...", "elapsed_seconds": 34}
    → NO:  activity = _capture_pane_activity(session)
          retorna: {"status": "working", "activity": "┊ search_files(...)", "elapsed": 12}

talk_to(action="wait", session_id="agora_abc123", timeout=60)
  → while time.time() < deadline:
  →     lee inbox JSON
  →     if inbox.written_at > session.sent_at: return response
  →     sleep(1)
  → retorna: {"status": "timeout"} si expira

talk_to(action="cancel", session_id="agora_abc123")
  → session.status = "cancelled"
  → retorna: {"status": "cancelled"}

talk_to(action="close", session_id="agora_abc123")
  → agora_registry.close_session(session_id)
  → retorna: {"status": "closed"}
```

---

## Escritura atómica del inbox

El worker escribe la respuesta usando el patrón tmp + rename:

```python
import json
import os
import tempfile

def _on_response_complete(session, response):
    inbox_data = {
        "written_at": time.time(),
        "response": response,
        "profile_name": session.agent,
    }
    inbox_path = session.inbox_path
    # Escribir a archivo temporal en el mismo directorio
    fd, tmp_path = tempfile.mkstemp(dir=inbox_path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(inbox_data, f)
        # Rename atómico — garantiza que el lector nunca vea datos parciales
        os.replace(tmp_path, inbox_path)
    except:
        os.unlink(tmp_path)
        raise
```

Esto garantiza que el orchestrator nunca lee un JSON a medio escribir.

---

## Detección de completitud: timestamp gating

La clave del sistema v5 es comparar timestamps:

```python
# En poll() y wait():
inbox = json.loads(inbox_path.read_text())
if inbox["written_at"] > session.sent_at:
    # La respuesta es posterior al mensaje enviado → es nuestra respuesta
    session.status = "done"
    session.response = inbox["response"]
```

Esto resuelve el problema de respuestas tardías: si un mensaje anterior llega tarde,
su `written_at` será menor que `sent_at` del mensaje actual, y se ignora correctamente.

---

## Watchdog del worker

El worker mantiene un watchdog que protege contra LLM failures.
Si el LLM falla (HTTP 400/404/503, credenciales inválidas, etc.),
el hook `post_llm_call` no se dispara. El watchdog escribe un error al inbox.

```
[pre_llm_call] → watchdog.start(timeout=90s)
    │
    ├─ [post_llm_call dispara] → watchdog se cancela
    │
    └─ [timeout 90s] → watchdog escribe error al inbox JSON
       → poll() detecta written_at > sent_at → session.status = "error"
```

---

## Observación de progreso

`poll` captura las últimas 5 líneas del pane tmux del agente worker:

```python
result = subprocess.run(
    ["tmux", "capture-pane", "-t", target, "-p", "-S", "-20"],
    capture_output=True, text=True, timeout=5
)
# Strip ANSI, tomar últimas 5 líneas con contenido
```

Esto permite que Hermes vea qué tools está llamando el agente mientras trabaja.

---

## Ventajas de v5 sobre v4

| Aspecto | v4 (FIFO) | v5 (Inbox JSON) |
|---------|-----------|-----------------|
| Threads por sesión | 2 (reader + watchdog) | 0 |
| Race conditions | 4+ (EOF, pipe closed, partial reads) | 0 (atomic write) |
| Debuggeable | No (pipe binario) | Sí (`cat inbox/hefesto.json`) |
| Respuestas tardías | Se pierden o causan errores | Manejadas por timestamp gating |
| Código total | ~1315 líneas | ~967 líneas (-26%) |
| Complejidad | select(), O_NONBLOCK, fd management | json.load(), compare timestamps |

---

## Limitaciones conocidas

| Limitación | Impacto | Estado |
|------------|---------|--------|
| Solo mismo host | No funciona en red | Por diseño |
| `message` es async | El LLM debe hacer `poll` o `wait` para obtener la respuesta | Por diseño |
| Archivo inbox se sobrescribe | Solo la última respuesta persiste | Por diseño (timestamp gating resuelve ambigüedad) |
| Pane tmux persiste después de close | Observabilidad a costo de memoria | Por diseño |
| Gateway mode no recibe notificaciones automáticas | Solo CLI | Pendiente futuro |
