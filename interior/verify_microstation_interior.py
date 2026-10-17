import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from interior.microstation_interior import verify_saved

verify_saved()
