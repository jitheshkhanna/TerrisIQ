"""Vercel serverless entry point.

Vercel's Python runtime detects the module-level `app` and serves it as an ASGI
application, so this file only has to make the package importable and hand over the
FastAPI instance defined in app/main.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The prebuilt spatial cache ships with the function while the source GeoJSON does not,
# so signature validation (which compares file mtimes) has to be skipped here.
os.environ.setdefault("TERRARISK_TRUST_CACHE", "1")

from app.main import app  # noqa: E402,F401  - re-exported for the Vercel runtime
