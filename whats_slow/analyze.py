"""Group processes into programs and decide whether they are impeding the PC.

The rules are deliberate and visible. A program is "slowing other programs"
only when its share of the processor, memory, or disk is large, when Windows
says its window is not responding, or when it is both failing often and sitting
on a path other programs have to use (file sync, search, security, Explorer).
A single crash is not treated as a storm.
"""

from __future__ import annotations

import getpass
import os
import socket
from datetime import datetime

from .events import is_disk_event
from .model import EventHit, EventInfo, Proc, Program, Report, Sample
from .names import (
    about_for,
    advice_for,
    exe_basename,
    friendly_name,
    interferes,
    is_symptom_name,
)

# Share of the WHOLE machine (not one core). 30 means 30% of the PC.
CPU_MILD = 15.0
CPU_SLOWING = 30.0
CPU_BLOCKING = 50.0

RAM_MILD = 12.0
RAM_SLOWING = 25.0
RAM_BLOCKING = 45.0

# Sustained bytes per second during the sample.
DISK_MILD_BPS = 8 * 1024 * 1024
DISK_SLOWING_BPS = 25 * 1024 * 1024
DISK_BLOCKING_BPS = 70 * 1024 * 1024

MEM_PRESSURE = 88.0
SWAP_PRESSURE = 15.0
# Linux major faults (the ones that really hit the disk).
MAJOR_FAULTS_NOTABLE = 30.0
# Windows page-fault counter mixes harmless bookkeeping with real misses.
# It only counts when memory is already tight or the number is extreme.
WIN_FAULTS_NOTABLE = 50_000.0
CTX_NOTABLE = 40_000.0
HANDLES_NOTABLE = 30_000

# Errors in the lookback window, divided by minutes.
ERR_OFTEN_PER_MIN = 0.4
ERR_IMPEDING_PER_MIN = 2.0


def build_report(samples: list[Sample], events: EventInfo, *, demo: bool = False) -> Report:
    if not samples:
        raise ValueError("at least one sample is required")
    programs = _merge(samples)
    _attach_events(programs, events)
    total_s = sum(sample.duration_s for sample in samples)
    system = _system_picture(samples)
    system.duration_s = total_s
    for program in programs:
        program.impact = impact_score(program, system)
        program.severity = severity_of(program, system, program.impact, use_peak=False)
        program.peak_severity = severity_of(program, system, program.impact, use_peak=True)
        program.sentences = explain_program(program, system, events)
    programs.sort(key=lambda p: (p.impact, p.cpu_share, p.mem_percent), reverse=True)
    visible = [p for p in programs if not p.is_symptom]
    notes = system_notes(system, programs, events)
    headlines = make_headlines(visible, system, notes)
    steps = next_steps(visible, notes)
    quiet = sum(1 for p in visible if _bucket(p) == "fine")
    return Report(
        sampled_at=datetime.now().astimezone().strftime("%A, %B %d, %Y at %I:%M %p %Z"),
        hostname=socket.gethostname(),
        os_label=system.platform,
        duration_s=total_s,
        repeat_count=len(samples),
        system=system,
        headlines=headlines,
        notes=notes,
        steps=steps,
        programs=visible,
        quiet_count=quiet,
        event_info=events,
        own_note=_own_note(samples),
        demo=demo,
    )


def impact_score(program: Program, system: Sample) -> int:
    cpu = program.cpu_share
    ram = program.mem_percent
    disk = program.read_bps + program.write_bps
    score = 0.0
    score += min(40.0, cpu * 40.0 / 50.0)
    score += min(25.0, ram * 25.0 / 40.0)
    score += min(20.0, (disk / DISK_BLOCKING_BPS) * 20.0)
    if _faults_are_pressure(program, system):
        score += 10.0
    per_min = _errors_per_min(program, system_window(program))
    if per_min:
        score += min(15.0, per_min * 8.0)
    if program.hung_count:
        score += min(15.0, 8.0 * program.hung_count)
    if system.cpu_percent >= 80 and cpu >= 25:
        score += 5.0
    if (program.handles or 0) >= HANDLES_NOTABLE:
        score += 5.0
    return int(round(min(100.0, score)))


def system_window(program: Program) -> int:
    # Event lookback is not stored on the program. Callers pass EventInfo.
    # This helper exists so score can stay a pure function of the program:
    # events are already attached, and the window is fixed at collection time.
    del program
    return 15


