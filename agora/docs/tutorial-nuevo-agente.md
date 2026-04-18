# Tutorial: Agregar un nuevo agente a Agora

> **Aplica a:** Agora plugin v4.0+  
> **Tiempo estimado:** 10-15 minutos  
> **Prerequisito:** Hermes Agent instalado, tmux disponible

---

## Resumen del proceso

Para que un agente sea alcanzable por `talk_to` necesitas cuatro cosas:

| Qué | Dónde |
|-----|-------|
| Profile de Hermes | `~/.hermes/profiles/{nombre}/` |
| Config válida | `~/.hermes/profiles/{nombre}/config.yaml` |
| Agent card | `~/.hermes/agora/cards/{nombre}.yaml` |
| Plugin instalado como symlink | `~/.hermes/profiles/{nombre}/plugins/agora` → `~/.hermes/agora/plugin` |

---

## Paso 1 — Crear el profile

```bash
hermes profile create mi-agente
```

Esto crea `~/.hermes/profiles/mi-agente/` con una config base.

---

## Paso 2 — Configurar el modelo (CRÍTICO)

Edita `~/.hermes/profiles/mi-agente/config.yaml`. La sección `model:` **debe** usar este formato:

```yaml
model:
  default: qwen3.6-plus
  provider: opencode-go
  base_url: https://opencode.ai/zen/go/v1
  api_mode: chat_completions
providers: {}
fallback_providers: []
agent:
  max_turns: 90
```

### ❌ Formato incorrecto (causa HTTP 400 y pipe bloqueado)

```yaml
# MAL — formato viejo, el SDK lo ignora o interpreta mal
model: opencode-go/kimi-k2.5
provider: opencode
```

### ✅ Por qué importa esto

Si el modelo falla, el hook `post_llm_call` nunca se dispara y el orchestrator
cuelga esperando la respuesta. El plugin tiene un watchdog de 90s que detecta
esto, pero el error es evitable configurando el modelo correctamente desde el
inicio.

**Modelos que funcionan con opencode-go:**
- `qwen3.6-plus` (recomendado para tests)
- Los modelos disponibles en `https://opencode.ai/zen/go/v1`

**Para verificar que el modelo funciona antes de integrarlo con Agora:**
```bash
# Abre el profile directamente y manda un mensaje de prueba
hermes -p mi-agente
# → Si responde sin error 400/404, el modelo está OK
```

---

## Paso 3 — Instalar el plugin como symlink

```bash
ln -s ~/.hermes/agora/plugin ~/.hermes/profiles/mi-agente/plugins/agora
```

**Verificar:**
```bash
ls -la ~/.hermes/profiles/mi-agente/plugins/agora
# Debe mostrar: agora -> $HOME/.hermes/agora/plugin
```

### ❌ No copies el directorio

```bash
# MAL — copia estática que queda desactualizada
cp -r ~/.hermes/agora/plugin ~/.hermes/profiles/mi-agente/plugins/agora

# BIEN — symlink al master
ln -s ~/.hermes/agora/plugin ~/.hermes/profiles/mi-agente/plugins/agora
```

El plugin tiene un guard en `__init__.py` que loggea un warning si detecta que
fue cargado desde una ruta no canónica. Si ves ese warning en `agent.log`, el
symlink está roto o hay una copia vieja.

---

## Paso 4 — Crear el Agent Card

Crea `~/.hermes/agora/cards/mi-agente.yaml`:

```yaml
name: mi-agente          # debe coincidir exactamente con el nombre del profile
role: mi-rol             # rol corto — el LLM lo usa para decidir a quién delegar
description: "Una línea que describe qué hace este agente."
capabilities:
  - capacidad-1
  - capacidad-2
launch_command: "hermes -p mi-agente"   # comando para arrancarlo en tmux
available: true
```

### Campo `launch_command`

Siempre debe ser `hermes -p {nombre-del-profile}`. Ejemplos:

```yaml
launch_command: "hermes -p ariadna"    # ✅
launch_command: "hermes -p hefesto"    # ✅
launch_command: "ariadna chat"         # ❌ comando inexistente
launch_command: "hermes chat"          # ❌ abre el profile por defecto, no el correcto
```

---

## Paso 5 — Verificar la instalación

