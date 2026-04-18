# Agora — Diseño y decisiones de arquitectura

## Contexto

Hermes necesita delegar trabajo a sub-agentes (Ariadna, Hefesto) sin:
- Hacer polling con sleep (consume tokens, es frágil)
- Depender de que el modelo worker recuerde llamar una tool de notificación
- Introducir dependencias externas (HTTP servers, brokers, bases de datos)
- **Bloquear al orchestrator mientras espera respuesta**

La solución es un canal IPC local async basado en un inbox JSON con escritura atómica
y un registry de sesiones (patrón ProcessRegistry del SDK).

---

## Decisiones de diseño

### 1. Tool única con parámetro `action`

**Decisión:** Una sola tool `talk_to` con `action` enum en lugar de tools separadas.

**Por qué:** El LLM maneja mejor un único nombre de tool. Las acciones le dan estructura
sin multiplicar las definiciones en su contexto. La SKILL.md enseña el flujo correcto.

**Acciones:**
| action | Parámetros | Bloquea? | Qué hace |
|-------|-----------|----------|----------|
| `discover` | agent | No | Lista agentes disponibles (lee cards) |
| `open` | agent | No | Valida card, crea sesión tmux, lanza agente, crea inbox |
| `message` | agent, prompt, session_id | No | Envía prompt via tmux, registra sent_at, retorna inmediatamente |
| `poll` | session_id | No | Consulta estado, progreso, y respuesta si llegó |
| `wait` | session_id, timeout | Sí (con timeout) | Bloquea hasta respuesta o timeout |
| `cancel` | session_id | No | Aborta sesión |
| `close` | session_id | No | Cierra canal, limpia registry |

### 2. Async por defecto — patrón AgoraRegistry

**Decisión:** `message` no bloquea. Retorna inmediatamente con `status: "sent"` y un `session_id`.
El LLM consulta el estado con `poll` o espera con `wait`.

**Por qué:** El modelo anterior (bloqueante por 300s) secuestraba al agente Hermes. No podía
hablar con Hefesto mientras Ariadna trabajaba. El patrón async es el mismo que
`process_registry` usa para procesos en background: lanza, consulta, espera si quieres.

**Flujo:**
```
Hermes: talk_to(agent="ariadna", action="open")
→ {"session_id": "agora_abc123", "agent": "ariadna", "status": "open"}

Hermes: talk_to(agent="ariadna", action="message", session_id="agora_abc123", prompt="...")
→ {"session_id": "agora_abc123", "status": "sent"}  ← INMEDIATO

Hermes: (hace otras cosas — puede hablar con Hefesto, ejecutar tools, etc.)

[SYSTEM: Agora — ariadna terminó. Usa poll para ver la respuesta.]

Hermes: talk_to(action="poll", session_id="agora_abc123")
→ {"status": "done", "response": "...", "elapsed_seconds": 34}

Hermes: talk_to(action="close", session_id="agora_abc123")
→ {"status": "closed"}
```

### 3. AgoraRegistry — Estado persistente entre tool calls

**Decisión:** Singleton de módulo `agora_registry` (como `process_registry`) que mantiene
sesiones, locks, y el estado de cada comunicación.

**Por qué:** El SDK ya usa este patrón para procesos en background. Cada llamada a `talk_to`
no destruye ni recrea nada — el registry existe en memoria por toda la vida del proceso.

**Componentes:**
- `AgoraSession` dataclass: id, agent, status, inbox_path, tmux_target, sent_at, response, output_buffer
- `AgoraRegistry` class: sessions dict, thread-safe methods
- Sin threads daemon — la detección es por polling con timestamp gating

### 4. Inbox JSON con escritura atómica

**Decisión:** El worker escribe la respuesta a un archivo JSON usando el patrón tmp + rename.
El orchestrator lee el archivo y compara `written_at > sent_at` para detectar completitud.

**Por qué:** Elimina completamente los race conditions de los FIFOs (EOF prematuro, pipe
cerrado, lecturas parciales). La escritura atómica garantiza que el lector nunca vea datos
a medio escribir. El timestamp gating resuelve el problema de respuestas tardías.

**Formato del inbox:**
```json
{
  "written_at": 1713312000.123,
  "response": "Contenido de la respuesta...",
  "profile_name": "ariadna"
}
```

**Escritura atómica:**
```python
fd, tmp_path = tempfile.mkstemp(dir=inbox_path.parent, suffix=".tmp")
with os.fdopen(fd, 'w') as f:
    json.dump(inbox_data, f)
os.replace(tmp_path, inbox_path)  # atómico en POSIX
```

### 5. Timestamp gating para detección de completitud

**Decisión:** `sent_at` se registra cuando se envía el mensaje. `poll()` y `wait()` leen
el inbox y comparan `inbox.written_at > session.sent_at`.

