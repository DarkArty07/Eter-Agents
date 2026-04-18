# AGENT_CARD — Formato y especificación

## Qué es un Agent Card

Archivo YAML estático que cada agente publica en el directorio centralizado
`~/.hermes/agora/cards/`. Es la fuente de verdad para el discovery de agentes.

**Regla:** Si no hay card en `~/.hermes/agora/cards/`, el agente no existe para `talk_to`.

---

## Formato

```yaml
name: string              # nombre único — debe coincidir exactamente con el profile
role: string              # rol corto — el LLM lo usa para decidir a quién delegar
description: string       # una línea de qué hace el agente
capabilities:
  - string                # lista de capacidades (el LLM las lee antes de delegar)
launch_command: string    # comando para iniciar el agente en tmux
available: bool           # false = talk_to retorna AgentNotAvailable sin intentar
```

---

## Campos obligatorios

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `name` | string | Debe coincidir exactamente con el nombre del profile |
| `role` | string | Rol corto, usado por el LLM para decidir a quién delegar |
| `description` | string | Una línea. El LLM la usa para decidir si este agente es el correcto |
| `capabilities` | lista | Qué puede hacer. El LLM la lee antes de delegar |
| `launch_command` | string | Comando para iniciar el agente en el pane tmux auto-creado |
| `available` | bool | Si es `false`, `talk_to` retorna `AgentNotAvailable` sin intentar nada |

---

## `launch_command` — reglas

El plugin ejecuta este comando en el pane tmux del agente cuando necesita arrancarlo.

```yaml
# ✅ Correcto — usa el profile específico
launch_command: "hermes -p ariadna"
launch_command: "hermes -p hefesto"
launch_command: "hermes -p mi-agente"

# ❌ Incorrecto — no arranca el profile correcto
launch_command: "ariadna chat"     # comando inexistente
launch_command: "hermes chat"      # abre el profile por defecto
launch_command: "hermes"           # abre el profile por defecto
```

El plugin verifica que el agente arrancó comprobando `pane_current_command`.
Si tras 12 segundos el proceso en el pane no es `python` o `python3`, retorna
`AgentNotReachable`.

---

## Cards actuales

### hermes.yaml
```yaml
name: hermes
version: "1.0.0"
role: orchestrator
description: "Diseñador de sistemas y orquestador. Recibe objetivos del usuario y delega trabajo a sub-agentes."
capabilities:
  - system-design
  - task-orchestration
  - agent-delegation
  - architecture-planning
available: true
```
> Hermes no tiene `launch_command` porque es el orquestador — no se auto-lanza.

### ariadna.yaml
```yaml
name: ariadna
version: "1.0.0"
role: project-manager
description: "Project Manager y auditora. Gestiona estado de proyectos, mantiene contexto entre sesiones."
capabilities:
  - session-management
  - project-state-tracking
  - audit
  - blocker-tracking
  - progress-reporting
launch_command: "hermes -p ariadna"
available: true
```

### hefesto.yaml
```yaml
name: hefesto
version: "1.0.0"
role: technical-orchestrator
description: "Orquestador de implementación via delegate_task. Recibe specs de Hermes y coordina mini-agentes."
capabilities:
  - task-decomposition
  - delegate-task-orchestration
  - code-review
  - parallel-execution
launch_command: "hermes -p hefesto"
available: true
```

---

## Cómo usa `talk_to` el Agent Card

### discover
```
talk_to(agent="ariadna", action="discover")
  → busca ~/.hermes/agora/cards/ariadna.yaml
  → AgentNotFound si no existe
  → retorna el card completo si existe

talk_to(agent="?", action="discover")
  → itera todos los .yaml en ~/.hermes/agora/cards/
  → retorna solo los que tienen available: true
```

### open
```
talk_to(agent="ariadna", action="open")
  → lee launch_command del card
  → verifica si el agente está corriendo (pane_current_command)
  → si no corre, ejecuta launch_command en el pane y espera hasta 12s
  → crea sesión en AgoraRegistry, retorna session_id
```

### message (async)
```
talk_to(agent="ariadna", action="message", session_id="agora_abc123", prompt="...")
  → envía prompt por tmux send-keys
  → inicia reader thread en background
  → retorna INMEDIATAMENTE con status: "sent"
```

### poll / wait
```
talk_to(action="poll", session_id="agora_abc123")
  → consulta estado, progreso, y respuesta si llegó

talk_to(action="wait", session_id="agora_abc123", timeout=120)
  → bloquea hasta respuesta o timeout
```

### cancel / close
```
talk_to(action="cancel", session_id="agora_abc123")
  → aborta sesión, limpia pipe

talk_to(action="close", session_id="agora_abc123")
  → cierra canal, elimina pipe, limpia registry
```

---

## Agregar un nuevo agente

Ver tutorial completo: [tutorial-nuevo-agente.md](tutorial-nuevo-agente.md)

Resumen:
1. `hermes profile create mi-agente`
2. Configurar `config.yaml` con formato de modelo correcto
3. `ln -s ~/.hermes/agora/plugin ~/.hermes/profiles/mi-agente/plugins/agora`
4. Crear `~/.hermes/agora/cards/mi-agente.yaml` con `launch_command: "hermes -p mi-agente"`
5. Verificar con `talk_to(agent="?", action="discover")`

El card YAML no requiere cambios para v4 — `session_id` es generado por el orchestrator, no por el card.