def severity_of(program: Program, system: Sample, score: int, *, use_peak: bool) -> str:
    cpu = program.cpu_share_peak if use_peak else program.cpu_share
    disk = program.disk_peak_bps if use_peak else (program.read_bps + program.write_bps)
    ram = program.mem_percent
    if (
        cpu >= CPU_BLOCKING
        or ram >= RAM_BLOCKING
        or disk >= DISK_BLOCKING_BPS
        or score >= 70
        or (program.hung_count and cpu >= 10)
    ):
        return "blocking"
    if (
        cpu >= CPU_SLOWING
        or ram >= RAM_SLOWING
        or disk >= DISK_SLOWING_BPS
        or score >= 40
        or program.hung_count
        or _errors_impede(program, system)
    ):
        return "slowing"
    if (
        cpu >= CPU_MILD
        or ram >= RAM_MILD
        or disk >= DISK_MILD_BPS
        or score >= 18
        or program.events
        or _faults_are_pressure(program, system)
    ):
        return "mild"
    return "fine"


def _errors_per_min(program: Program, window_minutes: int) -> float:
    if not program.events or window_minutes <= 0:
        return 0.0
    return len(program.events) / window_minutes


def _errors_impede(program: Program, system: Sample) -> bool:
    """A stream of errors impedes other programs only in specific cases.

    A crashing game does not slow File Explorer. A crashing file-sync client,
    search indexer, or Explorer add-in does, because other programs wait on it.
    """
    del system
    per_min = len(program.events) / 15.0 if program.events else 0.0
    if per_min < ERR_IMPEDING_PER_MIN:
        return False
    return program.interferes


def _faults_are_pressure(program: Program, system: Sample) -> bool:
    major = program.major_faults_per_sec or 0.0
    if major >= MAJOR_FAULTS_NOTABLE:
        return True
    total = program.faults_per_sec or 0.0
    if total < WIN_FAULTS_NOTABLE:
        return False
    disk_busy = (system.disk_read_bps + system.disk_write_bps) >= DISK_SLOWING_BPS
    ram_tight = system.ram_percent >= MEM_PRESSURE or system.swap_percent >= SWAP_PRESSURE
    return ram_tight or disk_busy


