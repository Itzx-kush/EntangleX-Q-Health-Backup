"""Vercel Python entrypoint for the existing FastAPI application.

The backend remains in backend/app; this module only makes the ASGI app
available to Vercel's Python Function runtime.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.main import app  # noqa: E402,F401
