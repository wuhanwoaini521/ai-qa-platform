#!/usr/bin/env python3
"""Verify that every translation namespace has the same keys in every language.

A missing key is a real defect: the UI either falls back to English silently or renders the raw key.
Run from `scripts/lint` so it fails CI rather than production.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parents[1] / "apps" / "web" / "src" / "i18n" / "locales"


def flatten(payload: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            keys |= flatten(value, path)
        else:
            keys.add(path)
    return keys


#: `t('key')`, `t("ns:key")`, `i18n.t('key', { ns: 'ns' })` — literals only; dynamic keys are skipped.
TRANSLATION_CALL = re.compile(r"""\bt\(\s*['"]([^'"]+)['"]""")
RENDER_TRANSLATION_CALL = re.compile(r"""<Trans[^>]*\bi18nKey=['"]([^'"]+)['"]""")


def source_keys(web_root: Path) -> set[tuple[str, str]]:
    """(namespace, key) pairs referenced by literal translation calls in the web sources."""
    found: set[tuple[str, str]] = set()
    for path in web_root.rglob("*.tsx"):
        if any(part in {"node_modules", "dist", ".vite"} for part in path.parts):
            continue
        for pattern in (TRANSLATION_CALL, RENDER_TRANSLATION_CALL):
            for match in pattern.finditer(path.read_text(encoding="utf-8", errors="replace")):
                reference = match.group(1)
                if ":" in reference:
                    namespace, _, key = reference.partition(":")
                    found.add((namespace, key))
                else:
                    # A bare key belongs to the file's own namespace, which cannot be known statically.
                    found.add(("", reference))
    return found


def main() -> int:
    if not LOCALES_DIR.is_dir():
        print(f"i18n locales directory not found: {LOCALES_DIR}")
        return 1

    languages = sorted(entry.name for entry in LOCALES_DIR.iterdir() if entry.is_dir())
    if len(languages) < 2:
        print(f"expected at least two languages, found: {languages}")
        return 1

    namespaces = sorted({path.stem for path in LOCALES_DIR.glob("*/*.json")})
    missing_files: list[str] = []
    failures: list[str] = []

    for namespace in namespaces:
        keys_by_language: dict[str, set[str]] = {}
        for language in languages:
            path = LOCALES_DIR / language / f"{namespace}.json"
            if not path.is_file():
                missing_files.append(f"{language}/{namespace}.json")
                keys_by_language[language] = set()
                continue
            try:
                keys_by_language[language] = flatten(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError as error:
                failures.append(f"{language}/{namespace}.json is not valid JSON: {error}")
                keys_by_language[language] = set()

        reference_language = languages[0]
        reference = keys_by_language[reference_language]
        for language in languages[1:]:
            keys = keys_by_language[language]
            for key in sorted(reference - keys):
                failures.append(f"{language}/{namespace}.json is missing key '{key}'")
            for key in sorted(keys - reference):
                failures.append(f"{reference_language}/{namespace}.json is missing key '{key}'")

    if missing_files:
        failures.extend(f"missing translation file: {entry}" for entry in missing_files)

    # Every literal key used by a component must exist in the resources, in every language.
    known_keys = {
        (namespace, key)
        for namespace in namespaces
        for key in flatten(json.loads((LOCALES_DIR / languages[0] / f"{namespace}.json").read_text(encoding="utf-8")))
    }
    known_by_key = {key for _namespace, key in known_keys}
    # Only the application sources, never node_modules or a previous build.
    web_root = LOCALES_DIR.parents[1]
    for namespace, key in sorted(source_keys(web_root)):
        if namespace:
            if (namespace, key) not in known_keys:
                failures.append(f"component references '{namespace}:{key}' but no such translation exists")
        elif key not in known_by_key:
            failures.append(f"component references '{key}' but no namespace defines it")

    if failures:
        print(f"i18n check failed ({len(failures)} problem(s)):")
        for failure in failures[:80]:
            print(f"  - {failure}")
        if len(failures) > 80:
            print(f"  ... and {len(failures) - 80} more")
        return 1

    total_keys = sum(
        len(flatten(json.loads((LOCALES_DIR / languages[0] / f"{ns}.json").read_text(encoding="utf-8"))))
        for ns in namespaces
    )
    print(f"i18n check passed: {len(namespaces)} namespace(s), {len(languages)} language(s), {total_keys} keys")
    return 0


if __name__ == "__main__":
    sys.exit(main())
