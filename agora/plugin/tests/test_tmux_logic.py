import unittest
from unittest.mock import patch, MagicMock
import subprocess
import os
import sys
from pathlib import Path

# Setup path to import orchestrator
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

# Mock basic setup before importing orchestrator if necessary
os.environ['HERMES_HOME'] = str(REPO_ROOT / "profiles/hermes")

# Ensure PYTHONPATH is set for PyYAML if needed
if "/home/jules/.local/share/pipx/venvs/conan/lib/python3.12/site-packages" not in sys.path:
    sys.path.append("/home/jules/.local/share/pipx/venvs/conan/lib/python3.12/site-packages")

try:
    from agora.plugin import _orchestrator
except ImportError:
    # Fallback if imports are still tricky
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "agora.plugin._orchestrator",
        str(REPO_ROOT / "agora/plugin/_orchestrator.py")
    )
    _orchestrator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_orchestrator)

class TestTmuxLogic(unittest.TestCase):
    @patch('subprocess.run')
    def test_check_tmux_available_success(self, mock_run):
        # Mock successful tmux -V execution
        mock_run.return_value = MagicMock(returncode=0)

        result = _orchestrator._check_tmux_available()

        self.assertTrue(result)
        mock_run.assert_called_once_with(
            ["tmux", "-V"],
            capture_output=True, text=True, timeout=5
        )

    @patch('subprocess.run')
    def test_check_tmux_available_not_found(self, mock_run):
        # Mock FileNotFoundError (tmux not in PATH)
        mock_run.side_effect = FileNotFoundError

        result = _orchestrator._check_tmux_available()

        self.assertFalse(result)

    @patch('subprocess.run')
    def test_check_tmux_available_failure(self, mock_run):
        # Mock non-zero return code
        mock_run.return_value = MagicMock(returncode=1)

        result = _orchestrator._check_tmux_available()

        self.assertFalse(result)

    @patch('subprocess.run')
    def test_check_tmux_available_timeout(self, mock_run):
        # Mock timeout
        mock_run.side_effect = subprocess.TimeoutExpired(["tmux", "-V"], timeout=5)

        result = _orchestrator._check_tmux_available()

        self.assertFalse(result)

    @patch('subprocess.run')
    def test_check_tmux_available_oserror(self, mock_run):
        # Mock general OSError
        mock_run.side_effect = OSError

        result = _orchestrator._check_tmux_available()

        self.assertFalse(result)

if __name__ == '__main__':
    unittest.main()
