"""Plain-text and single-file HTML reports."""

from __future__ import annotations

import html
import json
from pathlib import Path

from . import __version__
from .analyze import human_bytes, human_rate
from .model import Program, Report

JUDGING = [
    "Run this while the PC actually feels slow. A check taken when everything feels fine will look fine.",
    "One pass is a snapshot. If a program is listed as slowing others, run again for 20 seconds, three times (see the instructions). High every time means a real load. High once means a spike, such as an update or a scan.",
    "Processor percent here is the share of the whole PC, not of one core. Task Manager often shows a bigger number for the same process because 100% there can mean a single core.",
    "A single Windows error is usually one crash. It does not, by itself, slow the rest of the PC. Several errors every minute can, when they come from a program other software waits on (file sync, search, File Explorer, security, updates).",
    "This check does not see which browser tab, and it does not see inside a program's private errors unless Windows wrote them to the event log.",
    "It does not measure internet speed. If the processor is mostly free and only websites feel slow, the network or the site is the problem.",
    "Nothing is closed or changed. You decide what to quit.",
]

_LABEL = {
    "blocking": "Slowing other programs a lot",
    "slowing": "Slowing other programs",
    "mild": "Worth watching",
    "fine": "Not in the way",
}


def render_text(report: Report) -> str:
    lines: list[str] = []
    lines.append("WHAT IS SLOWING THIS PC")
    lines.append("=" * 72)
    if report.demo:
        lines.append("DEMO DATA. This is a made-up PC so you can practice reading a report.")
        lines.append("It is not your computer.")
        lines.append("")
    lines.append(f"When: {report.sampled_at}")
    lines.append(f"Computer: {report.hostname}  ·  {report.os_label}")
    watched = _watched_phrase(report)
    lines.append(
        f"Watched for {watched}. {report.system.cpu_count} processor cores, "
        f"{human_bytes(report.system.ram_total)} RAM, "
        f"memory {report.system.ram_percent:.0f}% full, "
        f"processor {report.system.cpu_percent:.0f}% busy."
    )
    lines.append("")
    lines.append("SUMMARY")
    lines.append("-" * 72)
    for line in report.headlines:
        lines.append(_wrap(line))
        lines.append("")
    if report.notes:
        lines.append("WHOLE-PC CONDITIONS")
        lines.append("-" * 72)
        for note in report.notes:
            lines.append(_wrap("• " + note))
            lines.append("")
    slowing = [p for p in report.programs if _bucket(p) in {"blocking", "slowing"}]
    watching = [p for p in report.programs if _bucket(p) == "mild"]
    lines.append("SLOWING OTHER PROGRAMS")
    lines.append("-" * 72)
    if not slowing:
        lines.append("None during this check.")
        lines.append("")
    for index, program in enumerate(slowing, start=1):
        lines.extend(_program_block(index, program))
    if watching:
        lines.append("WORTH WATCHING")
        lines.append("-" * 72)
        lines.append("These are using something, but not enough on their own to freeze the PC.")
        lines.append("")
        for index, program in enumerate(watching[:8], start=1):
            lines.extend(_program_block(index, program))
        extra = len(watching) - 8
        if extra > 0:
            lines.append(f"{extra} more programs are in this lighter range and are not listed.")
            lines.append("")
    lines.append("QUIET PROGRAMS")
    lines.append("-" * 72)
    lines.append(
        f"{report.quiet_count} other programs were using too little to get in the way. They are not listed."
    )
    lines.append("")
    lines.append("WHAT TO DO NEXT")
    lines.append("-" * 72)
    for step in report.steps:
        lines.append(_wrap("• " + step))
        lines.append("")
    if report.own_note:
        lines.append(_wrap(report.own_note))
        lines.append("")
    lines.append("HOW TO JUDGE THIS REPORT")
    lines.append("-" * 72)
    for item in JUDGING:
        lines.append(_wrap("• " + item))
        lines.append("")
    lines.append(
        "The impact number (out of 100) only ranks programs against each other. "
        "It is not a health grade and it is not a virus score. Read the sentences."
    )
    lines.append(f"whats-slow {__version__}. Read-only. No data leaves this PC.")
    lines.append("")
    return "\n".join(lines)