def _merge(samples: list[Sample]) -> list[Program]:
    n = len(samples)
    buckets: dict[str, dict] = {}
    for sample in samples:
        grouped = _group_one(sample.procs)
        for key, group in grouped.items():
            bucket = buckets.get(key)
            if bucket is None:
                bucket = {
                    "identity": group,
                    "count": 0,
                    "cpu_sum": 0.0,
                    "cpu_peak": 0.0,
                    "rss": 0,
                    "mem": 0.0,
                    "read_sum": 0.0,
                    "write_sum": 0.0,
                    "read_n": 0,
                    "disk_peak": 0.0,
                    "io_known": False,
                    "fault_sum": 0.0,
                    "fault_n": 0,
                    "major_sum": 0.0,
                    "major_n": 0,
                    "ctx_sum": 0.0,
                    "ctx_n": 0,
                    "threads": 0,
                    "handles": 0,
                    "handles_known": False,
                    "hung": 0,
                    "high": 0,
                    "users": set(),
                }
                buckets[key] = bucket
            bucket["count"] = max(bucket["count"], group["count"])
            bucket["cpu_sum"] += group["cpu"]
            bucket["cpu_peak"] = max(bucket["cpu_peak"], group["cpu"])
            bucket["rss"] = max(bucket["rss"], group["rss"])
            bucket["mem"] = max(bucket["mem"], group["mem"])
            bucket["threads"] = max(bucket["threads"], group["threads"])
            bucket["hung"] = max(bucket["hung"], group["hung"])
            bucket["users"].update(group["users"])
            if group["io_known"]:
                bucket["io_known"] = True
                bucket["read_sum"] += group["read"]
                bucket["write_sum"] += group["write"]
                bucket["read_n"] += 1
                bucket["disk_peak"] = max(bucket["disk_peak"], group["read"] + group["write"])
            if group["faults"] is not None:
                bucket["fault_sum"] += group["faults"]
                bucket["fault_n"] += 1
            if group["major"] is not None:
                bucket["major_sum"] += group["major"]
                bucket["major_n"] += 1
            if group["ctx"] is not None:
                bucket["ctx_sum"] += group["ctx"]
                bucket["ctx_n"] += 1
            if group["handles"] is not None:
                bucket["handles_known"] = True
                bucket["handles"] = max(bucket["handles"], group["handles"])
            if _metrics_high(group):
                bucket["high"] += 1
            # Prefer the identity from the sample where this program was busiest.
            if group["cpu"] >= bucket["identity"]["cpu"]:
                bucket["identity"] = group
    programs: list[Program] = []
    for key, bucket in buckets.items():
        ident = bucket["identity"]
        read_n = bucket["read_n"] or 1
        programs.append(
            Program(
                key=key,
                display_name=ident["display"],
                about=ident["about"],
                exe_name=ident["exe_name"],
                exe_path=ident["exe_path"],
                service=ident["service"],
                count=bucket["count"],
                usernames=sorted(bucket["users"]),
                cpu_share=min(100.0, bucket["cpu_sum"] / n),
                cpu_share_peak=min(100.0, bucket["cpu_peak"]),
                rss=bucket["rss"],
                mem_percent=min(100.0, bucket["mem"]),
                read_bps=(bucket["read_sum"] / read_n) if bucket["io_known"] else 0.0,
                write_bps=(bucket["write_sum"] / read_n) if bucket["io_known"] else 0.0,
                disk_peak_bps=bucket["disk_peak"],
                io_known=bucket["io_known"],
                faults_per_sec=(bucket["fault_sum"] / bucket["fault_n"]) if bucket["fault_n"] else None,
                major_faults_per_sec=(bucket["major_sum"] / bucket["major_n"]) if bucket["major_n"] else None,
                ctx_per_sec=(bucket["ctx_sum"] / bucket["ctx_n"]) if bucket["ctx_n"] else None,
                threads=bucket["threads"],
                handles=bucket["handles"] if bucket["handles_known"] else None,
                hung_count=bucket["hung"],
                events=[],
                is_symptom=ident["symptom"],
                interferes=ident["interferes"],
                high_samples=bucket["high"],
                total_samples=n,
            )
        )
    _disambiguate(programs)
    return programs


def _metrics_high(group: dict) -> bool:
    disk = (group["read"] + group["write"]) if group["io_known"] else 0.0
    return (
        group["cpu"] >= CPU_SLOWING
        or group["mem"] >= RAM_SLOWING
        or disk >= DISK_SLOWING_BPS
        or group["hung"] > 0
    )


def _group_one(procs: list[Proc]) -> dict[str, dict]:
    """Group processes. proc.cpu_raw is the share of the whole PC (100 = all cores)."""
    grouped: dict[str, dict] = {}
    for proc in procs:
        base = exe_basename(proc.exe, proc.name)
        key = _key(proc, base)
        slot = grouped.get(key)
        if slot is None:
            service = proc.service
            slot = {
                "display": friendly_name(base, service),
                "about": about_for(base, service),
                "exe_name": base,
                "exe_path": proc.exe,
                "service": service,
                "count": 0,
                "cpu": 0.0,
                "rss": 0,
                "mem": 0.0,
                "read": 0.0,
                "write": 0.0,
                "io_known": False,
                "faults": None,
                "major": None,
                "ctx": None,
                "threads": 0,
                "handles": None,
                "hung": 0,
                "users": set(),
                "symptom": is_symptom_name(base, proc.name),
                "interferes": interferes(base, service),
            }
            grouped[key] = slot
        slot["count"] += 1
        slot["cpu"] += max(0.0, proc.cpu_raw)
        slot["rss"] += proc.rss
        slot["mem"] += max(0.0, proc.mem_percent)
        if proc.io_known:
            slot["io_known"] = True
            slot["read"] += max(0.0, proc.read_bps)
            slot["write"] += max(0.0, proc.write_bps)
        slot["faults"] = _add_opt(slot["faults"], proc.faults_per_sec)
        slot["major"] = _add_opt(slot["major"], proc.major_faults_per_sec)
        slot["ctx"] = _add_opt(slot["ctx"], proc.ctx_per_sec)
        slot["threads"] += proc.threads or 0
        if proc.handles is not None:
            slot["handles"] = (slot["handles"] or 0) + proc.handles
        if proc.hung:
            slot["hung"] += 1
        if proc.username:
            slot["users"].add(_short_user(proc.username))
        if proc.service and not slot["service"]:
            slot["service"] = proc.service
        if is_symptom_name(base, proc.name):
            slot["symptom"] = True
    return grouped


