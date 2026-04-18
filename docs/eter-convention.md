# Eter — Convención de proyecto .eter/

> Referencia para todos los agentes del ecosistema

## Qué es .eter/

`.eter/` es la carpeta que vive en la raíz de cada proyecto y centraliza todo el estado del ecosistema de agentes para ese proyecto.

**Si no está en `.eter/`, no existe.**

## Estructura (simplificada v2)

```
PROYECTO/.eter/
├── .hermes/              ← Diseño y decisiones
│   ├── DESIGN.md         ← Arquitectura (medio y complejo)
│   └── PLAN.md           ← Ejecución (solo complejo)
├── .ariadna/             ← Tracking de proyecto
│   ├── CURRENT.md        ← Estado actual + blockers + próximos pasos (todo en uno)
│   └── LOG.md            ← Historial de sesiones (append only)
├── .hefesto/             ← Ejecución (creado por Hefesto)
│   └── TASKS.md          ← Estado de tareas (auto-generado)
└── .etalides/            ← Investigación (solo si se usó Etalides)
    └── RESEARCH.md       ← Hallazgos de investigación
```

**Cambios vs v1:**
- `BLOCKERS.md` se integró en `CURRENT.md` sección "Blockers"
- `ROADMAP.md` se integró en `CURRENT.md` sección "Próximos pasos"
- `SOURCES.md` se eliminó (las fuentes van dentro de RESEARCH.md)
- `PLAN.md` solo existe para complejo, no para medio

## Complejidad y archivos

| Complejidad | Archivos .eter/ creados |
|---|---|
| **Simple** | Ninguno |
| **Medio** | `.hermes/DESIGN.md` + `.ariadna/CURRENT.md` + `.ariadna/LOG.md` |
| **Complejo** | Todos (DESIGN.md + PLAN.md + CURRENT.md + LOG.md) |

## Reglas por agente

### Hermes (Arquitecto)
- Lee `.eter/.ariadna/CURRENT.md` al iniciar trabajo en un proyecto
- Escribe `.eter/.hermes/DESIGN.md` (medio y complejo) y `PLAN.md` (solo complejo)
- Al cerrar sesión, actualiza CURRENT.md y append a LOG.md
- Simple = no crea archivos .eter/

### Ariadna (Project Manager)
- `.eter/.ariadna/` es su dominio exclusivo
- `CURRENT.md` = estado + blockers + próximos pasos (todo en uno)
- `LOG.md` es append-only — nunca se modifica ni borra
- Si el proyecto no tiene `.eter/`, lo crea

### Hefesto (Ejecutor técnico)
- `.eter/.hefesto/` es su dominio
- `TASKS.md` tracking de tareas: en progreso, pendientes, completadas
- Al recibir un spec de Hermes, verifica que `.eter/` existe

### Etalides (Investigador/Bibliotecario)
- `.eter/.etalides/` solo se crea si se usa Etalides para research
- `RESEARCH.md` contiene hallazgos + fuentes estructuradas
- Siempre verifica `knowledge/` universal primero antes de buscar en web
- NUNCA usa OpenViking, NUNCA opina, SIEMPRE cita fuentes

## Crear .eter/ en un proyecto nuevo

Copiar el template:

```bash
cp -r ~/.hermes/docs/.eter-template/ /ruta/al/proyecto/.eter/
```

Luego editar cada archivo reemplazando `<Proyecto>` con el nombre real.

**Para tareas simples:** no crear `.eter/` en absoluto.

## Git

Agregar `.eter/` al `.gitignore` del proyecto si no se quiere versionar el estado de los agentes.
Alternativamente, versionar solo `DESIGN.md` y gitignoregar los de runtime (`LOG.md`, `TASKS.md`).

## Migración desde el formato anterior (v1)

Proyectos que usaban el formato v1 con 4 archivos en .ariadna/:
- Mover contenido de `BLOCKERS.md` a sección "Blockers" de `CURRENT.md`
- Mover contenido de `ROADMAP.md` a sección "Próximos pasos" de `CURRENT.md`
- Eliminar `BLOCKERS.md` y `ROADMAP.md`
- Mover fuentes de `SOURCES.md` dentro de `RESEARCH.md` y eliminar `SOURCES.md`