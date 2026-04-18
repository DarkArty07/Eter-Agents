# Agora — E2E Test Checklist v4

## Prerequisitos

- [ ] tmux instalado (`tmux -V`)
- [ ] Symlinks correctos (`bash ~/.hermes/agora/check.sh`)
- [ ] Profile de ariadna configurado (`hermes -p ariadna` funciona)
- [ ] Profile de hefesto configurado (`hermes -p hefesto` funciona)

---

## Test 1 — Discover

```
talk_to(agent="?", action="discover")
```

- [ ] Retorna JSON con `agents` array
- [ ] `ariadna` está en la lista con `available: true`
- [ ] `hefesto` está en la lista con `available: true`
- [ ] `hermes` está en la lista con `available: true`

## Test 2 — Discover specific agent

```
talk_to(agent="ariadna", action="discover")
```

- [ ] Retorna JSON con `name`, `role`, `description`, `capabilities`
- [ ] `available` es `true`

## Test 3 — Open

```
talk_to(agent="ariadna", action="open")
```

- [ ] Retorna JSON con `session_id` (formato "agora_xxxxxxxxxxxx")
- [ ] `status` es "open"
- [ ] `pipe` path existe en el filesystem
- [ ] Sesión tmux "agora" existe (`tmux list-sessions`)
- [ ] Pane para ariadna existe (`tmux list-windows -t agora`)
- [ ] ariadna está corriendo (pane_current_command es "hermes" o "python")

## Test 4 — Message async

```
talk_to(agent="ariadna", action="message", session_id="<session_id>", prompt="Hola, ¿estás online?")
```

- [ ] Retorna INMEDIATAMENTE (no bloquea más de 2 segundos)
- [ ] `status` es "sent"
- [ ] `session_id` coincide con el del open

## Test 5 — Poll (working)

```
talk_to(action="poll", session_id="<session_id>")
```

- [ ] Retorna JSON con `status` ("working" o "done")
- [ ] Si "working": `elapsed_seconds` > 0
- [ ] Si "working": `activity` contiene texto del pane tmux

## Test 6 — Wait (blocking)

```
talk_to(action="wait", session_id="<session_id>", timeout=120)
```

- [ ] Retorna JSON con `status` "done"
- [ ] `response` contiene la respuesta de ariadna
- [ ] `elapsed_seconds` > 0
- [ ] No bloquea más de `timeout` segundos

## Test 7 — Poll after response

```
talk_to(action="poll", session_id="<session_id>")
```

- [ ] `status` es "done"
- [ ] `response` contiene la respuesta completa

## Test 8 — Close

```
talk_to(action="close", session_id="<session_id>")
```

- [ ] Retorna JSON con `status` "closed"
- [ ] El pipe fue eliminado del filesystem
- [ ] La sesión ya no aparece en `list_sessions()`

## Test 9 — Error: message sin open

```
talk_to(agent="ariadna", action="message", prompt="test", session_id="invalid_id")
```

- [ ] Retorna error "SessionNotFound"

## Test 10 — Error: poll sin session_id

```
talk_to(action="poll", session_id="")
```

- [ ] Retorna error "Falta el parámetro 'session_id'"

## Test 11 — Multi-turno

```
# Segundo mensaje en la misma sesión
talk_to(agent="ariadna", action="message", session_id="<session_id>", prompt="Otra pregunta")
talk_to(action="wait", session_id="<session_id>", timeout=60)
```

- [ ] Retorna la segunda respuesta correctamente
- [ ] session_id es el mismo

## Test 12 — Paralelismo (dos agentes)

```
# Abrir dos canales
talk_to(agent="ariadna", action="open") → session_id_1
talk_to(agent="hefesto", action="open") → session_id_2

# Enviar mensajes a ambos
talk_to(agent="ariadna", action="message", session_id=session_id_1, prompt="...")
talk_to(agent="hefesto", action="message", session_id=session_id_2, prompt="...")

# Poll ambos
talk_to(action="poll", session_id=session_id_1)
talk_to(action="poll", session_id=session_id_2)

# Cerrar ambos
talk_to(action="close", session_id=session_id_1)
talk_to(action="close", session_id=session_id_2)
```

- [ ] Ambos mensajes se envían sin bloquearse entre sí
- [ ] Ambas respuestas se reciben independientemente
- [ ] Las sesiones no interfieren entre sí

## Test 13 — Cancel

```
talk_to(agent="ariadna", action="open") → session_id
talk_to(agent="ariadna", action="message", session_id=session_id, prompt="...")
talk_to(action="cancel", session_id=session_id)
```

- [ ] Retorna `status` "cancelled"
- [ ] El pipe fue eliminado
- [ ] Poll posterior retorna error "SessionNotFound" o status "cancelled"

## Test 14 — Wait timeout

```
# Configurar un timeout muy corto
talk_to(action="wait", session_id="<session_id>", timeout=2)
```

- [ ] Retorna `status` "timeout" si el agente no responde en 2 segundos
- [ ] No cuelga indefinidamente

## Test 15 — Notificación automática (CLI)

- [ ] Después de enviar un mensaje async, al recibir la respuesta del worker,
  el CLI muestra `[SYSTEM: Agora — ariadna terminó...]` como notificación
- [ ] La notificación incluye el session_id correcto

## Test 16 — Backward compatibility

- [ ] `discover` funciona igual que antes
- [ ] `open` retorna `session_id` además de los campos anteriores
- [ ] El worker (`_worker.py`) no requiere cambios
- [ ] Las cards YAML no requieren cambios

## Test 17 — Watchdog del worker

- [ ] Si se envía un mensaje a un agente con modelo mal configurado,
  el watchdog escribe error al pipe tras 90s
- [ ] El error se recibe vía `poll` como `status: "error"`
- [ ] El error se recibe vía `wait` como `status: "error"`

## Test 18 — Pane activity capture

- [ ] Durante un `poll` con `status: "working"`, el campo `activity` muestra
  las últimas acciones del agente (tools que está llamando)
- [ ] `activity` no está vacío cuando el agente está trabajando
- [ ] `activity` se strippea de ANSI codes