def _key(proc: Proc, base: str) -> str:
    if proc.service:
        return "service:" + proc.service.lower()
    if proc.exe:
        path = proc.exe
        if os.path.isabs(path):
            path = os.path.normcase(os.path.abspath(path))
        else:
            path = os.path.normcase(path)
        return "exe:" + path
    return "name:" + (base or proc.name or "unknown").lower()


def _add_opt(current: float | None, extra: float | None) -> float | None:
    if extra is None:
        return current
    return (current or 0.0) + extra


def _disambiguate(programs: list[Program]) -> None:
    by_name: dict[str, list[Program]] = {}
    for program in programs:
        by_name.setdefault(program.display_name, []).append(program)
    for name, group in by_name.items():
        if len(group) < 2:
            continue
        for program in group:
            folder = os.path.dirname(program.exe_path) if program.exe_path else ""
            folder = folder or program.exe_name
            program.display_name = f"{name} ({folder})"


def _attach_events(programs: list[Program], info: EventInfo) -> None:
    if not info.available:
        return
    disks: list[EventHit] = []
    claimed: set[int] = set()
    for index, event in enumerate(info.events):
        if is_disk_event(event):
            disks.append(event)
            claimed.add(index)
            continue
        for program in programs:
            if program.is_symptom:
                continue
            if _event_matches(program, event):
                program.events.append(event)
                claimed.add(index)
                break
    info.disk_events = disks


def _event_matches(program: Program, event: EventHit) -> bool:
    stems = set()
    if program.exe_name:
        stems.add(program.exe_name.lower())
    if program.service:
        stems.add(program.service.lower())
    display = program.display_name.lower()
    generic = {
        "system",
        "application",
        "svchost.exe",
        "svchost",
        "unknown",
        "registry",
    }
    stems = {s for s in stems if len(s) >= 4 and s not in generic}
    faulting = (event.faulting_app or "").lower()
    if faulting and faulting in stems:
        return True
    # Service names are specific enough to match the provider or the message.
    blob = f"{event.provider} {event.message}".lower()
    if program.service and len(program.service) >= 4:
        token = program.service.lower()
        if token not in generic and token in blob:
            return True
    for stem in stems:
        if stem.endswith(".exe") and stem in blob:
            return True
    return False


def _system_picture(samples: list[Sample]) -> Sample:
    """Levels (RAM, free disk) from the latest sample. Busyness averaged."""
    last = samples[-1]
    last.cpu_percent = sum(s.cpu_percent for s in samples) / len(samples)
    iow = [s.iowait_percent for s in samples if s.iowait_percent is not None]
    last.iowait_percent = sum(iow) / len(iow) if iow else None
    last.ram_percent = max(s.ram_percent for s in samples)
    last.swap_percent = max(s.swap_percent for s in samples)
    last.disk_read_bps = sum(s.disk_read_bps for s in samples) / len(samples)
    last.disk_write_bps = sum(s.disk_write_bps for s in samples) / len(samples)
    last.unreadable = max(s.unreadable for s in samples)
    last.disk_sleep_count = max(s.disk_sleep_count for s in samples)
    last.zombie_count = max(s.zombie_count for s in samples)
    hots = [s.hot_c for s in samples if s.hot_c is not None]
    last.hot_c = max(hots) if hots else None
    return last


