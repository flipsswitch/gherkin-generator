import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from microstation_gherkin import verify_saved


if __name__ == '__main__':
    verify_saved()
