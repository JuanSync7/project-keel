"""
title: Integration — test packages cannot shadow project imports
summary: Fail when a package directory anywhere under tests has the name of a top-level module or package under scripts or src.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]


def test_test_packages_do_not_shadow_project_imports():
    import_names = set()
    for code_root in (_ROOT / "scripts", _ROOT / "src"):
        if not code_root.is_dir():
            continue
        for path in code_root.iterdir():
            if path.is_file() and path.suffix == ".py" and path.stem != "__init__":
                import_names.add(path.stem)
            elif path.is_dir() and path.name.isidentifier():
                import_names.add(path.name)

    assert import_names, "No project import names found under scripts/ or src/"
    collisions = sorted(
        str(init.parent.relative_to(_ROOT))
        for init in (_ROOT / "tests").rglob("__init__.py")
        if init.parent.name in import_names
    )
    assert not collisions, (
        "Test packages shadow project imports; remove their __init__.py and use "
        "flat mirror tests instead:\n" + "\n".join(collisions)
    )