def make_headlines(programs: list[Program], system: Sample, notes: list[str]) -> list[str]:
    offenders = [p for p in programs if _bucket(p) in {"blocking", "slowing"}]
    lines: list[str] = []
    watched = _fmt_seconds(system.duration_s)
    if offenders:
        names = _name_list(offenders[:3])
        verb = "is" if len(offenders) == 1 else "are"
        lines.append(
            f"In this {watched} check, {names} {verb} using enough of the PC to slow other programs."
        )
    else:
        spikes = [p for p in programs if p.peak_severity in {"blocking", "slowing"} and p.total_samples > 1]
        if spikes:
            lines.append(
                f"In this {watched} check, nothing stayed heavy the whole time. "
                f"{_name_list(spikes[:2])} spiked and then quieted down."
            )
        else:
            lines.append(
                f"In this {watched} check, no program used enough processor, memory, or disk to clearly slow the others."
            )
    bits = []
    if system.cpu_percent >= 75:
        bits.append(f"the processor is {system.cpu_percent:.0f}% busy")
    elif system.cpu_percent < 35:
        bits.append(f"the processor is only {system.cpu_percent:.0f}% busy")
    if system.ram_percent >= MEM_PRESSURE:
        bits.append(f"memory is {system.ram_percent:.0f}% full")
    if system.swap_total and system.swap_percent >= SWAP_PRESSURE:
        bits.append("the PC is using the disk as extra memory, which feels like freezing")
    if system.iowait_percent is not None and system.iowait_percent >= 20:
        bits.append(f"the PC is spending {system.iowait_percent:.0f}% of its time waiting on the disk")
    if bits:
        lines.append("At the same time, " + _join(bits) + ".")
    if not offenders and system.cpu_percent < 40 and system.ram_percent < MEM_PRESSURE:
        lines.append(
            "If the PC still feels slow, the cause is likely a short spike this check missed, "
            "a program that is waiting instead of working, or the network. "
            "A slow website does not show up here when the processor is mostly free. "
            "Run the check again while the slowness is actually happening."
        )
    if notes and offenders:
        lines.append("There is also a whole-PC condition below that can slow every program at once.")
    return lines


def explain_program(program: Program, system: Sample, events: EventInfo) -> list[str]:
    sentences: list[str] = []
    where = program.exe_path or program.exe_name
    if program.count == 1 and program.service:
        host = program.exe_name or "svchost.exe"
        sentences.append(
            f"This process belongs to the Windows service {program.display_name}, hosted by {host}."
        )
    elif program.service:
        host = program.exe_name or "svchost.exe"
        sentences.append(
            f"These {program.count} processes belong to the Windows service "
            f"{program.display_name}, hosted by {host}."
        )
    elif program.count == 1:
        sentences.append(
            f"This process belongs to {program.display_name}"
            + (f" ({where})." if where else ".")
        )
    else:
        sentences.append(
            f"These {program.count} processes belong to {program.display_name}"
            + (f" ({where})." if where else ".")
        )
        sentences.append(
            "They are added together because they are the same program, not because Windows listed one line."
        )

    bits = []
    if program.cpu_share >= 3:
        cores = system.cpu_count * program.cpu_share / 100.0
        bits.append(
            f"about {program.cpu_share:.0f}% of the processor "
            f"(around {cores:.1f} of {system.cpu_count} cores)"
        )
    if program.mem_percent >= 2 or program.rss >= 200 * 1024 * 1024:
        bits.append(f"{human_bytes(program.rss)} of memory ({program.mem_percent:.0f}% of RAM)")
    if program.io_known and (program.read_bps + program.write_bps) >= 0.5 * 1024 * 1024:
        bits.append(
            f"disk activity of {human_rate(program.read_bps)} read and {human_rate(program.write_bps)} written"
        )
    elif not program.io_known:
        bits.append("disk activity that this check was not allowed to see")
    if bits:
        sentences.append("It is using " + _join(bits) + ".")
    else:
        sentences.append("It is using very little processor, memory, and disk right now.")

    bucket = _bucket(program)
    reason = _dominant(program, system)
    sentences.append(_because(program, system, bucket, reason))

    if program.total_samples > 1:
        sentences.append(_persistence(program))

    if _faults_are_pressure(program, system):
        if (program.major_faults_per_sec or 0) >= MAJOR_FAULTS_NOTABLE:
            sentences.append(
                f"It is forcing about {program.major_faults_per_sec:,.0f} real memory-to-disk lookups a second. "
                "That is the PC using the disk as memory, and it makes every program stutter."
            )
        else:
            sentences.append(
                f"It is touching memory about {program.faults_per_sec:,.0f} times a second while RAM is "
                f"{system.ram_percent:.0f}% full. When memory is that full, those requests spill onto the disk "
                "and the whole PC stutters. On Windows this counter also includes harmless bookkeeping, "
                "so it is only treated as a problem because memory or the disk is already under stress."
            )
    if program.hung_count:
        word = "window" if program.hung_count == 1 else "windows"
        sentences.append(
            f"Windows reports {program.hung_count} {word} for this program as not responding. "
            "A frozen window often means the program is stuck, and the PC can feel slow until it is closed."
        )
    sentences.extend(_error_sentences(program, events))
    if (program.ctx_per_sec or 0) >= CTX_NOTABLE and program.cpu_share < CPU_SLOWING:
        sentences.append(
            f"It is waking the processor about {program.ctx_per_sec:,.0f} times a second. "
            "That much churn can make the PC feel less smooth even when the processor percentage looks modest."
        )
    if (program.handles or 0) >= HANDLES_NOTABLE:
        sentences.append(
            f"It is holding about {program.handles:,.0f} open handles (files and system objects). "
            "A number that high often means a leak, which slowly makes the whole PC less stable."
        )
    who = _who(program)
    if who:
        sentences.append(who)
    if program.about:
        sentences.append(program.about)
    return sentences