def render_html(report: Report, banner_html: str = "") -> str:
    slowing = [p for p in report.programs if _bucket(p) in {"blocking", "slowing"}]
    watching = [p for p in report.programs if _bucket(p) == "mild"]
    demo = ""
    if report.demo:
        demo = (
            "<p class='demo'>Demo data. This is a made-up PC so you can practice "
            "reading a report. It is not your computer.</p>"
        )
    sections = [
        "<!DOCTYPE html>",
        "<html lang='en'>",
        "<head>",
        "<meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>What is slowing this PC</title>",
        "<style>",
        _CSS,
        "</style>",
        "</head>",
        "<body>",
        "<main>",
        banner_html,
        "<header>",
        "<p class='eyebrow'>Read-only check · nothing was closed or changed</p>",
        "<h1>What is slowing this PC</h1>",
        demo,
        "<p class='meta'>",
        html.escape(report.sampled_at),
        " · ",
        html.escape(report.hostname),
        " · ",
        html.escape(report.os_label),
        "</p>",
        "<p class='meta'>",
        html.escape(
            f"Watched for {_watched_phrase(report)}. "
            f"{report.system.cpu_count} cores, {human_bytes(report.system.ram_total)} RAM, "
            f"memory {report.system.ram_percent:.0f}% full, processor {report.system.cpu_percent:.0f}% busy."
        ),
        "</p>",
        "</header>",
        "<section class='summary'>",
        "<h2>Summary</h2>",
    ]
    for line in report.headlines:
        sections.append(f"<p>{html.escape(line)}</p>")
    sections.append("</section>")
    if report.notes:
        sections.append("<section><h2>Whole-PC conditions</h2><ul>")
        for note in report.notes:
            sections.append(f"<li>{html.escape(note)}</li>")
        sections.append("</ul></section>")
    sections.append("<section><h2>Slowing other programs</h2>")
    if not slowing:
        sections.append("<p>None during this check.</p>")
    for program in slowing:
        sections.append(_card(program))
    sections.append("</section>")
    if watching:
        sections.append("<section><h2>Worth watching</h2>")
        sections.append("<p>Using something, but not enough on their own to freeze the PC.</p>")
        for program in watching[:8]:
            sections.append(_card(program))
        sections.append("</section>")
    sections.append("<section><h2>What to do next</h2><ol>")
    for step in report.steps:
        sections.append(f"<li>{html.escape(step)}</li>")
    sections.append("</ol></section>")
    sections.append(
        f"<p class='quiet'>{report.quiet_count} other programs were too quiet to list.</p>"
    )
    if report.own_note:
        sections.append(f"<p class='quiet'>{html.escape(report.own_note)}</p>")
    sections.append("<section><h2>How to judge this report</h2><ul>")
    for item in JUDGING:
        sections.append(f"<li>{html.escape(item)}</li>")
    sections.append("</ul>")
    sections.append(
        "<p>The impact number only ranks programs against each other. "
        "It is not a health grade and it is not a virus score. Read the sentences.</p>"
        "</section>"
    )
    sections.append(
        f"<footer>whats-slow {html.escape(__version__)}. "
        "The report stays on this PC. No usage data is sent anywhere.</footer>"
    )
    sections.append("</main></body></html>")
    return "\n".join(sections)


def render_json(report: Report) -> str:
    payload = {
        "tool": "whats-slow",
        "version": __version__,
        "demo": report.demo,
        "sampled_at": report.sampled_at,
        "hostname": report.hostname,
        "os": report.os_label,
        "duration_seconds": round(report.duration_s, 1),
        "repeats": report.repeat_count,
        "processor_busy_percent": round(report.system.cpu_percent, 1),
        "memory_full_percent": round(report.system.ram_percent, 1),
        "headlines": report.headlines,
        "conditions": report.notes,
        "next_steps": report.steps,
        "programs": [_program_json(p) for p in report.programs if _bucket(p) != "fine"],
        "quiet_program_count": report.quiet_count,
    }
    return json.dumps(payload, indent=2)


