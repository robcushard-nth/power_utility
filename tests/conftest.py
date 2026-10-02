"""Make `3_grid_simulation` importable (the directory name starts with a digit)."""
import sys
from pathlib import Path

SIM_DIR = Path(__file__).resolve().parents[1] / "3_grid_simulation"
if str(SIM_DIR) not in sys.path:
    sys.path.insert(0, str(SIM_DIR))

pytest_plugins = ["nicegui.testing.user_plugin"]