def _because(program: Program, system: Sample, bucket: str, reason: str) -> str:
    name = program.display_name
    if bucket == "blocking":
        lead = f"This is enough to get in the way of other programs. {name} is one of the main reasons the PC feels slow right now."
    elif bucket == "slowing":
        if reason == "errors":
            lead = f"This is enough to slow other programs that depend on {name}."
        elif reason == "hung":
            lead = f"This is enough to make the PC feel stuck. {name} is not responding."
        else:
            lead = f"This is enough to slow other programs. {name} is taking a real share of the PC."
    elif bucket == "mild":
        return (
            "This is noticeable, but on its own it should not freeze the other programs. "
            "It matters more if several programs are in this range together."
        )
    else:
        if program.peak_severity in {"blocking", "slowing"} and program.total_samples > 1:
            return (
                "Averaged over the whole check, this is not enough to keep other programs waiting. "
                "It did spike. See the note below on how many samples were high."
            )
        return "This is not enough to get in the way of other programs."
    detail = {
        "cpu": " The processor is spending a large share of its time here, so other programs wait for their turn.",
        "memory": " It is holding so much memory that other programs have little room, and the PC starts leaning on the disk.",
        "disk": " Other programs that need to read or write are waiting behind this disk activity.",
        "hung": " The frozen window is the problem more than the raw processor number.",
        "errors": " The resource numbers are not the whole story. It is also failing often enough to stall work that depends on it.",
        "faults": " Memory is so tight that this program's memory use is turning into disk waits for everyone.",
    }.get(reason, "")
    if reason == "disk" and _disk_share(program, system) >= 0.4:
        detail += " That is a large share of all disk activity during the check."
    return lead + detail


def _disk_share(program: Program, system: Sample) -> float:
    total = system.disk_read_bps + system.disk_write_bps
    if total <= 0:
        return 0.0
    return (program.read_bps + program.write_bps) / total


def _dominant(program: Program, system: Sample) -> str:
    cpu_pts = min(40.0, program.cpu_share * 40.0 / 50.0)
    ram_pts = min(25.0, program.mem_percent * 25.0 / 40.0)
    disk_pts = min(20.0, ((program.read_bps + program.write_bps) / DISK_BLOCKING_BPS) * 20.0)
    scores = {"cpu": cpu_pts, "memory": ram_pts, "disk": disk_pts}
    if program.hung_count and max(scores.values()) < 15:
        return "hung"
    if _errors_impede(program, system) and max(scores.values()) < 15:
        return "errors"
    if _faults_are_pressure(program, system) and max(scores.values()) < 12:
        return "faults"
    winner = max(scores, key=scores.get)
    if scores[winner] < 1:
        if program.events:
            return "errors"
        if program.hung_count:
            return "hung"
    return winner


def _persistence(program: Program) -> str:
    n = program.total_samples
    high = program.high_samples
    if high == n and n > 1:
        return f"It was high in all {n} samples, so this is not a one-second blip."
    if high == 0 and program.cpu_share_peak >= CPU_SLOWING:
        return (
            f"It peaked at {program.cpu_share_peak:.0f}% of the processor but was not high for a whole sample. "
            "That looks like a short burst."
        )
    if high == 1:
        return (
            f"It was high in only 1 of {n} samples. It may have been a short spike "
            "(an update, a scan, or a file copy). Run the check once more before closing it for this reason."
        )
    if high > 1:
        return f"It was high in {high} of {n} samples. That is repeated, not a single blip."
    return f"Across {n} samples it stayed in the same range."


