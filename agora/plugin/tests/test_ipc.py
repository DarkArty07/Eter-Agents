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

sys.path.insert(0, '$HOME/.hermes/sdk')

# Restaurar HOME al valor real para que ~ se expanda correctamente
os.environ['HOME'] = '$HOME'
os.environ['HERMES_HOME'] = '$HOME/.hermes/profiles/hermes'

# --- Cargar _orchestrator.py directamente ---
spec_orch = importlib.util.spec_from_file_location(
    'agora.plugin._orchestrator',
    '$HOME/.hermes/agora/plugin/_orchestrator.py'
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


# ── Test 2 — Timeout del thread reader ──────────────────────────────────────

def test_timeout():
    """
    Crea un pipe para "ariadna", parchea _TIMEOUT_SECONDS a 2s,
    llama _action_message — nadie escribe → debe retornar Timeout en ~2s.

    Nota: tmux send-keys falla silenciosamente.
    El thread reader bloquea indefinidamente en open(pipe, "r") hasta que
    el timeout lo interrumpe eliminando el pipe.
    """
    original_timeout = orchestrator._TIMEOUT_SECONDS
    orchestrator._TIMEOUT_SECONDS = 2

    # El código usa .pane_map para encontrar el target tmux.
    # Simulamos que _action_open registró un pane para ariadna.
    original_pane_map = dict(orchestrator._pane_map)
    orchestrator._pane_map["ariadna"] = "agora:ariadna"

    # El código usa .pipe como extensión de pipe
    pipe_path = orchestrator.IPC_DIR / "ariadna.pipe"
    orchestrator.IPC_DIR.mkdir(parents=True, exist_ok=True)

    # Cleanup previo
    if pipe_path.exists():
        os.remove(pipe_path)

    os.mkfifo(pipe_path)

    t_start = time.time()
    result = json.loads(orchestrator._action_message("ariadna", "ping"))
    elapsed = time.time() - t_start

    # Restaurar antes de los asserts para cleanup seguro
    orchestrator._TIMEOUT_SECONDS = original_timeout
    orchestrator._pane_map = original_pane_map

    # Cleanup (el timeout ya elimina el pipe, pero por si acaso)
    if pipe_path.exists():
        os.remove(pipe_path)

    assert result.get("error") == "Timeout", (
        f"Esperado Timeout, obtenido: {result}"
    )
    assert elapsed < 10, f"Tardó demasiado: {elapsed:.1f}s (esperado ~2s)"
    results[-1] = f"✅ Test 2 — timeout: retorna error en ~{elapsed:.1f}s"


test("Test 2 — timeout: retorna error en ~2s", test_timeout)


# ── Test 3 — close limpia el pipe ───────────────────────────────────────────

def test_close_removes_pipe():
    """
    Crea un FIFO para "ariadna", llama _action_close,
    verifica que el pipe fue eliminado y el resultado tiene status: closed.
    """
    # El código usa .pipe como extensión de pipe
    pipe_path = orchestrator.IPC_DIR / "ariadna.pipe"
    orchestrator.IPC_DIR.mkdir(parents=True, exist_ok=True)

    # Cleanup previo
    if pipe_path.exists():
        os.remove(pipe_path)

    os.mkfifo(pipe_path)

    assert pipe_path.exists(), "El pipe debería existir antes del close"

    result = json.loads(orchestrator._action_close("ariadna"))

    assert not pipe_path.exists(), (
        f"El pipe debería haber sido eliminado, pero aún existe: {pipe_path}"
    )
    assert result.get("status") == "closed", (
        f"Esperado status 'closed', obtenido: {result}"
    )
    results[-1] = "✅ Test 3 — close: pipe eliminado"


test("Test 3 — close: pipe eliminado", test_close_removes_pipe)


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
