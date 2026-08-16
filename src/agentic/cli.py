from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from agentic.config import load_settings
from agentic.locks import AlreadyRunningError


def _print(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _json(payload: Any) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentic")
    sub = parser.add_subparsers(dest="command", required=True)

    loop_cmd = sub.add_parser("loop", help="loop de saúde em execução na main")
    loop_cmd.add_argument("--once", action="store_true")
    loop_cmd.add_argument("--interval", type=int, default=0)

    status_cmd = sub.add_parser("status", help="saúde das ferramentas + ledger")

    improve_cmd = sub.add_parser("improve", help="map / develop / review")
    improve_cmd.add_argument("action", choices=["status", "map", "develop", "review"])
    improve_cmd.add_argument("--no-apply", action="store_true")

    integrity_cmd = sub.add_parser("integrity", help="checks git + systemd + kill switch")
    integrity_cmd.add_argument("--no-systemd", action="store_true")
    integrity_cmd.add_argument("--output")

    aro_cmd = sub.add_parser("aro", help="ciclo ARO (observar / pausar)")
    aro_cmd.add_argument("action", choices=["status", "cycle", "stop", "resume"])

    mail_cmd = sub.add_parser("mail", help="caixa ARO AgentMail")
    mail_cmd.add_argument("action", choices=["status", "verify"])
    mail_cmd.add_argument("--otp", default="")

    args = parser.parse_args(argv)
    settings = load_settings()
    if args.command == "loop":
        from dataclasses import replace
        from agentic.loop import run_loop

        if args.interval:
            settings = replace(settings, interval_seconds=max(15, int(args.interval)))
        return run_loop(settings, once=args.once)
    if args.command == "status":
        from agentic.improve import run_action
        from agentic.loop import collect_census

        payload = {
            "tools": collect_census(settings.root).get("tools"),
            "improve": run_action(settings, "status"),
        }
        return _json(payload)
    if args.command == "improve":
        from agentic.improve import run_action
        from agentic.improve_git import GitError

        try:
            result = run_action(
                settings,
                args.action,
                progress=_print,
                apply=False if args.no_apply else None,
            )
        except AlreadyRunningError as exc:
            _print(str(exc))
            return 1
        except GitError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return _json(result)
    if args.command == "integrity":
        from agentic.integrity import run_and_store
        from pathlib import Path

        report = run_and_store(
            settings.root,
            systemd=not args.no_systemd,
            path=Path(args.output) if args.output else None,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0 if report.get("ok") else 1
    if args.command == "aro":
        from agentic.aro.constitution import STOP_COMMAND, STOP_FILENAME
        from agentic.aro.cycle import run_cycle

        stop = settings.root / STOP_FILENAME
        if args.action == "stop":
            stop.write_text(STOP_COMMAND + "\n", encoding="utf-8")
            return _json({"ok": True, "paused": True, "command": STOP_COMMAND})
        if args.action == "resume":
            if stop.exists():
                stop.unlink()
            return _json({"ok": True, "paused": False, "command": "resume"})
        report = run_cycle(settings.root)
        if args.action == "status":
            slim = {
                "ok": report.get("ok"),
                "paused": report.get("paused"),
                "ready_for_outbound": report.get("ready_for_outbound"),
                "constitution_ok": report.get("constitution_ok"),
                "payout_destination_configured": report.get("payout_destination_configured"),
                "financial_limits_configured": report.get("financial_limits_configured"),
                "offers": report.get("offers"),
                "decision": report.get("decision"),
                "note": report.get("note"),
            }
            return _json(slim)
        return _json(report)
    if args.command == "mail":
        from agentic.mail import status as mail_status
        from agentic.mail import verify_otp

        if args.action == "verify":
            return _json(verify_otp(args.otp))
        payload = mail_status()
        return _json(payload)
    parser.error("comando desconhecido")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
