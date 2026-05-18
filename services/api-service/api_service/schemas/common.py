"""Deprecated — D-04 hoisted to api_service.common.schemas. Do not add new symbols here.

This module is kept as an empty stub so that Python keeps the legacy package
import path resolvable (some external tooling references the module). All
exports have moved to `api_service.common.schemas`. Phase 4 / Phase 5 code
MUST import from the new path; importing the legacy per-domain envelope
class names from here will raise ImportError by design (Pitfall 8 — legacy
alias erased).
"""

from __future__ import annotations
