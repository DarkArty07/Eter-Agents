"""
Smoke test para el plugin agora.
No requiere tmux, harmonia ni agentes corriendo.

Ejecutar:
    $HOME/.hermes/sdk/venv/bin/python \
    $HOME/.hermes/agora/plugin/tests/test_smoke.py
"""

import json
import os
import shutil
import subprocess
import sys
import importlib
import types

# ── Importar el plugin ──────────────────────────────────────────────────────

from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[3]
AGORA_DIR = REPO_ROOT / "agora"

sys.path.insert(0, str(REPO_ROOT))

# Restaurar HOME al valor real para que ~ se expanda correctamente
# (el entorno hermes puede sobreescribir HOME al del profile)
if 'HOME' not in os.environ:
    os.environ['HOME'] = str(Path.home())
os.environ['HERMES_HOME'] = str(REPO_ROOT / "profiles/hermes")

# Crear paquete padre 'agora' en sys.modules para que los imports relativos
# en plugin/__init__.py (from . import _orchestrator) funcionen.
agora_pkg = types.ModuleType('agora')
agora_pkg.__path__ = [str(AGORA_DIR)]
agora_pkg.__package__ = 'agora'
sys.modules['agora'] = agora_pkg

# Ahora usar importlib para cargar el subpaquete 'agora.plugin'
import importlib.util

spec = importlib.util.spec_from_file_location(
    'agora.plugin',
    str(AGORA_DIR / "plugin/__init__.py"),
    submodule_search_locations=[str(AGORA_DIR / "plugin")],
)
agora = importlib.util.module_from_spec(spec)
agora.__package__ = 'agora.plugin'
sys.modules['agora.plugin'] = agora
sys.modules['agora']._plugin = agora  # para que 'from . import _orchestrator' encuentre el padre
spec.loader.exec_module(agora)

# Los imports relativos dentro de register() ahora funcionan.
# Para acceder a las funciones internas directamente:
from agora.plugin import _orchestrator as orchestrator
from agora.plugin import _worker as worker


# ── Mock de contexto ────────────────────────────────────────────────────────

class MockCtx:
    def __init__(self):
        self.registered_tools = []
        self.registered_hooks = []
        self.manifest = type('M', (), {'config': {}})()

    def register_tool(self, name, **kwargs):
        self.registered_tools.append(name)

    def register_hook(self, name, cb):
        self.registered_hooks.append(name)


# ── Runner de tests ─────────────────────────────────────────────────────────

passed = 0
failed = 0
results = []


def test(name, fn):
    global passed, failed
    # Pre-append para que fn() pueda sobreescribir results[-1] con info dinámica
    results.append(f"✅ {name}")
    try:
        fn()
        passed += 1
    except AssertionError as e:
        failed += 1
        results[-1] = f"❌ {name} → {e}"
    except Exception as e:
        failed += 1
        results[-1] = f"❌ {name} → excepción inesperada: {type(e).__name__}: {e}"


# ── Helper: detectar si tmux está instalado ─────────────────────────────────

def _tmux_installed() -> bool:
    """True si el binario tmux está disponible en el sistema."""
    return shutil.which("tmux") is not None


# ── Tests ───────────────────────────────────────────────────────────────────

# 1. Detección de rol: orchestrator
def t_rol_orchestrator():
    os.environ['HERMES_HOME'] = '$HOME/.hermes/profiles/hermes'
    ctx = MockCtx()
    agora.register(ctx)
    assert 'talk_to' in ctx.registered_tools, \
        f"talk_to no registrada, herramientas: {ctx.registered_tools}"

test("detección de rol: orchestrator", t_rol_orchestrator)


# 2. Detección de rol: worker
def t_rol_worker():
    os.environ['HERMES_HOME'] = '$HOME/.hermes/profiles/ariadna'
    ctx = MockCtx()
    agora.register(ctx)
    assert 'post_llm_call' in ctx.registered_hooks, \
        f"hook no registrado, hooks: {ctx.registered_hooks}"

test("detección de rol: worker", t_rol_worker)

# Restaurar HERMES_HOME para el resto de los tests
os.environ['HERMES_HOME'] = '$HOME/.hermes/profiles/hermes'


# 3. discover ? → JSON válido, Ariadna incluida, count >= 1
def t_discover_todos():
    raw = orchestrator._action_discover("?")
    data = json.loads(raw)
    assert "agents" in data, f"sin campo 'agents': {data}"
    assert "count" in data, f"sin campo 'count': {data}"
    count = data["count"]
    assert count >= 1, f"count es {count}, se esperaba >= 1"
    names = [a["name"] for a in data["agents"]]
    assert "ariadna" in names, f"ariadna no está en la lista: {names}"
    results[-1] = f"✅ discover ? → {count} agentes"

