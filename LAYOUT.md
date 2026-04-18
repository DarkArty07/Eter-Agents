# Eter Agents — Directory Layout

> Canonical reference for `~/.hermes/` structure.
> Last updated: 2026-04-18

## Root Structure

```
~/.hermes/
├── .eter/                    ← Ecosystem state tracking
│   ├── .ariadna/             ← Project management (CURRENT.md, LOG.md)
│   ├── .etalides/            ← Research notes
│   ├── .hefesto/             ← Task state
│   └── .hermes/              ← Design docs (DESIGN.md, PLAN.md)
│
├── agora/                    ← IPC system (v5 — inbox JSON)
│   ├── inbox/                ← Response files (atomic JSON write)
│   ├── plugin/               ← Python plugin code
│   │   ├── _orchestrator.py  ← Hermes-side: talk_to handler
│   │   ├── _worker.py        ← Worker-side: post_llm_call hook
│   │   ├── _registry.py      ← Session management
│   │   ├── _convo_log.py     ← Conversation logging
│   │   ├── _paths.py         ← HERMES_HOME-aware path resolution
│   │   ├── __init__.py       ← Plugin registration
│   │   ├── plugin.yaml       ← Plugin metadata
│   │   ├── tests/            ← Test suite
│   │   └── cards/            ← Agent cards (symlink-free)
│   │       ├── hermes.yaml
│   │       ├── ariadna.yaml
│   │       ├── hefesto.yaml
│   │       └── etalides.yaml
│   ├── docs/                 ← Agora documentation
│   └── skills/               ← Agora skill docs
│
├── docs/                     ← Ecosystem documentation
│   ├── .eter-template/       ← Template for new projects
│   ├── eter-convention.md    ← .eter/ convention spec
│   └── *.md                  ← Various design docs
│
├── profiles/                 ← Agent profiles (one per agent)
│   ├── hermes/               ← Primary agent (architect)
│   │   ├── .env              ← Generated (gitignored) — DO NOT EDIT
│   │   ├── .env.overrides    ← Profile-specific env overrides
│   │   ├── config.yaml       ← Agent configuration
│   │   ├── SOUL.md           ← Agent identity and behavior
│   │   ├── skills/           ← Agent-specific skills
│   │   ├── plugins/          ← Plugin config (plugins: paths in config.yaml)
│   │   ├── sessions/         ← Conversation history (gitignored)
│   │   ├── memories/         ← Persistent memory (gitignored)
│   │   └── state.db          ← Session state (gitignored)
│   │
│   ├── ariadna/              ← Project manager
│   ├── hefesto/              ← Technical executor
│   └── etalides/             ← Researcher
│       └── (same structure as hermes/)
│
├── scripts/                  ← Infrastructure scripts
│   ├── setup-env.sh          ← Generate .env from shared/env.base + overrides
│
├── shared/                   ← Shared configuration (git-tracked)
│   └── env.base              ← API keys and config shared by all profiles
│
├── sdk/                      ← Hermes Agent framework (gitignored)
│
├── .gitignore                ← Comprehensive ignore rules
└── README.md                 ← This file
```

## Legacy Files (pre-refactor, not tracked)

The root `~/.hermes/` directory contains runtime artifacts from before the refactor.
These are gitignored but present on disk:

```
~/.hermes/
├── cache/              ← Image/model cache (gitignored)
├── channel_directory.json  ← Gateway state (gitignored)
├── cron/               ← Cron job state (gitignored)
├── gateway.pid         ← Gateway PID (gitignored)
├── gateway_state.json  ← Gateway state (gitignored)
├── interface/          ← Terminal frontend (separate project)
├── logs/               ← Agent logs (gitignored)
├── memories/           ← Legacy memory (gitignored, now OpenViking)
├── plans/              ← Legacy plans directory
├── platforms/          ← Platform configs (gitignored)
├── plugins/            ← Plugin discovery dir (agora symlink)
├── sessions/           ← Session history (gitignored)
├── skills/             ← Global skills dir (gitignored)
├── state.db*           ← Agent state DB (gitignored)
```

These are runtime artifacts and should not be committed to the repo.

## Key Principles

1. **No symlinks** except `plugins/agora` (required by SDK discovery mechanism)
2. **No hardcoded paths** — Agora plugin uses `_paths.get_hermes_root()` for HERMES_HOME-aware resolution
3. **Shared env** — `shared/env.base` + `profiles/<name>/.env.overrides` → generated `.env`
4. **Git-tracked** — Only docs, plugin code, skills, SOUL.md, config templates, and scripts
5. **Gitignored** — .env, sessions/, memories/, state.db, logs/, auth.json, sdk/

## Path Resolution

The Agora plugin resolves paths relative to the ecosystem root:

```
HERMES_HOME=~/.hermes/profiles/hermes  →  root=~/.hermes/
HERMES_HOME=~/.hermes                   →  root=~/.hermes/
```

Implemented in `agora/plugin/_paths.py` using the same logic as `hermes_constants.get_default_hermes_root()`.

## Plugin Loading

Plugins are loaded via `config.yaml`:

```yaml
plugins:
  paths:
    - $HOME/.hermes/agora/plugin  # TODO: make portable
```

This is the remaining hardcoded path — future work to make it relative.