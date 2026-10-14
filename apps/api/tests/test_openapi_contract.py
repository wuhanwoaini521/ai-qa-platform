import json
from pathlib import Path

from app.main import app


def test_committed_openapi_contract_matches_fastapi():
    contract = Path(__file__).resolve().parents[2] / "web" / "src" / "api" / "openapi.json"
    assert json.loads(contract.read_text(encoding="utf-8")) == app.openapi()