**Por qué:** Sin este gate, una respuesta tardía de un mensaje anterior podría ser
interpretada como la respuesta del mensaje actual. El timestamp garantiza que solo
se aceptan respuestas posteriores al envío.

### 6. Observación de progreso via tmux capture-pane

**Decisión:** `poll` captura las últimas 5 líneas del pane tmux del agente worker
para dar visibilidad del progreso.

**Por qué:** Sin progreso visible, `poll` solo retorna "working" — el LLM no tiene
información para decidir si seguir esperando o cancelar. Las líneas del pane muestran
qué tools está llamando el agente.

**Implementación:** `tmux capture-pane -t {target} -p -S -20` + strip ANSI + últimos 5 líneas.

### 7. post_llm_call hook simplificado en el worker

**Decisión:** El worker solo usa el hook `post_llm_call` (v5 eliminó pre_llm_call,
on_session_end, y el watchdog thread). El hook escribe directamente al inbox JSON.

**Por qué:** Sin threads de reader ni FIFOs, el worker es mucho más simple.
Solo necesita escribir al inbox cuando el LLM responde.

### 8. AGENT_CARD centralizado (sin cambios)

**Decisión:** Sin cambios en el formato de cards.

### 9. Envío al worker via tmux send-keys (sin cambios)

**Decisión:** Sin cambios. tmux send-keys sigue siendo el mecanismo de input.

### 10. Sesiones tmux auto-gestionadas (sin cambios)

**Decisión:** Sin cambios. La sesión `agora` se crea on-demand. Los panes persisten
después de close para observabilidad.

---

## Flujo completo (v5)

```
Hermes LLM
  │
  └─ talk_to(agent="ariadna", action="open")
        │ lee AGENT_CARD.yaml de ariadna ──→ valida existencia y available
        │ _ensure_agent_running() ──────────→ lanza en tmux si no corre
        │ crea inbox JSON vacío en ariadna.json
        │ agora_registry.create_session() ─→ session_id: agora_abc123
        └─ retorna: {"session_id": "agora_abc123", "agent": "ariadna", "status": "open"}

  └─ talk_to(agent="ariadna", action="message", session_id="agora_abc123", prompt="...")
        │ tmux send-keys -t agora:2 "Dame estado del proyecto X" Enter
        │ session.sent_at = time.time()
        │ session.status = "sent"
        └─ retorna: {"session_id": "agora_abc123", "agent": "ariadna", "status": "sent"}

        │     [Ariadna trabaja: LLM razona, llama tools, itera]
        │     [on_response_complete → escribe inbox JSON atómico (tmp + rename)]
        │
        │  [Hermes hace poll o wait para verificar]

  └─ talk_to(action="poll", session_id="agora_abc123")
        │ lee inbox JSON → json.loads(inbox_path.read_text())
        │ inbox.written_at > session.sent_at? → SÍ
        │ tmux capture-pane ──→ últimas líneas de actividad
        └─ retorna: {"status": "done", "response": "...", "elapsed_seconds": 34}

  └─ talk_to(action="close", session_id="agora_abc123")
        │ agora_registry.close_session()
        └─ retorna: {"status": "closed"}
```

---

## Lo que NO es Agora

- **No es un broker de mensajes.** No hay colas persistentes, no hay reintentos automáticos.
- **No es un sistema distribuido.** Todo corre en el mismo host, en el mismo usuario.
- **No es un reemplazo de delegate_task.** Agora es para agentes con identidad y sesión
  propia. delegate_task es para sub-tareas efímeras sin identidad.
- **No depende de layouts tmux externos.** Crea y gestiona su propia sesión `agora`
  de forma automática.

---

## Catálogo de errores

| Error | Cuándo se produce | Acción sugerida |
|-------|-------------------|-----------------|
| `TmuxNotAvailable` | El binario `tmux` no está instalado | Instalar tmux |
| `AgentNotReachable` | El agente falló al iniciar | Verificar `launch_command` en la card |
| `AgentNotFound` | No existe card para ese nombre | Usar `discover` para ver agentes |
| `AgentNotAvailable` | Card tiene `available: false` | Agente deliberadamente fuera de servicio |
| `SelfTalkRejected` | Se intentó abrir canal hacia uno mismo | Hablar con otro agente |
| `SessionNotFound` | session_id no existe en el registry | Verificar el ID o hacer `open` primero |
| `SessionAgentMismatch` | session_id no pertenece al agent indicado | Usar el agent correcto |
| `InboxNotReady` | El inbox JSON no existe o está vacío | Re-abrir el canal con `open` |
| `Timeout` | `wait` expiró sin recibir respuesta | Verificar estado del worker, usar `poll` |

---

## Pendientes para versiones futuras

- Multi-turno: reenviar mensaje en la misma sesión sin re-abrir
- Comunicación Ariadna → Hefesto con la misma arquitectura
- Timeout configurable por sesión
- Reconexión پس orchestrator restart (pane_map persistente)
