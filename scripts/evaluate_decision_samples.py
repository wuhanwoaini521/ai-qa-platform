#!/usr/bin/env python3
"""Offline evaluator for JSON decision samples; no model/provider calls are made."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from app.services.decision_sample_evaluation import evaluate_decision_samples


def _load_samples(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = [json.loads(line) for line in text.splitlines() if line.strip()]

    if isinstance(payload, list):
        samples = payload
    elif isinstance(payload, dict):
        samples = next(
            (payload[key] for key in ("decision_samples", "samples", "records", "rows") if key in payload),
            [payload],
        )
    else:
        raise ValueError("Input must be a JSON array, JSONL file, or an object containing decision_samples.")
    if not isinstance(samples, list) or any(not isinstance(item, dict) for item in samples):
        raise ValueError("Every decision sample must be a JSON object.")
    if not samples:
        raise ValueError("At least one decision sample is required.")
    return samples


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("samples", type=Path, help="JSON/JSONL decision sample file")
    parser.add_argument("--threshold", type=float, default=0.7, help="Offline advisory threshold in [0, 1]")
    parser.add_argument("--input-cost-per-million-usd", type=float)
    parser.add_argument("--output-cost-per-million-usd", type=float)
    parser.add_argument("--output", type=Path, help="Write the report to this file instead of stdout")
    args = parser.parse_args(argv)
    if not math.isfinite(args.threshold) or not 0 <= args.threshold <= 1:
        parser.error("--threshold must be a finite number between 0 and 1")
    for name in ("input_cost_per_million_usd", "output_cost_per_million_usd"):
        value = getattr(args, name)
        if value is not None and (not math.isfinite(value) or value < 0):
            parser.error(f"--{name.replace('_', '-')} must be a finite non-negative number")

    try:
        samples = _load_samples(args.samples)
        report = evaluate_decision_samples(
            samples,
            threshold=args.threshold,
            input_cost_per_million_usd=args.input_cost_per_million_usd,
            output_cost_per_million_usd=args.output_cost_per_million_usd,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    output = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
