"""Minimal stdlib CLI: screen the seeded declarations, or verify the audit chain (argparse)."""

from __future__ import annotations

import argparse
import sys

from ..adapters.controls import RecordingReviewRouter
from ..assembly import assessment_service


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="conflicts_gifts_pad_register")
    sub = parser.add_subparsers(dest="command", required=True)

    screen_cmd = sub.add_parser("screen", help="Screen the seeded declarations for a tenant.")
    screen_cmd.add_argument("--tenant", default="demo-bank")
    screen_cmd.add_argument("--actor", default="cli-user@bank.example")

    args = parser.parse_args(argv)
    container, service = assessment_service()

    if args.command == "screen":
        feed = container.declaration_feed.declarations(args.tenant)
        trades = container.brokerage_feed.pad_trades(args.tenant)
        for declaration in (*feed, *trades):
            result = service.assess(declaration, actor=args.actor)
            container.register_store.put(result)
            print(f"{result.declaration_id}: {result.verdict.value} ({result.severity.value})")
            for finding in result.screening.findings:
                print(f"  fired {finding.rule_id}: {finding.reason}")
            # Rule R8 on the CLI path too: the same escalation, the same router.
            routing = RecordingReviewRouter(container.review_router)
            ref = routing.route(result, maker=args.actor, tenant=declaration.tenant)
            print(f"  human review hand-off : {routing.outcome.value} {ref}".rstrip())
        return 0

    return 2  # pragma: no cover - argparse requires a subcommand


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
