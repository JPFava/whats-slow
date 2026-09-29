"""A made-up busy PC, so the report's language can be read before a real check."""

from __future__ import annotations

from .analyze import build_report
from .events import EventInfo
from .model import DiskUsage, EventHit, EventInfo as _EI, Proc, Sample

GB = 1024**3
MB = 1024**2


def _proc(**kwargs) -> Proc:
    base = dict(
        pid=1,
        name="app",
        exe=None,
        username="John",
        ppid=4,
        status="running",
        cpu_raw=0.0,
        rss=40 * MB,
        mem_percent=0.3,
        read_bps=0.0,
        write_bps=0.0,
        io_known=True,
        faults_per_sec=None,
        major_faults_per_sec=None,
        ctx_per_sec=None,
        threads=8,
        handles=200,
        hung=False,
        service=None,
    )
    base.update(kwargs)
    return Proc(**base)


def _sample(procs: list[Proc], **kwargs) -> Sample:
    ram = 16 * GB
    base = dict(
        duration_s=8.0,
        cpu_percent=91.0,
        iowait_percent=None,
        cpu_count=8,
        ram_total=ram,
        ram_used=int(ram * 0.93),
        ram_percent=93.0,
        swap_total=8 * GB,
        swap_used=int(2.4 * GB),
        swap_percent=30.0,
        disk_read_bps=20 * MB,
        disk_write_bps=55 * MB,
        disks=[
            DiskUsage(mount="C:\\", percent=96.0, free_bytes=int(12 * GB), total_bytes=int(300 * GB)),
        ],
        process_count=len(procs) + 40,
        unreadable=0,
        disk_sleep_count=0,
        zombie_count=0,
        hot_c=None,
        platform="Windows-11",
        procs=procs,
        own_cpu_share=0.0,
        own_rss=80 * MB,
    )
    base.update(kwargs)
    return Sample(**base)


def demo_report():
    chrome_a = _proc(
        pid=100,
        name="chrome.exe",
        exe=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        cpu_raw=36.0,
        rss=int(3.4 * GB),
        mem_percent=21.0,
        read_bps=2 * MB,
        write_bps=1 * MB,
        faults_per_sec=80_000,
        threads=40,
        handles=4000,
    )
    chrome_b = _proc(
        pid=101,
        name="chrome.exe",
        exe=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        cpu_raw=22.0,
        rss=int(2.1 * GB),
        mem_percent=13.0,
        read_bps=1 * MB,
        write_bps=0.2 * MB,
        faults_per_sec=20_000,
        threads=30,
        handles=2500,
    )
    onedrive = _proc(
        pid=200,
        name="OneDrive.exe",
        exe=r"C:\Users\John\AppData\Local\Microsoft\OneDrive\OneDrive.exe",
        cpu_raw=4.0,
        rss=180 * MB,
        mem_percent=1.1,
        read_bps=8 * MB,
        write_bps=42 * MB,
    )
    sysmain = _proc(
        pid=300,
        name="svchost.exe",
        exe=r"C:\Windows\System32\svchost.exe",
        cpu_raw=6.0,
        rss=90 * MB,
        mem_percent=0.5,
        read_bps=12 * MB,
        write_bps=3 * MB,
        service="SysMain",
        username="SYSTEM",
    )
    word = _proc(
        pid=400,
        name="WINWORD.EXE",
        exe=r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
        cpu_raw=2.0,
        rss=350 * MB,
        mem_percent=2.1,
        hung=True,
    )
    widgets = _proc(
        pid=500,
        name="Widgets.exe",
        exe=r"C:\Program Files\WindowsApps\Widgets\Widgets.exe",
        cpu_raw=1.0,
        rss=120 * MB,
        mem_percent=0.7,
    )
    spotify = _proc(
        pid=600,
        name="Spotify.exe",
        exe=r"C:\Users\John\AppData\Roaming\Spotify\Spotify.exe",
        cpu_raw=0.4,
        rss=180 * MB,
        mem_percent=1.1,
    )
    idle = _proc(
        pid=0,
        name="System Idle Process",
        exe=None,
        cpu_raw=5.0,
        rss=0,
        mem_percent=0,
        username="SYSTEM",
    )
    compression = _proc(
        pid=8,
        name="Memory Compression",
        exe=None,
        cpu_raw=1.0,
        rss=int(1.4 * GB),
        mem_percent=8.0,
        username="SYSTEM",
    )
    procs = [chrome_a, chrome_b, onedrive, sysmain, word, widgets, spotify, idle, compression]
    # Second sample: Chrome stays high, OneDrive stays high, Widgets stays quiet.
    procs_2 = []
    for proc in procs:
        clone = Proc(**proc.__dict__)
        if clone.pid in {100, 101}:
            clone.cpu_raw = proc.cpu_raw * 0.9
        procs_2.append(clone)
    events = [
        EventHit(
            when="2026-09-29T18:20:00",
            log="Application",
            provider="Application Error",
            event_id=1000,
            message="Faulting application name: chrome.exe, version: 129.0.0.0",
            faulting_app="chrome.exe",
        ),
        EventHit(
            when="2026-09-29T18:21:00",
            log="Application",
            provider="Application Error",
            event_id=1000,
            message="Faulting application name: chrome.exe, version: 129.0.0.0",
            faulting_app="chrome.exe",
        ),
    ]
    events.extend(
        EventHit(
            when="2026-09-29T18:10:00",
            log="Application",
            provider="Application Error",
            event_id=1000,
            message="Faulting application name: Widgets.exe, version: 1.0.0.0",
            faulting_app="Widgets.exe",
        )
        for _ in range(18)
    )
    events.append(
        EventHit(
            when="2026-09-29T18:12:00",
            log="System",
            provider="disk",
            event_id=7,
            message="The device, \\Device\\Harddisk0\\DR0, has a bad block.",
            faulting_app=None,
        )
    )
    info = EventInfo(available=True, reason="", window_minutes=15, events=events)
    report = build_report(
        [_sample(procs), _sample(procs_2, duration_s=8.0, cpu_percent=88.0)],
        info,
        demo=True,
    )
    report.hostname = "Example-PC"
    report.sampled_at = "Tuesday, September 29, 2026 at 6:40 PM EDT"
    return report


# Re-export for tests that want the type name stable.
EventInfo = _EI
