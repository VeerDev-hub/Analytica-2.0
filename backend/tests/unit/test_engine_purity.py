"""Guards design rule D-08: the engine package must not import web, DB or task code."""

import ast
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[2] / "app" / "engine"
FORBIDDEN = ("fastapi", "starlette", "sqlalchemy", "celery", "redis", "boto3", "app.")


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def test_engine_has_no_forbidden_imports():
    offenders = [
        f"{py.relative_to(ENGINE_DIR)}: {name}"
        for py in ENGINE_DIR.rglob("*.py")
        for name in _imports(py)
        if name == "app" or name.startswith(FORBIDDEN)
    ]
    assert not offenders, "engine/ must stay pure:\n" + "\n".join(offenders)
