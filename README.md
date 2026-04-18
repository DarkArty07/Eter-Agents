# Eter Agent Ecosystem

Multi-agent AI infrastructure built on the [Hermes Agent](https://github.com/nousresearch/hermes-agent) framework.

## Getting Started

### Prerequisites

- **Python 3.11+** — Required for the Hermes Agent framework
- **tmux** — Required for multi-agent IPC (inter-agent communication)
- **Git** — Version control
- **Hermes Agent SDK** — The agent runtime framework

### Installing the Hermes Agent SDK

The SDK lives in `~/.hermes/sdk/` (gitignored). Install it from the official repo:

```bash
# Clone the SDK into the expected location
git clone https://github.com/nousresearch/hermes-agent.git ~/.hermes/sdk

# Install Python dependencies
cd ~/.hermes/sdk
pip install -e .

# Verify installation — the "hermes" command should be available
hermes --version
```

> The `hermes` command is what launches agent profiles. 
> Each profile runs as an independent agent instance.

### Installation

```bash
# 1. Clone the ecosystem into ~/.hermes/
git clone https://github.com/DarkArty07/Eter-Agent-Ecosystem.git ~/.hermes
cd ~/.hermes

# 2. Install the Hermes Agent SDK (see above)
git clone https://github.com/nousresearch/hermes-agent.git ~/.hermes/sdk
cd sdk && pip install -e . && cd ..

# 3. Copy and configure API keys
cp shared/env.base.example shared/env.base
# Edit shared/env.base with your real API keys (nano, vim, etc.)

# 4. Create profile config from example
cp profiles/hermes/config.yaml.example profiles/hermes/config.yaml
# Edit config.yaml with your model provider settings

# 5. Generate .env files for each profile
./scripts/setup-env.sh

# 6. Install the Agora IPC plugin for each profile
mkdir -p profiles/hermes/plugins
ln -s ~/.hermes/agora/plugin profiles/hermes/plugins/agora

# 7. Verify Agora installation
bash agora/check.sh

# 8. Launch your first agent
hermes -p hermes
```

### Configuration

**API Keys:** All shared API keys live in `shared/env.base`. This file is git-ignored — never commit it!

- Copy `shared/env.base.example` to `shared/env.base`
- Fill in your real API keys (OpenCode Go, GLM, MiniMax, Exa, FAL.ai, etc.)
- Run `./scripts/setup-env.sh` to generate `.env` files for each profile

**Profile Overrides:** For profile-specific settings, use `profiles/<name>/.env.overrides`. These override the shared base.

### Launching

```bash
# Launch a specific profile
hermes -p hermes        # Architect & orchestrator
hermes -p ariadna       # Project manager
hermes -p hefesto       # Technical executor
hermes -p etalides      # Researcher
```

### Structure

See [LAYOUT.md](LAYOUT.md) for the canonical directory reference.

```
~/.hermes/
├── agora/                    ← Inter-agent IPC (v5 — inbox JSON)
│   ├── plugin/               ← Python plugin code
│   │   ├── _orchestrator.py  ← talk_to handler
│   │   ├── _worker.py        ← post_llm_call hook
│   │   ├── _registry.py      ← Session management
│   │   ├── _paths.py         ← HERMES_HOME-aware paths
│   │   └── cards/            ← Agent cards (symlink-free)
│   └── docs/                 ← Design & IPC documentation
├── docs/                     ← Templates & conventions
│   ├── .eter-template/       ← Template for project .eter/ dirs
│   └── eter-convention.md    ← Ecosystem conventions
├── profiles/                 ← Agent profiles (isolated environments)
│   ├── hermes/               ← Architect & orchestrator
│   ├── ariadna/              ← Project manager & session auditor
│   ├── hefesto/              ← Technical executor
│   └── etalides/             ← Researcher & knowledge librarian
├── scripts/                  ← Infrastructure scripts
│   └── setup-env.sh          ← Generate .env from shared base
├── shared/                   ← Shared config
│   └── env.base.example      ← API keys template (git-tracked)
├── .gitignore                ← Ignores runtime, secrets, checkpoints
├── LAYOUT.md                 ← Directory structure reference
└── README.md                 ← This file
```

**Not in repo (git-ignored):**
- `shared/env.base` — Your real API keys (copy from example)
- `profiles/*/config.yaml` — Per-profile config
- `profiles/*/.env` — Generated environment files
- `profiles/*/checkpoints/` — Git checkpoints (7000+ files)
- `profiles/*/logs/`, `profiles/*/memories/` — Runtime data
- `profiles/*/sessions/` — Session history
- `profiles/*/docs/`, `profiles/*/plans/` — Runtime docs & plans
- `.eter/` — Ecosystem state tracking
- `agora/.eter/`, `agora/.ariadna/` — Agent runtime state
- `agora/research/` — Development research notes
- `interface/` — Separate UI project
- `plans/`, `docs/sesiones/`, `docs/agent-queue/` — Legacy data

### Creating a New Agent

1. **Create the profile:**
   ```bash
   hermes profile create myagent
   ```

2. **Edit the SOUL.md** — define identity, role, and behavior:
   ```bash
   nano profiles/myagent/SOUL.md
   ```

3. **Create the Agent Card** for IPC discovery:
   ```bash
   cp agora/plugin/cards/hermes.yaml agora/plugin/cards/myagent.yaml
   nano agora/plugin/cards/myagent.yaml
   # Set: name, role, description, capabilities, launch_command
   ```

4. **Configure the profile:**
   ```bash
   cp profiles/hermes/config.yaml.example profiles/myagent/config.yaml
   nano profiles/myagent/config.yaml
   ```

5. **Install the Agora plugin:**
   ```bash
   mkdir -p profiles/myagent/plugins
   ln -s ~/.hermes/agora/plugin profiles/myagent/plugins/agora
   ```

6. **Generate .env:**
   ```bash
   ./scripts/setup-env.sh --profile myagent
   ```

7. **Launch and verify:**
   ```bash
   hermes -p myagent
   ```

For the full walkthrough, see [agora/docs/tutorial-nuevo-agente.md](agora/docs/tutorial-nuevo-agente.md).

---

## Agent Hierarchy

Three tiers with distinct roles and capabilities:

### Archon (Level 1) — Orchestrator

The human's direct interface. Designs systems, makes architectural decisions, delegates work, synthesizes results.

```
└── Hermes — System architect, researcher, orchestrator
```

### Daimon (Level 2) — Specialists

Persistent agents with their own identity (SOUL.md), memory, skills, and cross-session state. Not task executors — collaborators with agency.

```
├── Ariadna  — Project manager, cross-session memory, audit
├── Hefesto  — Technical executor, delegate_task coordinator
└── Etalides — Researcher, web investigation, knowledge preservation
```

### Ergates (Level 3) — Workers

Stateless task executors. Spawned on demand by Hefesto via `delegate_task`. Single job, no persistent memory.

```
├── implementer   — Writes code
├── researcher    — Investigates and reports
└── reviewer      — Audits against acceptance criteria
```

## Communication

```
El usuario → talk_to → Hermes → talk_to → Ariadna  (state queries)
                                     → Hefesto   (implementation)
                                     → Etalides  (research)
Hefesto → delegate_task → mini-agents (parallel execution)
```

**Agora IPC v5** — Self-managed inter-agent communication using tmux + JSON inboxes:
- `discover → open → message → poll/wait → close`
- Zero threads per session, atomic JSON writes, debuggable with `cat`
- Auto-spawns agents in tmux, waits for framework ready before sending messages

See [agora/docs/ipc.md](agora/docs/ipc.md) for the full IPC protocol specification.

## Environment Configuration

**No individual `.env` editing.** All shared API keys live in `shared/env.base`. Profile-specific overrides go in `profiles/<name>/.env.overrides`. Generate with:

```bash
./scripts/setup-env.sh          # All profiles
./scripts/setup-env.sh --profile hermes  # Single profile
```

See [shared/env.base.example](shared/env.base.example) for available keys.

## Project Tracking (`.eter/`)

Each project has a `.eter/` directory for cross-session state:

```
project/.eter/
├── .hermes/       ← DESIGN.md (architecture) + PLAN.md (execution)
├── .ariadna/      ← CURRENT.md (status + blockers) + LOG.md (history)
├── .hefesto/      ← TASKS.md (auto-generated during execution)
└── .etalides/     ← RESEARCH.md (investigation findings)
```

Complexity classification: **simple** (no files) → **medium** (DESIGN.md) → **complex** (DESIGN.md + PLAN.md)

Template available at [docs/.eter-template/](docs/.eter-template/).

## Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| No symlinks | Direct files for cards and config | Portable, git-friendly |
| Shared env | `env.base` + `.env.overrides` → generated `.env` | No SDK modification needed |
| HERMES_HOME paths | `_paths.py` resolves root dynamically | Works in profile and direct mode |
| Agent cards | Inside plugin (`agora/plugin/cards/`) | Single source of truth |
| Plugin loading | `plugins: paths` in config.yaml | No symlinks needed |
| Checkpoints gitignored | 7000+ files in `profiles/*/checkpoints/` | Prevents repo bloat |

## License

See [LICENSE](LICENSE) for details.
