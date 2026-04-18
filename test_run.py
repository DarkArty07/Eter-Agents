import unittest
import sys
from agora.plugin.tests import test_tmux_logic
suite = unittest.TestLoader().loadTestsFromModule(test_tmux_logic)
result = unittest.TextTestRunner().run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
