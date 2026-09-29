"""Command line entry. From the project folder: python -m whats_slow"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .demo import demo_report
from .render import render_json, render_text, write_reports
from .scan import run_scan
from .server import serve


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 9):
        print("Python 3.9 or newer is required.", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(
        prog="whats_slow",
        description="Say which programs are using this PC and whether that is enough to slow the others.",
    )
    parser.add_argument("--seconds", type=float, default=8, help="How long to watch (default 8, max 120).")
    parser.add_argument("--repeat", type=int, default=1, help="Watch this many times (default 1, max 5).")
    parser.add_argument("--demo", action="store_true", help="Print a made-up report so you can practice reading one.")
    parser.add_argument("--serve", action="store_true", help="Open a page on this PC that can run the check.")
    parser.add_argument("--port", type=int, default=8765, help="Port for --serve (default 8765).")
    parser.add_argument("--open", action="store_true", help="Open the saved HTML report in the browser.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of the text report.")
    parser.add_argument("--no-events", action="store_true", help="Skip the Windows error-log lookup.")
    parser.add_argument("--out", default="reports", help="Folder for saved reports (default: reports).")
    parser.add_argument("--version", action="store_true", help="Print the version and exit.")
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    if args.serve:
        try:
            serve("127.0.0.1", args.port)
        except KeyboardInterrupt:
            return 0
        except OSError as exc:
            print(f"Could not start the page: {exc}", file=sys.stderr)
            return 1
        return 0

    seconds = min(120.0, max(3.0, args.seconds))
    repeats = min(5, max(1, args.repeat))
    try:
        if args.demo:
            report = demo_report()
        else:
            report = run_scan(
                seconds=seconds,
                repeats=repeats,
                include_events=not args.no_events,
            )
    except KeyboardInterrupt:
        print("\nStopped before a report was written.", file=sys.stderr)
        return 1

    paths = write_reports(report, Path(args.out))
    if args.json:
        print(render_json(report))
    else:
        print(render_text(report))
    print(f"Saved: {paths['html']}", file=sys.stderr)
    print(f"Saved: {paths['text']}", file=sys.stderr)
    if args.open:
        webbrowser.open(paths["html"].resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
