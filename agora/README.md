# Agora — Canal de comunicación inter-agente

Canal IPC async para que Hermes se comunique con sub-agentes (Ariadna, Hefesto).

## Versión 5.0.0

**Cambio principal:** Inbox JSON atómico reemplaza Named Pipes (FIFOs). Cero threads por sesión, cero race conditions. Debuggeable con `cat inbox/hefesto.json`.

**Mejoras sobre v4:**
- 0 threads por sesión (antes 2: reader + watchdog)
- 0 race conditions (antes 4+: EOF, pipe closed, partial reads)
- Detección de completitud por timestamp gating (`written_at > sent_at`)
- Escritura atómica (tmp + rename) — nunca se lee JSON a medio escribir
- ~26% menos código (967 vs 1315 líneas)
- Respuestas tardías manejadas correctamente

## Acciones

| Acción | Bloquea? | Descripción |
|---|---|---|
| `discover` | No | Lista agentes disponibles |
| `open` | No | Crea canal de comunicación, retorna session_id |
| `message` | **No** | Envía prompt, retorna inmediatamente (async) |
| `poll` | No | Consulta estado, progreso y respuesta |
| `wait` | Sí (timeout) | Bloquea hasta respuesta o timeout |
| `cancel` | No | Aborta sesión |
| `close` | No | Cierra canal |

## Instalación

```bash
# Verificar instalación
bash ~/.hermes/agora/check.sh

# Symlinks (si no están)
ln -sf ~/.hermes/agora/plugin ~/.hermes/profiles/hermes/plugins/agora
ln -sf ~/.hermes/agora/plugin ~/.hermes/profiles/ariadna/plugins/agora
ln -sf ~/.hermes/agora/plugin ~/.hermes/profiles/hefesto/plugins/agora
```

## Estructura

```
~/.hermes/agora/
├── plugin/           # Código del plugin
│   ├── __init__.py   # Entry point (despacha por profile)
│   ├── _orchestrator.py  # Handler de talk_to (Hermes)
│   ├── _registry.py  # AgoraRegistry (estado entre llamadas)
│   ├── _worker.py    # Hooks del worker (Ariadna/Hefesto)
│   └── plugin.yaml   # Metadata (v5.0.0)
├── cards/            # Agent cards YAML
├── docs/             # Documentación
├── inbox/            # Inbox JSON files (runtime)
├── skills/           # Skill de uso para Hermes
└── check.sh          # Script de verificación
```

## Documentación

- `docs/design.md` — Decisiones de arquitectura
- `docs/ipc.md` — Mecanismo IPC técnico
- `docs/agent-cards.md` — Especificación de agent cards
- `skills/hermes/SKILL.md` — Guía de uso de talk_to
