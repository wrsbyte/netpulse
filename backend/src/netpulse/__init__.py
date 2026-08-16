"""netpulse — local, always-on network health & analysis for a single host.

``__version__`` is the single source of truth for the package version AND the data-provenance
version stamped onto every sample (``code_version``; see docs/DATA_VERSIONING.md). Bump it by DATA
impact, not code-API impact (docs/CONVENTIONS.md). pyproject reads it dynamically (hatchling), and
the runtime reads this literal directly so a bump takes effect on a plain restart.
"""

from __future__ import annotations

__version__ = "0.2.0"
