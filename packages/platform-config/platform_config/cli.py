from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from platform_config import ConfigLoadError, ConfigManager, sanitize_config_value


def _runtime_state(manager: ConfigManager) -> tuple[str, str, str]:
    config = manager.get()
    ai = (
        "DISABLED"
        if not config.ai.enabled
        else "SIMULATION"
        if config.ai.provider == "fake"
        else "READY_CONFIGURED"
        if config.ai.api_key.get_secret_value()
        else "BLOCKED_MISSING_API_KEY"
    )
    jev = (
        "DISABLED"
        if not config.jev.enabled or not config.features.jev_decision
        else "READY_CONFIGURED"
        if config.jev.api_key.get_secret_value()
        else "BLOCKED_MISSING_API_KEY"
    )
    repair = (
        "DISABLED"
        if not config.repair.enabled or not config.features.ai_repair or config.repair.mode == "OFF"
        else "READY_CONFIGURED"
        if ai == "READY_CONFIGURED" and (not config.repair.require_jev or jev == "READY_CONFIGURED")
        else "BLOCKED"
    )
    return ai, jev, repair


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="platform-config")
    parser.add_argument("--config", type=Path, help="Read an alternate config file (test and migration use only).")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Validate config and summarize configured runtime readiness.")
    dump = commands.add_parser("dump", help="Print effective config with secrets redacted.")
    dump.add_argument("--effective", action="store_true", required=True)
    args = parser.parse_args(argv)

    try:
        manager = ConfigManager(args.config)
    except ConfigLoadError as error:
        print(f"Config: INVALID ({error})", file=sys.stderr)
        return 2

    if args.command == "check":
        ai, jev, repair = _runtime_state(manager)
        print(f"Config: OK ({manager.path})")
        print(f"AI: {ai}")
        print(f"Jev: {jev}")
        print(f"Repair: {repair}")
        print("Browser: CONFIGURED")
        return 0

    print(json.dumps(sanitize_config_value(manager.get().model_dump(mode="python")), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
