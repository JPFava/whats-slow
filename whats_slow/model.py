"""Data the sampler collects and the report shows. No behavior here."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DiskUsage:
    mount: str
    percent: float
    free_bytes: int
    total_bytes: int


@dataclass
class Proc:
    """One process, measured across a single sample window."""

    pid: int
    name: str
    exe: str | None
    username: str | None
    ppid: int | None
    status: str
    # Share of the whole PC. 100 means this one process is using every core.
    cpu_raw: float
    rss: int
    mem_percent: float
    read_bps: float
    write_bps: float
    io_known: bool
    faults_per_sec: float | None
    major_faults_per_sec: float | None
    ctx_per_sec: float | None
    threads: int | None
    handles: int | None
    hung: bool
    service: str | None


@dataclass
class Sample:
    duration_s: float
    cpu_percent: float
    iowait_percent: float | None
    cpu_count: int
    ram_total: int
    ram_used: int
    ram_percent: float
    swap_total: int
    swap_used: int
    swap_percent: float
    disk_read_bps: float
    disk_write_bps: float
    disks: list[DiskUsage]
    process_count: int
    unreadable: int
    disk_sleep_count: int
    zombie_count: int
    hot_c: float | None
    platform: str
    procs: list[Proc]
    own_cpu_share: float
    own_rss: int


@dataclass
class EventHit:
    when: str
    log: str
    provider: str
    event_id: int
    message: str
    faulting_app: str | None = None


@dataclass
class EventInfo:
    available: bool
    reason: str
    window_minutes: int
    events: list[EventHit] = field(default_factory=list)
    disk_events: list[EventHit] = field(default_factory=list)


@dataclass
class Program:
    key: str
    display_name: str
    about: str
    exe_name: str
    exe_path: str | None
    service: str | None
    count: int
    usernames: list[str]
    cpu_share: float
    cpu_share_peak: float
    rss: int
    mem_percent: float
    read_bps: float
    write_bps: float
    disk_peak_bps: float
    io_known: bool
    faults_per_sec: float | None
    major_faults_per_sec: float | None
    ctx_per_sec: float | None
    threads: int
    handles: int | None
    hung_count: int
    events: list[EventHit]
    is_symptom: bool
    interferes: bool
    high_samples: int
    total_samples: int
    impact: int = 0
    severity: str = "fine"
    peak_severity: str = "fine"
    sentences: list[str] = field(default_factory=list)


@dataclass
class Report:
    sampled_at: str
    hostname: str
    os_label: str
    duration_s: float
    repeat_count: int
    system: Sample
    headlines: list[str]
    notes: list[str]
    steps: list[str]
    programs: list[Program]
    quiet_count: int
    event_info: EventInfo
    own_note: str | None
    demo: bool = False
