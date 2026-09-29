"""Measure processes for a few seconds. Read-only. Never stops a program."""

from __future__ import annotations

import os
import platform
import time

import psutil

from .model import DiskUsage, Proc, Sample
from .names import service_from_cmdline

_SKIP_FS = {
    "squashfs",
    "tmpfs",
    "devtmpfs",
    "overlay",
    "iso9660",
    "autofs",
    "cgroup2",
    "cgroup",
    "proc",
    "sysfs",
    "devpts",
    "mqueue",
    "nsfs",
    "tracefs",
    "debugfs",
    "securityfs",
    "pstore",
    "bpf",
    "configfs",
    "ramfs",
    "fuse.portal",
}


def take_sample(seconds: float) -> Sample:
    seconds = max(1.0, float(seconds))
    own_pids = _own_pids()
    hung = _hung_pids()

    _prime_cpu()
    baseline = _capture(own_pids)
    cpu_times_0 = psutil.cpu_times()
    disk_0 = psutil.disk_io_counters()
    psutil.cpu_percent(interval=None)
    started = time.monotonic()
    time.sleep(seconds)
    elapsed = max(time.monotonic() - started, 0.1)
    cpu_times_1 = psutil.cpu_times()
    disk_1 = psutil.disk_io_counters()
    system_cpu = psutil.cpu_percent(interval=None)
    ending = _capture(own_pids)

    procs, unreadable, own_cpu, own_rss, disk_sleep, zombies = _diff(
        baseline, ending, elapsed, hung, own_pids
    )
    busy, iowait = _cpu_split(cpu_times_0, cpu_times_1)
    # psutil's own percent is the better "how busy is the machine" number when
    # it came back; the times split is the fallback and the source of iowait.
    if system_cpu is None:
        system_cpu = busy
    read_bps, write_bps = _disk_rates(disk_0, disk_1, elapsed)
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return Sample(
        duration_s=elapsed,
        cpu_percent=float(system_cpu or 0.0),
        iowait_percent=iowait,
        cpu_count=psutil.cpu_count(logical=True) or 1,
        ram_total=int(vm.total),
        ram_used=int(vm.total - vm.available),
        ram_percent=float(vm.percent),
        swap_total=int(swap.total),
        swap_used=int(swap.used),
        swap_percent=float(swap.percent) if swap.total else 0.0,
        disk_read_bps=read_bps,
        disk_write_bps=write_bps,
        disks=_disks(),
        process_count=len(ending),
        unreadable=unreadable,
        disk_sleep_count=disk_sleep,
        zombie_count=zombies,
        hot_c=_hottest(),
        platform=platform.platform(terse=True),
        procs=procs,
        own_cpu_share=own_cpu,
        own_rss=own_rss,
    )


def _own_pids() -> set[int]:
    pids = {os.getpid()}
    try:
        parent = os.getppid()
        if parent:
            pids.add(parent)
    except OSError:
        pass
    try:
        me = psutil.Process()
        for child in me.children(recursive=True):
            pids.add(child.pid)
    except (psutil.Error, OSError):
        pass
    return pids


def _prime_cpu() -> None:
    for proc in psutil.process_iter():
        try:
            proc.cpu_percent(interval=None)
        except (psutil.Error, OSError):
            continue


