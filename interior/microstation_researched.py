import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for module_name in ('privacy', 'gherkin', 'interior.geometry', 'interior.generator', 'interior.researched',
                    'interior.validation', 'interior.validation_researched', 'microstation_gherkin', 'interior.microstation_interior'):
    if module_name in sys.modules:
        importlib.reload(sys.modules[module_name])
from interior.microstation_interior import build

if __name__ == '__main__':
    build(ROOT / 'interior/parameters-researched.json', ROOT / 'research/parameters-exterior.json')