```bash
# 1. El card existe y es válido
cat ~/.hermes/agora/cards/mi-agente.yaml

# 2. El symlink del plugin apunta al master
ls -la ~/.hermes/profiles/mi-agente/plugins/agora

# 3. El agente puede arrancar manualmente
hermes -p mi-agente
# → debe mostrar el prompt "mi-agente ◈ ❯" y el modelo correcto en la barra de estado
# → no debe mostrar errores HTTP 400/404 al mandar un mensaje

# 4. Desde otra terminal, verificar que el plugin carga como worker
grep "Plugin discovery" ~/.hermes/profiles/mi-agente/logs/agent.log | tail -3
# → debe mostrar: "Plugin discovery complete: 1 found, 1 enabled"
```

---

## Paso 6 — Probar con talk_to

Desde Hermes:

```
talk_to(agent="?", action="discover")
# → mi-agente debe aparecer en la lista con available: true

talk_to(agent="mi-agente", action="open")
# → {"session_id": "agora_abc123", "agent": "mi-agente", "status": "open", ...}

talk_to(agent="mi-agente", action="message", session_id="agora_abc123", prompt="Hola, ¿estás operativo?")
# → {"session_id": "agora_abc123", "status": "sent"}  ← retorna INMEDIATAMENTE

talk_to(action="wait", session_id="agora_abc123", timeout=60)
# → {"status": "done", "response": "...respuesta del agente...", "elapsed_seconds": 12}

talk_to(action="close", session_id="agora_abc123")
# → {"status": "closed", "agent": "mi-agente"}
```

Alternativamente, puedes usar `poll` en vez de `wait` para consultar sin bloquear:

```
talk_to(action="poll", session_id="agora_abc123")
# → {"status": "working", "activity": "┊ search_files(...)", "elapsed_seconds": 5}
```

---

## Diagnóstico de errores comunes

### `AgentNotReachable`

El agente no arrancó dentro del timeout de verificación (12s).

```bash
# Intentar arrancar manualmente para ver el error real
hermes -p mi-agente

# Verificar los logs del agente
tail -20 ~/.hermes/profiles/mi-agente/logs/agent.log
```

Causas frecuentes: modelo inválido, credenciales incorrectas, config mal formateada.

---

### `AgentNotFound`

No existe el card en `~/.hermes/agora/cards/`.

```bash
ls ~/.hermes/agora/cards/
# Verificar que mi-agente.yaml existe
```

---

### `WorkerLLMFailed` (respuesta del watchdog, llega en ~90s)

El agente arrancó pero el LLM falló al procesar el mensaje.

```bash
# Ver el error específico en los logs del agente
tail -30 ~/.hermes/profiles/mi-agente/logs/agent.log | grep -E "ERROR|Non-retryable|400|404|503"
```

La causa más común: modelo incorrecto o no disponible. Revisar Paso 2.

---

### Pipe bloqueado / Hermes espera más de 90s

```bash
# Ver quién tiene el pipe abierto
lsof ~/.hermes/agora/ipc/mi-agente.pipe

# Ver el estado del pane del agente
tmux capture-pane -t agora -p -S -10
# Si muestra "Killed" o prompt bash: el agente murió, relanzar manualmente
```

---

### El agente recibe el mensaje como comando bash (output: "command not found")

El pane de tmux tenía texto residual con indicadores de agente (ej: `ariadna ◈ ❯ Killed`)
que el plugin interpretó como "agente corriendo". El plugin ahora usa `pane_current_command`
para detectarlo, pero si el proceso murió y el pane sigue en bash:

```bash
# Verificar el proceso real en el pane
tmux display-message -t "agora:{indice}" -p "#{pane_current_command}"
# Si muestra "bash" en vez de "python", el agente murió

# Matar el pane y dejar que Agora lo recree en el próximo open
tmux kill-window -t "agora:{indice}"
```

---

## Checklist de verificación rápida

Antes de reportar un bug en Agora, verificar:

- [ ] `hermes -p mi-agente` abre sin errores y el modelo responde
- [ ] `~/.hermes/profiles/mi-agente/plugins/agora` es un **symlink** (no directorio)
- [ ] `config.yaml` usa el formato anidado con `model: { default: ..., provider: ..., ... }`
- [ ] `launch_command` en el card es exactamente `"hermes -p mi-agente"`
- [ ] `available: true` en el card
- [ ] `agent.log` muestra "Plugin discovery complete: 1 found, 1 enabled"