test("discover ? → N agentes", t_discover_todos)


# 4. discover ariadna → capacidades, available: true
def t_discover_ariadna():
    raw = orchestrator._action_discover("ariadna")
    data = json.loads(raw)
    assert "error" not in data, f"retornó error: {data}"
    assert data.get("available") is True, f"available no es true: {data}"
    caps = data.get("capabilities", [])
    assert len(caps) > 0, f"sin capacidades: {data}"

test("discover ariadna → available: true", t_discover_ariadna)


# 5. discover fantasma → AgentNotFound
def t_discover_fantasma():
    raw = orchestrator._action_discover("fantasma")
    data = json.loads(raw)
    assert data.get("error") == "AgentNotFound", \
        f"error esperado 'AgentNotFound', obtenido: {data}"

test("discover fantasma → AgentNotFound", t_discover_fantasma)


# 6. open sin tmux → TmuxNotAvailable / open con tmux → AgentNotReachable o ready
def t_open_sin_tmux():
    raw = orchestrator._action_open("ariadna")
    data = json.loads(raw)

    if not _tmux_installed():
        # Sin tmux → solo TmuxNotAvailable es aceptable
        assert data.get("error") == "TmuxNotAvailable", \
            f"sin tmux: se esperaba 'TmuxNotAvailable', obtenido: {data}"
        results[-1] = "✅ open sin tmux → TmuxNotAvailable"
    else:
        # Con tmux instalado: el orchestrator crea sesión + pane dinámicamente.
        # Puede retornar:
        #   - status: ready (si todo funciona)
        #   - error: TmuxNotAvailable (si tmux -V funciona pero el server falla)
        #   - error: AgentNotReachable (si no puede lanzar el agente)
        acceptable = {"ready", "TmuxNotAvailable", "AgentNotReachable"}
        if data.get("status") in acceptable:
            results[-1] = f"✅ open con tmux → status: {data.get('status')}"
        elif data.get("error") in acceptable:
            results[-1] = f"✅ open con tmux → error: {data.get('error')}"
        else:
            raise AssertionError(
                f"con tmux: se esperaba status ready o error TmuxNotAvailable/AgentNotReachable, "
                f"obtenido: {data}"
            )

test("open → manejo de tmux", t_open_sin_tmux)


# 7. message sin open previo → CanalNoAbierto
def t_message_sin_open():
    # Limpiar pane_map para asegurar estado limpio
    orchestrator._pane_map.clear()
    raw = orchestrator._action_message("ariadna", "hola", "")
    data = json.loads(raw)
    assert "error" in data, f"se esperaba campo 'error', obtenido: {data}"
    # El código revisa primero si existe la card (AgentNotFound) y luego
    # si existe el pipe (CanalNoAbierto). Como ariadna tiene card válida
    # pero no hay pipe, retorna CanalNoAbierto.
    assert data.get("error") == "CanalNoAbierto", \
        f"error esperado 'CanalNoAbierto', obtenido: {data}"

test("message sin open → CanalNoAbierto", t_message_sin_open)


# 8. close sin pipe → SessionNotFound
def t_close_sin_pipe():
    raw = orchestrator._action_close("agora_invalid", "ariadna")
    data = json.loads(raw)
    # result = {"error": "SessionNotFound", "session_id": "agora_invalid"}
    assert data.get("error") == "SessionNotFound", \
        f"error esperado 'SessionNotFound', obtenido: {data}"

test("close sin pipe → SessionNotFound", t_close_sin_pipe)


# 9. hook worker sin pipe → return silencioso, no cuelga
def t_hook_worker_sin_pipe():
    import signal

    def timeout_handler(signum, frame):
        raise TimeoutError("_on_response_complete tardó más de 5 segundos")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(5)
    try:
        result = worker._on_response_complete("respuesta de test")
        signal.alarm(0)
        # Debe retornar None (return implícito o explícito)
        assert result is None, f"se esperaba None, obtenido: {result!r}"
    except TimeoutError as e:
        raise AssertionError(str(e))
    finally:
        signal.alarm(0)

test("hook worker sin pipe → silencioso", t_hook_worker_sin_pipe)


# ── Reporte ─────────────────────────────────────────────────────────────────

print()
for r in results:
    print(r)
print()

total = passed + failed
if failed == 0:
    print(f"--- {passed}/{total} TESTS PASARON ---")
else:
    print(f"--- {passed}/{total} PASARON, {failed} FALLARON ---")
    sys.exit(1)