def _error_sentences(program: Program, events: EventInfo) -> list[str]:
    if not events.available and not program.events:
        return []
    count = len(program.events)
    window = events.window_minutes or 15
    if count == 0:
        return []
    per_min = count / window
    if count <= 2 and per_min < ERR_OFTEN_PER_MIN:
        return [
            f"Windows logged {count} error{'s' if count != 1 else ''} for it in the last {window} minutes. "
            "That is a small burst, often a single crash, not an ongoing stream of errors. "
            "Judge the slowdown from the processor, memory, and disk numbers, not from this burst alone."
        ]
    if per_min >= ERR_IMPEDING_PER_MIN and program.interferes:
        return [
            f"Windows logged {count} errors in the last {window} minutes, about {per_min:.1f} every minute. "
            "That is a stream of failures, not one crash. Because this program sits on the path of normal PC use "
            "(files, search, security, or updates), other programs can stall while it keeps failing."
        ]
    if per_min >= ERR_OFTEN_PER_MIN:
        extra = ""
        if not program.interferes:
            extra = (
                " These failures make this program unreliable. They do not, by themselves, prove it is slowing unrelated programs."
            )
        return [
            f"Windows logged {count} errors in the last {window} minutes, about {per_min:.1f} every minute. "
            "That is a real stream of failures, not a one-time crash."
            + extra
        ]
    return [
        f"Windows logged {count} errors for it in the last {window} minutes. "
        "That is more than a single crash, but not a rapid stream."
    ]


def system_notes(system: Sample, programs: list[Program], events: EventInfo) -> list[str]:
    notes: list[str] = []
    for disk in system.disks:
        if disk.percent >= 90:
            notes.append(
                f"The drive {disk.mount} is {disk.percent:.0f}% full, with {human_bytes(disk.free_bytes)} free. "
                "Windows gets slow, and updates fail, when a drive has less than about 15% free."
            )
    if system.ram_percent >= 90 and system.swap_percent >= 10 and system.swap_total:
        notes.append(
            "Memory is almost full and the PC has started using the disk as extra RAM. "
            "That one condition makes every program feel slow. The large programs above are what filled the memory."
        )
    elif system.ram_percent >= MEM_PRESSURE:
        notes.append(
            f"Memory is {system.ram_percent:.0f}% full. The PC is close to the point where everything slows down, "
            "even programs that are behaving."
        )
    if system.iowait_percent is not None and system.iowait_percent >= 25:
        notes.append(
            f"The processor spent {system.iowait_percent:.0f}% of the check waiting on the disk rather than running programs. "
            "When this number is high, the disk is the bottleneck."
        )
    if events.available and events.disk_events:
        n = len(events.disk_events)
        notes.append(
            f"Windows recorded {n} disk error{'s' if n != 1 else ''} in the last {events.window_minutes} minutes. "
            "Disk errors slow every program, because every program has to wait on storage. "
            "Copy important files somewhere else and check the drive."
        )
    for program in programs:
        if program.is_symptom and program.display_name.lower().startswith("memory compression") and program.rss >= 1024**3:
            notes.append(
                f"Windows is compressing memory (about {human_bytes(program.rss)}). "
                "That happens when RAM is tight. The programs using the most memory are the cause, not Memory Compression."
            )
        if program.exe_name.lower() in {"kswapd0", "kswapd"} and (program.cpu_share >= 2 or system.ram_percent >= MEM_PRESSURE):
            notes.append(
                "The kernel is spending time shuffling memory because RAM is overfull. "
                "Closing the largest programs above is what helps, not stopping the kernel task."
            )
    if system.hot_c and system.hot_c >= 92:
        notes.append(
            f"A temperature sensor reads about {system.hot_c:.0f}°C. "
            "When a PC gets this hot it slows itself to avoid damage. Check that fans are spinning and vents are not blocked."
        )
    if system.disk_sleep_count >= 3:
        notes.append(
            f"{system.disk_sleep_count} processes are stuck waiting on the disk. "
            "The PC can feel frozen until the disk responds. This points at the disk or a driver, not at a single window you clicked."
        )
    if system.unreadable >= 12:
        notes.append(
            f"{system.unreadable} processes could not be fully measured. "
            "If a heavy program seems to be missing, run the check again as administrator."
        )
    if not events.available and events.reason:
        notes.append(events.reason)
    return notes