def _capture(own_pids: set[int]) -> dict[int, dict]:
    rows: dict[int, dict] = {}
    for proc in psutil.process_iter():
        try:
            with proc.oneshot():
                pid = proc.pid
                name = proc.name() or ""
                exe = _optional(proc.exe)
                cmdline = _optional(proc.cmdline) or []
                username = _optional(proc.username)
                ppid = _optional(proc.ppid)
                status = ""
                try:
                    status = proc.status()
                except (psutil.Error, OSError):
                    status = ""
                mem = proc.memory_info()
                rss = int(getattr(mem, "rss", 0) or 0)
                try:
                    mem_percent = float(proc.memory_percent())
                except (psutil.Error, OSError):
                    mem_percent = 0.0
                io = _optional(proc.io_counters)
                faults = _faults(proc, mem)
                ctx = _optional(proc.num_ctx_switches)
                threads = _optional(proc.num_threads)
                handles = _handles(proc)
                cpu = 0.0
                if pid not in own_pids:
                    try:
                        cpu = float(proc.cpu_percent(interval=None) or 0.0)
                    except (psutil.Error, OSError):
                        cpu = 0.0
                rows[pid] = {
                    "name": name,
                    "exe": exe,
                    "cmdline": list(cmdline) if isinstance(cmdline, (list, tuple)) else [],
                    "username": username,
                    "ppid": ppid,
                    "status": status or "",
                    "cpu": cpu,
                    "rss": rss,
                    "mem_percent": mem_percent,
                    "read": int(getattr(io, "read_bytes", 0) or 0) if io else None,
                    "write": int(getattr(io, "write_bytes", 0) or 0) if io else None,
                    "faults": faults[0],
                    "major": faults[1],
                    "ctx": _ctx_total(ctx),
                    "threads": int(threads) if isinstance(threads, int) else None,
                    "handles": handles,
                    "service": service_from_cmdline(name, list(cmdline) if isinstance(cmdline, (list, tuple)) else []),
                }
        except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied, OSError):
            continue
    return rows


def _diff(baseline, ending, elapsed, hung: set[int], own_pids: set[int]):
    cpu_count = psutil.cpu_count(logical=True) or 1
    procs: list[Proc] = []
    unreadable = 0
    own_cpu_raw = 0.0
    own_rss = 0
    disk_sleep = 0
    zombies = 0
    for pid, end in ending.items():
        status = (end["status"] or "").lower()
        if status in {"disk-sleep", "disk_sleep"}:
            disk_sleep += 1
        if status == "zombie":
            zombies += 1
        if pid in own_pids:
            own_rss += int(end["rss"] or 0)
            # cpu was not primed for a useful reading on our own pid; skip
            continue
        start = baseline.get(pid)
        if start is None:
            continue
        cpu_share = max(0.0, float(end["cpu"])) / cpu_count
        read_b, write_b, io_known = _counter_rate(start["read"], end["read"], start["write"], end["write"], elapsed)
        faults = _rate(start["faults"], end["faults"], elapsed)
        major = _rate(start["major"], end["major"], elapsed)
        ctx = _rate(start["ctx"], end["ctx"], elapsed)
        if end["cpu"] == 0 and end["rss"] == 0 and not end["name"]:
            unreadable += 1
            continue
        procs.append(
            Proc(
                pid=pid,
                name=end["name"] or "unknown",
                exe=end["exe"],
                username=end["username"],
                ppid=end["ppid"],
                status=end["status"] or "",
                cpu_raw=cpu_share,
                rss=int(end["rss"] or 0),
                mem_percent=float(end["mem_percent"] or 0.0),
                read_bps=read_b,
                write_bps=write_b,
                io_known=io_known,
                faults_per_sec=faults,
                major_faults_per_sec=major,
                ctx_per_sec=ctx,
                threads=end["threads"],
                handles=end["handles"],
                hung=pid in hung,
                service=end["service"],
            )
        )
    return procs, unreadable, own_cpu_raw / cpu_count, own_rss, disk_sleep, zombies


def _counter_rate(read0, read1, write0, write1, elapsed):
    if None in (read0, read1, write0, write1):
        return 0.0, 0.0, False
    return max(0.0, (read1 - read0) / elapsed), max(0.0, (write1 - write0) / elapsed), True


def _rate(a, b, elapsed):
    if a is None or b is None:
        return None
    if b < a:
        return None
    return (b - a) / elapsed


def _faults(proc, mem) -> tuple[int | None, int | None]:
    total = getattr(mem, "num_page_faults", None)
    major = None
    if os.name == "posix" and os.path.exists(f"/proc/{proc.pid}/stat"):
        parsed = parse_proc_stat_file(proc.pid)
        if parsed is not None:
            minor, major = parsed
            if total is None:
                total = minor + major
    if total is None:
        try:
            full = proc.memory_full_info()
            total = getattr(full, "num_page_faults", None)
        except (psutil.Error, OSError):
            pass
    return (
        int(total) if total is not None else None,
        int(major) if major is not None else None,
    )


