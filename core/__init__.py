"""
Tamil Nadu Lead Generation & Outreach Engine - Core Package
"""
import sys
from pathlib import Path

CORE_DIR = Path(__file__).parent.resolve()
BASE_DIR = CORE_DIR.parent.resolve()

for p in [str(CORE_DIR), str(BASE_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)