def write_reports(report: Report, directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = _stamp(report)
    html_path = directory / f"slow-report-{stamp}.html"
    text_path = directory / f"slow-report-{stamp}.txt"
    json_path = directory / f"slow-report-{stamp}.json"
    html_path.write_text(render_html(report), encoding="utf-8")
    text_path.write_text(render_text(report), encoding="utf-8")
    json_path.write_text(render_json(report), encoding="utf-8")
    latest = directory / "latest.html"
    latest.write_text(html_path.read_text(encoding="utf-8"), encoding="utf-8")
    return {"html": html_path, "text": text_path, "json": json_path, "latest": latest}


def _program_json(program: Program) -> dict:
    return {
        "program": program.display_name,
        "verdict": _LABEL[_bucket(program)],
        "impact": program.impact,
        "processes": program.count,
        "exe": program.exe_path or program.exe_name,
        "service": program.service,
        "cpu_share_percent": round(program.cpu_share, 1),
        "cpu_share_peak_percent": round(program.cpu_share_peak, 1),
        "memory_bytes": program.rss,
        "memory_percent": round(program.mem_percent, 1),
        "disk_read_bytes_per_sec": round(program.read_bps),
        "disk_write_bytes_per_sec": round(program.write_bps),
        "hung_windows": program.hung_count,
        "windows_errors": len(program.events),
        "high_in_samples": program.high_samples,
        "samples": program.total_samples,
        "sentences": program.sentences,
    }


def _card(program: Program) -> str:
    bucket = _bucket(program)
    cpu = min(100.0, program.cpu_share)
    mem = min(100.0, program.mem_percent)
    disk = program.read_bps + program.write_bps
    disk_pct = min(100.0, disk / (70 * 1024 * 1024) * 100.0)
    sentences = "".join(f"<p>{html.escape(s)}</p>" for s in program.sentences)
    return (
        f"<article class='card {bucket}'>"
        f"<div class='card-top'><h3>{html.escape(program.display_name)}</h3>"
        f"<span class='pill {bucket}'>{html.escape(_LABEL[bucket])}</span></div>"
        f"<p class='impact'>Impact {program.impact} out of 100 · {program.count} "
        f"process{'es' if program.count != 1 else ''}</p>"
        f"{sentences}"
        f"<div class='meters'>"
        f"{_meter('Processor', cpu, f'{program.cpu_share:.0f}% of the PC')}"
        f"{_meter('Memory', mem, human_bytes(program.rss))}"
        f"{_meter('Disk', disk_pct, human_rate(disk) if program.io_known else 'not visible')}"
        f"</div></article>"
    )


def _meter(label: str, pct: float, caption: str) -> str:
    width = max(0.0, min(100.0, pct))
    return (
        "<div class='meter'>"
        f"<div class='meter-label'><span>{html.escape(label)}</span>"
        f"<span>{html.escape(caption)}</span></div>"
        f"<div class='track'><span style='width:{width:.1f}%'></span></div>"
        "</div>"
    )


def _program_block(index: int, program: Program) -> list[str]:
    bucket = _bucket(program)
    lines = [
        f"{index}. {program.display_name} — {_LABEL[bucket]} (impact {program.impact} of 100)",
    ]
    for sentence in program.sentences:
        lines.append(_wrap("   " + sentence))
    lines.append("")
    return lines


def _bucket(program: Program) -> str:
    if program.severity in {"blocking", "slowing"}:
        return program.severity
    if (
        program.total_samples > 1
        and program.peak_severity in {"blocking", "slowing"}
        and program.severity == "fine"
    ):
        return "mild"
    return program.severity if program.severity in _LABEL else "fine"


def _watched_phrase(report: Report) -> str:
    seconds = report.duration_s
    base = f"{seconds:.0f} seconds" if seconds < 70 else f"{seconds / 60:.0f} minutes"
    if report.repeat_count > 1:
        return f"{base} across {report.repeat_count} samples"
    return base


def _stamp(report: Report) -> str:
    from datetime import datetime

    del report
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _wrap(text: str, width: int = 78) -> str:
    import textwrap

    prefix = ""
    body = text
    if text.startswith("• "):
        prefix = "• "
        body = text[2:]
        return textwrap.fill(body, width=width, initial_indent="• ", subsequent_indent="  ")
    if text.startswith("   "):
        return textwrap.fill(text.strip(), width=width, initial_indent="   ", subsequent_indent="   ")
    return textwrap.fill(text, width=width)


_CSS = """
:root {
  color-scheme: light;
  --ink: #1c1915;
  --muted: #5c564c;
  --paper: #f6f3ec;
  --card: #fffdf8;
  --line: #e3dccf;
  --block: #8c2f2f;
  --slow: #8a5a00;
  --mild: #2f5d50;
  --fine: #3d4a3f;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font: 18px/1.5 "Segoe UI", "Source Sans 3", Helvetica, Arial, sans-serif;
}
main { max-width: 820px; margin: 0 auto; padding: 32px 20px 64px; }
h1 { font-size: 2.1rem; line-height: 1.15; margin: 0 0 8px; letter-spacing: -0.02em; }
h2 { font-size: 1.35rem; margin: 0 0 10px; }
h3 { font-size: 1.25rem; margin: 0; }
.eyebrow { text-transform: uppercase; letter-spacing: 0.08em; font-size: 0.78rem; color: var(--muted); margin: 0 0 8px; }
.meta, .quiet, footer { color: var(--muted); }
.demo { background: #fff4d6; border: 1px solid #e6d39a; padding: 10px 12px; border-radius: 10px; }
.summary { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 8px 18px 4px; margin: 18px 0; }
section { margin: 28px 0; }
.card { background: var(--card); border: 1px solid var(--line); border-left: 6px solid var(--mild); border-radius: 14px; padding: 16px 16px 8px; margin: 12px 0 16px; }
.card.blocking { border-left-color: var(--block); }
.card.slowing { border-left-color: var(--slow); }
.card-top { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; flex-wrap: wrap; }
.pill { font-size: 0.82rem; font-weight: 650; border-radius: 999px; padding: 3px 10px; background: #e7efe9; color: var(--mild); }
.pill.blocking { background: #f8e4e4; color: var(--block); }
.pill.slowing { background: #f8efd8; color: var(--slow); }
.impact { color: var(--muted); margin-top: 6px; }
.meters { display: grid; gap: 8px; margin: 8px 0 12px; }
.meter-label { display: flex; justify-content: space-between; gap: 12px; font-size: 0.92rem; color: var(--muted); }
.track { height: 8px; background: #efeae0; border-radius: 99px; overflow: hidden; }
.track span { display: block; height: 100%; background: #3f5e52; border-radius: 99px; }
ul, ol { padding-left: 1.2rem; }
li { margin: 0.4rem 0; }
form.check { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; background: var(--card); border: 1px solid var(--line); padding: 14px; border-radius: 14px; margin-bottom: 18px; }
label { display: flex; flex-direction: column; font-size: 0.9rem; color: var(--muted); gap: 4px; }
input { font: inherit; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--line); color: var(--ink); background: white; width: 6rem; }
button { font: inherit; background: #24352c; color: white; border: 0; border-radius: 10px; padding: 10px 16px; cursor: pointer; }
button:hover { background: #1a2820; }
footer { margin-top: 28px; font-size: 0.92rem; }
@media (max-width: 640px) {
  body { font-size: 17px; }
  h1 { font-size: 1.7rem; }
  main { padding: 20px 14px 48px; }
}
"""
