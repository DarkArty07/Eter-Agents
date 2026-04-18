"""
Test de integración IPC para el plugin agora.
Verifica el mecanismo FIFO completo sin necesitar tmux, harmonia ni agentes reales.

Ejecutar:
    HOME=$HOME HERMES_HOME=$HOME/.hermes/profiles/hermes \
    $HOME/.hermes/sdk/venv/bin/python \
    $HOME/.hermes/agora/plugin/tests/test_ipc.py
"""

import json
import os
import sys
import threading
import time
import importlib.util
from pathlib import Path

# ── Importar el plugin ──────────────────────────────────────────────────────

from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[3]
AGORA_DIR = REPO_ROOT / "agora"

sys.path.insert(0, str(REPO_ROOT))

# Restaurar HOME al valor real para que ~ se expanda correctamente
if 'HOME' not in os.environ:
    os.environ['HOME'] = str(Path.home())
os.environ['HERMES_HOME'] = str(REPO_ROOT / "profiles/hermes")

# --- Cargar _orchestrator.py directamente ---
spec_orch = importlib.util.spec_from_file_location(
    'agora.plugin._orchestrator',
    str(AGORA_DIR / "plugin/_orchestrator.py")
)
orchestrator = importlib.util.module_from_spec(spec_orch)
sys.modules['agora.plugin._orchestrator'] = orchestrator
spec_orch.loader.exec_module(orchestrator)


# ── Runner de tests ─────────────────────────────────────────────────────────

passed = 0
failed = 0
results = []


def test(name, fn):
    global passed, failed
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


# ── Test 1 — Ciclo completo de pipe (mock Ariadna) ──────────────────────────

def test_full_pipe_cycle():
    """
    Simula el flujo completo sin orchestrator._action_message:
    1. Crear FIFO manualmente (como haría _action_open)
    2. Thread escritor simula Ariadna escribiendo al pipe
    3. Thread lector simula Hermes leyendo del pipe
    4. Verificar que el mensaje llega correctamente
    """
    pipe_path = Path("/tmp/test_agora_ipc.pipe")
    if pipe_path.exists():
        os.remove(pipe_path)
    os.mkfifo(pipe_path)

    respuesta_esperada = "Hola desde Ariadna (mock)"
    resultado = {"response": None}

    def mock_ariadna():
        time.sleep(0.5)
        with open(pipe_path, "w") as f:
            f.write(respuesta_esperada)

    def mock_hermes():
        with open(pipe_path, "r") as f:
            resultado["response"] = f.read()

    t_ariadna = threading.Thread(target=mock_ariadna, daemon=True)
    t_hermes = threading.Thread(target=mock_hermes, daemon=True)

    t_hermes.start()
    t_ariadna.start()

    t_hermes.join(timeout=5)
    t_ariadna.join(timeout=5)

    # Cleanup
    if pipe_path.exists():
        os.remove(pipe_path)

    assert resultado["response"] == respuesta_esperada, (
        f"Esperado: {respuesta_esperada!r}, Obtenido: {resultado['response']!r}"
    )
    results[-1] = "✅ Test 1 — ciclo completo FIFO: mensaje recibido correctamente"


test("Test 1 — ciclo completo FIFO: mensaje recibido correctamente", test_full_pipe_cycle)


# ── Test 2 — Timeout del registry.wait ──────────────────────────────────────

def test_timeout():
    """
    Crea una sesión, llama _action_wait con timeout=1s.
    Nadie escribe en el inbox → debe retornar status: timeout en ~1s.
    """
    # El código usa .pane_map para encontrar el target tmux.
    # Simulamos que _action_open registró un pane para ariadna.
    original_pane_map = dict(orchestrator._pane_map)
    orchestrator._pane_map["ariadna"] = "agora:ariadna"

    # Mock open a session to get a session_id
    # We need a card for ariadna to exist, which it does in /app/agora/plugin/cards/ariadna.yaml
    # We also need to mock _check_tmux_available and _ensure_agent_running to return True
    import unittest.mock as mock
    with mock.patch.object(orchestrator, "_check_tmux_available", return_value=True), \
         mock.patch.object(orchestrator, "_ensure_agent_running", return_value=True):
        open_res = json.loads(orchestrator._action_open("ariadna"))
        session_id = open_res.get("session_id")

    assert session_id is not None, f"No se pudo abrir sesión: {open_res}"

    t_start = time.time()
    result = json.loads(orchestrator._action_wait(session_id, "ariadna", 1))
    elapsed = time.time() - t_start

    # Restaurar
    orchestrator._pane_map = original_pane_map

    assert result.get("status") == "timeout", (
        f"Esperado status 'timeout', obtenido: {result}"
    )
    assert 0.8 <= elapsed <= 5.0, f"Tiempo fuera de rango: {elapsed:.1f}s (esperado ~1s)"
    results[-1] = f"✅ Test 2 — timeout: retorna status timeout en ~{elapsed:.1f}s"


test("Test 2 — timeout: retorna status timeout en ~1s", test_timeout)


# ── Test 3 — close limpia la sesión ───────────────────────────────────────────

def test_close_removes_session():
    """
    Crea una sesión, llama _action_close,
    verifica que la sesión fue eliminada del registry.
    """
    import unittest.mock as mock
    with mock.patch.object(orchestrator, "_check_tmux_available", return_value=True), \
         mock.patch.object(orchestrator, "_ensure_agent_running", return_value=True):
        open_res = json.loads(orchestrator._action_open("ariadna"))
        session_id = open_res.get("session_id")

    assert session_id is not None, f"No se pudo abrir sesión: {open_res}"
    assert orchestrator.agora_registry.get(session_id) is not None

    result = json.loads(orchestrator._action_close(session_id, "ariadna"))

    assert orchestrator.agora_registry.get(session_id) is None, (
        f"La sesión debería haber sido eliminada del registry"
    )
    assert result.get("status") == "closed", (
        f"Esperado status 'closed', obtenido: {result}"
    )
    results[-1] = "✅ Test 3 — close: sesión eliminada"


test("Test 3 — close: sesión eliminada", test_close_removes_session)


# ── Reporte ─────────────────────────────────────────────────────────────────

print()
for r in results:
    print(r)
print()

total = passed + failed
if failed == 0:
    print(f"--- {total}/{total} TESTS PASARON ---")
else:
    print(f"--- {passed}/{total} PASARON, {failed} FALLARON ---")
    sys.exit(1)
