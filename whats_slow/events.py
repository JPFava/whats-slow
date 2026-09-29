"""Best-effort recent error events.

Windows can tell us about crashes, hung programs, and disk errors recorded in
the last few minutes. It cannot tell us about exceptions a program caught and
hid. Other operating systems get a clear 'not available' rather than a guess.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from .model import EventHit, EventInfo

WINDOW_MINUTES = 15
_FAULTING = re.compile(r"faulting application name:\s*([^\s,]+)", re.IGNORECASE)
_HUNG_PROG = re.compile(r"\bprogram\s+([^\s,]+\.exe)\b", re.IGNORECASE)
_DISK_PROVIDERS = {
    "disk",
    "ntfs",
    "storahci",
    "stornvme",
    "nvme",
    "volmgr",
    "disk ",
    "iaStorA",
    "iastora",
    "spaceport",
}


def collect_events(window_minutes: int = WINDOW_MINUTES) -> EventInfo:
    if os.name == "nt":
        return _windows_events(window_minutes)
    return EventInfo(
        available=False,
        reason=(
            "Error totals are read from the Windows event log. "
            "On this operating system the check only covers processor, memory, and disk."
        ),
        window_minutes=window_minutes,
    )


def parse_faulting_app(provider: str, message: str) -> str | None:
    text = message or ""
    match = _FAULTING.search(text)
    if match:
        return os.path.basename(match.group(1))
    if provider.lower() in {"application hang", "application error"}:
        hung = _HUNG_PROG.search(text)
        if hung:
            return os.path.basename(hung.group(1))
    return None


def is_disk_event(event: EventHit) -> bool:
    provider = (event.provider or "").strip().lower()
    if provider in _DISK_PROVIDERS or provider.startswith("disk"):
        return True
    message = (event.message or "").lower()
    if event.log.lower() == "system" and any(
        phrase in message
        for phrase in (
            "disk",
            "controller error",
            "reset to device",
            "ntfs",
            "i/o operation",
        )
    ):
        return True
    return False


def _windows_events(window_minutes: int) -> EventInfo:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if not powershell:
        return EventInfo(
            available=False,
            reason="PowerShell was not found, so Windows error events could not be read.",
            window_minutes=window_minutes,
        )
    script = f"""
$ErrorActionPreference = 'SilentlyContinue'
$start = (Get-Date).AddMinutes(-{int(window_minutes)})
$rows = @()
foreach ($log in @('Application','System')) {{
  $items = Get-WinEvent -FilterHashtable @{{LogName=$log; Level=2; StartTime=$start}} -MaxEvents 120
  foreach ($item in $items) {{
    $msg = ''
    if ($item.Message) {{
      $msg = ($item.Message -replace '\\s+', ' ')
      if ($msg.Length -gt 500) {{ $msg = $msg.Substring(0, 500) }}
    }}
    $rows += [PSCustomObject]@{{
      when = $item.TimeCreated.ToString('o')
      log = $log
      provider = [string]$item.ProviderName
      id = [int]$item.Id
      message = $msg
    }}
  }}
}}
# Hangs are often warnings, not errors. Pull them on purpose.
$hangs = Get-WinEvent -FilterHashtable @{{LogName='Application'; ProviderName='Application Hang'; StartTime=$start}} -MaxEvents 40
foreach ($item in $hangs) {{
  $msg = ''
  if ($item.Message) {{
    $msg = ($item.Message -replace '\\s+', ' ')
    if ($msg.Length -gt 500) {{ $msg = $msg.Substring(0, 500) }}
  }}
  $rows += [PSCustomObject]@{{
    when = $item.TimeCreated.ToString('o')
    log = 'Application'
    provider = 'Application Hang'
    id = [int]$item.Id
    message = $msg
  }}
}}
if ($rows.Count -eq 0) {{ '[]' }} else {{ $rows | ConvertTo-Json -Compress }}
"""
    try:
        completed = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return EventInfo(
            available=False,
            reason="Reading the Windows event log took too long. Resource numbers below are still valid.",
            window_minutes=window_minutes,
        )
    raw = (completed.stdout or "").strip()
    if not raw:
        return EventInfo(
            available=False,
            reason="The Windows event log could not be read. Resource numbers below are still valid.",
            window_minutes=window_minutes,
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return EventInfo(
            available=False,
            reason="The Windows event log returned data this tool could not parse. Resource numbers below are still valid.",
            window_minutes=window_minutes,
        )
    if isinstance(payload, dict):
        payload = [payload]
    events: list[EventHit] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        provider = str(row.get("provider") or "")
        message = str(row.get("message") or "")
        try:
            event_id = int(row.get("id") or 0)
        except (TypeError, ValueError):
            event_id = 0
        events.append(
            EventHit(
                when=str(row.get("when") or ""),
                log=str(row.get("log") or ""),
                provider=provider,
                event_id=event_id,
                message=message,
                faulting_app=parse_faulting_app(provider, message),
            )
        )
    return EventInfo(
        available=True,
        reason="",
        window_minutes=window_minutes,
        events=events,
    )
