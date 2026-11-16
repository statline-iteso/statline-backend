import json
import os
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
# Shared JSON Schemas live at the repo root (schemas/), used by ingesta and documented for the API.
_RAIZ = Path(__file__).resolve().parents[1]
SCHEMAS_DIR = os.environ.get("TEST_SCHEMAS_DIR") or str(_RAIZ.parent.parent / "schemas")


def cargar(nombre: str) -> dict[str, Any]:
    datos: dict[str, Any] = json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))
    return datos


@pytest.fixture
def schemas_dir() -> str:
    return SCHEMAS_DIR