def next_steps(programs: list[Program], notes: list[str]) -> list[str]:
    steps: list[str] = []
    ranked = [p for p in programs if _bucket(p) in {"blocking", "slowing", "mild"}]
    ranked.sort(key=lambda p: ({"blocking": 0, "slowing": 1, "mild": 2}.get(_bucket(p), 3), -p.impact))
    for program in ranked[:3]:
        steps.append(advice_for(program.exe_name, program.service, program.display_name, _advice_kind(program)))
    for note in notes:
        lower = note.lower()
        if "full" in lower and "drive" in lower:
            steps.append("Free space on the full drive. Aim for at least 15% free, then restart the PC.")
        if "disk error" in lower:
            steps.append(
                "Back up files you cannot replace. Then check the drive's health, or have a shop do it. "
                "Disk errors are a hardware warning, not an app to uninstall."
            )
        if "temperature" in lower or "°c" in lower:
            steps.append("Make sure the vents are clear and the fans spin. Heat throttling looks like a slow PC.")
    # De-duplicate while keeping order.
    unique = []
    for step in steps:
        if step not in unique:
            unique.append(step)
    if not unique:
        unique.append(
            "Nothing needs to be closed based on this check. Run it again while the PC feels slow, "
            "for 20 seconds, three times in a row (the repeat option in the instructions). "
            "If it is still quiet and only websites are slow, the network is the problem, not a program on this PC."
        )
    return unique[:5]


def _advice_kind(program: Program) -> str:
    if program.hung_count and program.cpu_share < CPU_SLOWING and program.mem_percent < RAM_SLOWING:
        return "hung"
    disk = program.read_bps + program.write_bps
    cpu_pts = program.cpu_share
    ram_pts = program.mem_percent
    disk_pts = disk / (1024 * 1024)
    if program.events and cpu_pts < CPU_MILD and ram_pts < RAM_MILD and disk < DISK_MILD_BPS:
        return "errors"
    if disk_pts >= 25 and disk_pts >= cpu_pts and ram_pts < RAM_SLOWING:
        return "disk"
    if ram_pts >= RAM_SLOWING and ram_pts >= cpu_pts:
        return "memory"
    return "cpu"


def _bucket(program: Program) -> str:
    if program.severity in {"blocking", "slowing"}:
        return program.severity
    if (
        program.total_samples > 1
        and program.peak_severity in {"blocking", "slowing"}
        and program.severity == "fine"
    ):
        return "mild"
    return program.severity


def _who(program: Program) -> str:
    if not program.usernames:
        return ""
    try:
        me = getpass.getuser()
    except OSError:
        me = ""
    shorts = program.usernames
    if len(shorts) == 1:
        only = shorts[0]
        if me and only.lower() == me.lower():
            return "It is running as you."
        if only.lower() in {"system", "local service", "network service", "root"}:
            return f"It is running as {only}, which means it is a background service rather than a window you opened."
        return f"It is running as {only}."
    return "It is running under more than one account."


def _own_note(samples: list[Sample]) -> str | None:
    # Sampler currently leaves own_cpu_share at 0 because it skips self CPU.
    rss = max(s.own_rss for s in samples)
    if rss <= 0:
        return None
    return (
        f"This check itself was using about {human_bytes(rss)} of memory while it watched. "
        "That is the cost of measuring, and it is not counted against your programs."
    )


def _short_user(username: str) -> str:
    if "\\" in username:
        return username.split("\\", 1)[1]
    if username.endswith("$"):
        return username
    if "@" in username:
        return username.split("@", 1)[0]
    return username


def _name_list(programs: list[Program]) -> str:
    names = [p.display_name for p in programs]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _join(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def _fmt_seconds(seconds: float) -> str:
    if seconds < 70:
        return f"{seconds:.0f}-second"
    minutes = seconds / 60.0
    return f"{minutes:.0f}-minute"


def human_bytes(n: float) -> str:
    n = float(n)
    sign = "-" if n < 0 else ""
    n = abs(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "B":
                return f"{sign}{n:.0f} {unit}"
            if n >= 10:
                return f"{sign}{n:.0f} {unit}"
            return f"{sign}{n:.1f} {unit}"
        n /= 1024
    return f"{sign}{n:.0f} TB"


def human_rate(bps: float) -> str:
    return human_bytes(bps) + "/s"