def parse_proc_stat_file(pid: int) -> tuple[int, int] | None:
    try:
        with open(f"/proc/{pid}/stat", "r", encoding="utf-8", errors="replace") as handle:
            return parse_proc_stat(handle.read())
    except OSError:
        return None


def parse_proc_stat(text: str) -> tuple[int, int] | None:
    """Return (minflt, majflt) from a /proc/pid/stat line.

    Field numbers match man proc: 10 minflt, 12 majflt, counting from 1,
    and the command name is removed first because it may contain spaces.
    """
    end = text.rfind(")")
    if end < 0:
        return None
    fields = text[end + 2 :].split()
    if len(fields) < 10:
        return None
    try:
        return int(fields[7]), int(fields[9])
    except ValueError:
        return None


def _ctx_total(ctx) -> int | None:
    if ctx is None:
        return None
    voluntary = getattr(ctx, "voluntary", 0) or 0
    involuntary = getattr(ctx, "involuntary", 0) or 0
    return int(voluntary) + int(involuntary)


def _handles(proc) -> int | None:
    try:
        if os.name == "nt":
            return int(proc.num_handles())
        return int(proc.num_fds())
    except (psutil.Error, OSError):
        return None


def _optional(func):
    try:
        return func()
    except (psutil.Error, OSError):
        return None


def _cpu_split(t0, t1) -> tuple[float, float | None]:
    fields = set(getattr(t0, "_fields", ()))
    total = 0.0
    for name in fields:
        total += float(getattr(t1, name)) - float(getattr(t0, name))
    if total <= 0:
        return 0.0, None
    busy = 0.0
    for name in ("user", "system", "nice", "irq", "softirq", "steal"):
        if name in fields:
            busy += float(getattr(t1, name)) - float(getattr(t0, name))
    iowait = None
    if "iowait" in fields:
        iowait = max(0.0, (float(t1.iowait) - float(t0.iowait)) / total * 100.0)
    return max(0.0, busy / total * 100.0), iowait


def _disk_rates(d0, d1, elapsed) -> tuple[float, float]:
    if not d0 or not d1:
        return 0.0, 0.0
    read = max(0.0, (d1.read_bytes - d0.read_bytes) / elapsed)
    write = max(0.0, (d1.write_bytes - d0.write_bytes) / elapsed)
    return read, write


def _disks() -> list[DiskUsage]:
    found: list[DiskUsage] = []
    try:
        parts = psutil.disk_partitions(all=False)
    except (psutil.Error, OSError):
        return found
    seen = set()
    for part in parts:
        fstype = (part.fstype or "").lower()
        if fstype in _SKIP_FS:
            continue
        mount = part.mountpoint
        if mount in seen:
            continue
        try:
            usage = psutil.disk_usage(mount)
        except (psutil.Error, OSError, PermissionError):
            continue
        if usage.total < 5 * 1024 * 1024 * 1024:
            continue
        seen.add(mount)
        found.append(
            DiskUsage(
                mount=mount,
                percent=float(usage.percent),
                free_bytes=int(usage.free),
                total_bytes=int(usage.total),
            )
        )
    return found


def _hottest() -> float | None:
    try:
        sensors = psutil.sensors_temperatures()
    except (AttributeError, psutil.Error, OSError):
        return None
    if not sensors:
        return None
    hottest = None
    for entries in sensors.values():
        for entry in entries:
            current = getattr(entry, "current", None)
            if current is None:
                continue
            if hottest is None or current > hottest:
                hottest = float(current)
    if hottest is None or hottest < 40:
        return None
    return hottest


def _hung_pids() -> set[int]:
    """Windows-only: visible windows the OS itself already calls hung."""
    if os.name != "nt":
        return set()
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return set()
    try:
        user32 = ctypes.windll.user32
        found: set[int] = set()

        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def _each(hwnd, _lparam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                if not user32.IsHungAppWindow(hwnd):
                    return True
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value:
                    found.add(int(pid.value))
            except OSError:
                return True
            return True

        user32.EnumWindows(enum_proc(_each), 0)
        return found
    except (OSError, AttributeError, ValueError):
        return set()
