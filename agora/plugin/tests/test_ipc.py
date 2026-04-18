"""
Test de integración IPC para el plugin agora (Agora v5 — inbox JSON).
Verifica el mecanismo de sesión completo sin necesitar tmux, harmonia ni agentes reales.

Ejecutar:
    python agora/plugin/tests/test_ipc.py
"""

import json
import os
import sys
import time
import importlib.util
from pathlib import Path

# ── Path setup (portable) ──────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[3]   # ~/.hermes/ or project root
AGORA_DIR = REPO_ROOT / "agora"

sys.path.insert(0, str(REPO_ROOT))

# HERMES_HOME apunta al profile hermes dentro del repo
os.environ.setdefault('HOME', str(Path.home()))
os.environ['HERMES_HOME'] = str(REPO_ROOT / "profiles" / "hermes")

# --- Cargar _orchestrator.py directamente ---
spec_orch = importlib.util.spec_from_file_location(
    'agora.plugin._orchestrator',
    str(AGORA_DIR / "plugin" / "_orchestrator.py")
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


# ── Test 1 — Ciclo completo inbox JSON: mock escritura/lectura ──────────────

def test_full_inbox_cycle():
    """
    Verifica que el mecanismo de inbox JSON funciona:
    1. Escribir un JSON al inbox de un agente simulado
    2. Leer el JSON del inbox
    3. Verificar que el contenido es correcto
    """
    import threading

    inbox_dir = orchestrator.IPC_DIR / "test_agent"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    test_data = {"role": "assistant", "content": "Hola desde mock Ariadna"}
    inbox_file = inbox_dir / "response.json"

    def mock_writer():
        time.sleep(0.1)
        # Atomic write (tmp + rename, como hace Agora v5)
        tmp = inbox_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(test_data))
        tmp.rename(inbox_file)

    def mock_reader():
        # Polling simple para simular orchestrator.wait
        for _ in range(50):
            if inbox_file.exists():
                content = inbox_file.read_text()
                result["response"] = json.loads(content)
                inbox_file.unlink(missing_ok=True)
                return
            time.sleep(0.1)

    result = {"response": None}

    t_writer = threading.Thread(target=mock_writer, daemon=True)
    t_reader = threading.Thread(target=mock_reader, daemon=True)

    t_reader.start()
    t_writer.start()

    t_reader.join(timeout=5)
    t_writer.join(timeout=5)

    assert result["response"] is not None, "No se recibió respuesta del inbox"
    assert result["response"]["content"] == "Hola desde mock Ariadna", \
        f"Contenido inesperado: {result['response']}"
    results[-1] = "✅ Test 1 — ciclo completo inbox JSON: mensaje recibido correctamente"


test("Test 1 — ciclo completo inbox JSON: mensaje recibido correctamente", test_full_inbox_cycle)


# ── Test 2 — discover agents ────────────────────────────────────────────────

def test_discover():
    """Verifica que discover retorna JSON válido con agentes."""
    raw = orchestrator._action_discover("?")
    data = json.loads(raw)
    assert "agents" in data, f"sin campo 'agents': {data}"
    assert "count" in data, f"sin campo 'count': {data}"
    assert data["count"] >= 1, f"count es {data['count']}, se esperaba >= 1"
    results[-1] = f"✅ Test 2 — discover: {data['count']} agentes encontrados"


test("Test 2 — discover: agentes disponibles", test_discover)


# ── Test 3 — close sin sesión → SessionNotFound ─────────────────────────────

def test_close_no_session():
    """
    Llama _action_close con un session_id inexistente.
    Debe retornar error: SessionNotFound.
    """
    result = json.loads(orchestrator._action_close("nonexistent_session", "ariadna"))
    assert result.get("error") == "SessionNotFound", \
        f"Esperado error 'SessionNotFound', obtenido: {result}"
    results[-1] = "✅ Test 3 — close sin sesión → SessionNotFound"


test("Test 3 — close sin sesión → SessionNotFound", test_close_no_session)


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