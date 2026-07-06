"""Shared pytest path setup for the sidecar test suite."""

import sys
from pathlib import Path

# Make the receipt_scanner package importable when running pytest from
# anywhere (the package lives one level up from this tests/ dir).
SIDECAR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SIDECAR_DIR))
