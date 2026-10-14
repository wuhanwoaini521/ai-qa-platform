from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "apps" / "web" / "src" / "api" / "openapi.json"
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.main import app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export the FastAPI OpenAPI contract consumed by the web client.")
    parser.add_argument("--check", action="store_true", help="fail if the committed OpenAPI file is stale")
    args = parser.parse_args()
    content = json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != content:
            print(f"OpenAPI contract is stale: run {Path(__file__).relative_to(ROOT)}")
            return 1
        print("OpenAPI contract is current")
        return 0
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
