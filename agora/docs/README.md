# Agora — Canal de comunicación inter-agente

> Plugin de comunicación entre agentes Hermes. Permite que un agente orquestador
> delegue trabajo a sub-agentes y reciba respuestas sin polling.

---

## Inicio rápido (30 segundos)

**Prerequisitos:** `tmux` instalado, profiles configurados con modelo válido.

**Verificar que funciona:**
```
# En Hermes, el LLM puede llamar:
talk_to(agent="?", action="discover")
# → retorna lista de agentes disponibles con sus capacidades
```

**Observar agentes en tiempo real:**
```bash
tmux attach -t agora
```

> Agora crea y gestiona su propia sesión tmux llamada `agora` con una ventana
> por agente. Independiente de harmonia o cualquier workspace externo.

---

## Qué es Agora

Plugin de comunicación P2P entre profiles de Hermes Agent. Implementa un canal
basado en Named Pipes (FIFO) + tmux que permite:

- **Hermes orqueste sub-agentes** sin consumir tokens mientras espera respuesta
- **Los workers notifiquen automáticamente** cuando terminan (infraestructura, no decisión del LLM)
- **Discovery sin alucinación** — solo puedes hablar con agentes que tienen card en `~/.hermes/agora/cards/`
- **Auto-arranque** — si el agente no está corriendo, Agora lo lanza automáticamente

---

## Agentes registrados

| Agente  | Rol                        | Modelo        |
|---------|----------------------------|---------------|
| Hermes  | Orquestador / Diseñador    | orchestrator (tool `talk_to`) |
| Ariadna | Project Manager            | qwen3.6-plus  |
| Hefesto | Orquestador técnico        | qwen3.6-plus  |

---

## Instalación del plugin

El plugin se instala como **symlink** apuntando al master. Nunca como copia.

```bash
# Para el orquestador (Hermes)
ln -s ~/.hermes/agora/plugin ~/.hermes/profiles/hermes/plugins/agora

# Para cada agente worker
ln -s ~/.hermes/agora/plugin ~/.hermes/profiles/ariadna/plugins/agora
ln -s ~/.hermes/agora/plugin ~/.hermes/profiles/hefesto/plugins/agora
```

**Verificar symlinks:**
```bash
ls -la ~/.hermes/profiles/*/plugins/agora
# Todos deben mostrar: agora -> $HOME/.hermes/agora/plugin
```

> El plugin tiene un guard en `__init__.py` que loggea un warning en `agent.log`
> si detecta que fue cargado desde una ruta no canónica (copia desactualizada).

---

## Estructura de carpetas

```
~/.hermes/
├── agora/
│   ├── plugin/                      ← MASTER del plugin (único source of truth)
│   │   ├── __init__.py              ← detecta rol: hermes=orchestrator, resto=worker
│   │   ├── _orchestrator.py         ← tool talk_to (discover/open/message/close)
│   │   ├── _worker.py               ← hooks: pre_llm_call (watchdog), post_llm_call, on_session_end
│   │   ├── plugin.yaml              ← manifiesto
│   │   └── tests/
│   ├── cards/                       ← Agent Cards centralizados
│   │   ├── hermes.yaml
│   │   ├── ariadna.yaml
│   │   └── hefesto.yaml
│   ├── ipc/                         ← FIFOs creados en runtime
│   │   └── {agent}.pipe
│   └── docs/                        ← esta documentación
│
├── profiles/
│   ├── hermes/
│   │   └── plugins/agora            ← symlink → ~/.hermes/agora/plugin
│   ├── ariadna/
│   │   └── plugins/agora            ← symlink → ~/.hermes/agora/plugin
│   └── hefesto/
│       └── plugins/agora            ← symlink → ~/.hermes/agora/plugin
│
└── plugins/
    └── agora                        ← symlink → ~/.hermes/agora/plugin (fallback sin profile)
```

---

## Documentación

- [Tutorial: agregar un nuevo agente](tutorial-nuevo-agente.md) ← **empieza aquí**
- [Formato de Agent Card](agent-cards.md)
- [Mecanismo IPC — Named Pipes](ipc.md)
- [Diseño y decisiones de arquitectura](design.md)
- [Checklist E2E](../plugin/tests/e2e_checklist.md)
