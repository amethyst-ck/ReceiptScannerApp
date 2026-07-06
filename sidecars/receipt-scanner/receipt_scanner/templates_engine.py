"""
Stage 2 enrichment: invoice2data template matching.

Loaded templates are matched by keyword against raw_text. The first
template whose keywords all match wins; its `fields` regexes extract
higher-fidelity values that overlay the generic baseline.

Templates are enrichment, not gatekeepers — Stage 2 always returns a
generic baseline; templates just improve specific recurring vendors.
"""

import logging
from pathlib import Path
from typing import Any, Optional


_log = logging.getLogger(__name__)

# Templates ship alongside the package so the Docker image bundles them.
TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"

try:
    from invoice2data.extract.loader import read_templates
except ImportError:
    read_templates = None

# Whether the invoice2data strategy can run at all (reported by /health).
INVOICE2DATA_AVAILABLE = read_templates is not None


def _load_templates() -> list:
    """Load templates from TEMPLATES_DIR. Returns [] if dir missing or empty."""
    if read_templates is None or not TEMPLATES_DIR.exists():
        return []
    try:
        return read_templates(str(TEMPLATES_DIR))
    except Exception:
        _log.warning("failed to load templates from %s", TEMPLATES_DIR, exc_info=True)
        return []


_TEMPLATES = _load_templates()


def template_count() -> int:
    """Number of invoice2data templates loaded at import time."""
    return len(_TEMPLATES)


def template_names() -> list[str]:
    """Names of the loaded templates (for /health diagnostics)."""
    return [_template_name(t) for t in _TEMPLATES]


def _template_name(tpl: Any) -> str:
    """Pull a usable name out of an invoice2data template dict-like object."""
    # invoice2data templates are dict-like; "template_name" is set by the loader.
    if hasattr(tpl, "get"):
        return tpl.get("template_name") or tpl.get("issuer") or "unknown"
    return getattr(tpl, "template_name", "unknown")


def extract_with_templates(text: str) -> Optional[dict]:
    """
    Try each loaded template. Returns the first match's structured fields
    plus the template name, or None if no template's keywords match.
    """
    for tpl in _TEMPLATES:
        try:
            if not tpl.matches_input(text):
                continue
            fields = tpl.extract(text)
        except Exception:
            continue
        if fields:
            return {"template": _template_name(tpl), "fields": fields}
    return None
