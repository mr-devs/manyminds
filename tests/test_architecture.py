"""Module boundaries: the core never depends on the interface toolkit."""

import ast
import subprocess
import sys
from pathlib import Path

import manyminds.core

CORE = Path(manyminds.core.__file__).parent


def imported_modules(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_core_has_modules_to_check() -> None:
    assert len(list(CORE.rglob("*.py"))) >= 5


def test_no_core_module_imports_nicegui_or_the_ui_package() -> None:
    offenders = []
    for path in sorted(CORE.rglob("*.py")):
        for name in imported_modules(path.read_text()):
            if name.split(".")[0] == "nicegui" or name.startswith("manyminds.ui"):
                offenders.append(f"{path.relative_to(CORE)} imports {name}")

    assert offenders == []


def test_importing_every_core_module_does_not_load_nicegui() -> None:
    modules = sorted(
        "manyminds.core." + ".".join(path.relative_to(CORE).with_suffix("").parts)
        for path in CORE.rglob("*.py")
        if path.name != "__init__.py"
    )
    program = (
        "import importlib, sys\n"
        f"for name in {modules!r}:\n"
        "    importlib.import_module(name)\n"
        "loaded = sorted(m for m in sys.modules if m.split('.')[0] in ('nicegui', 'fastapi'))\n"
        "print(len(sys.modules), loaded)\n"
        "sys.exit(1 if loaded else 0)\n"
    )

    done = subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, timeout=60, check=False
    )

    assert done.returncode == 0, done.stdout + done.stderr
    assert "manyminds.core.fake" in modules
