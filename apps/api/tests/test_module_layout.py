"""Layout regression guard.

The original codebase had flat modules (``app/db.py``, ``app/models.py``,
``app/schemas.py``, ``app/security.py``, ``services/audit.py``,
``services/documents.py``). The rebuild introduced packages with the same
names (``app/db/``, ``app/models/``, ``app/schemas/``) and service modules
under different names (``audit_service.py``, ``document_service.py``). During
audit, stale flat copies were found still on disk, shadowed-but-confusing.
These tests fail if any dead flat copy is ever reintroduced.
"""

from __future__ import annotations

from pathlib import Path

import app

APP_DIR = Path(app.__file__).resolve().parent

SHADOWED_FLAT_MODULES = ["db.py", "models.py", "schemas.py", "security.py"]
RENAMED_SERVICES = ["audit.py", "documents.py"]  # real: audit_service.py / document_service.py


def test_no_shadowed_flat_core_modules() -> None:
    for name in SHADOWED_FLAT_MODULES:
        assert not (APP_DIR / name).exists(), (
            f"app/{name} shadows the app/{name[:-3]}/ package — delete the flat copy"
        )


def test_no_stale_flat_service_modules() -> None:
    for name in RENAMED_SERVICES:
        assert not (APP_DIR / "services" / name).exists(), (
            f"app/services/{name} is a dead copy; the real module is "
            f"app/services/{name[:-3]}_service.py"
        )


def test_core_namespaces_resolve_to_packages() -> None:
    import app.db
    import app.models
    import app.schemas

    for module in (app.db, app.models, app.schemas):
        assert module.__file__ is not None and module.__file__.endswith("__init__.py"), (
            f"{module.__name__} resolved to a flat module, expected a package"
        )
