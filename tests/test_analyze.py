"""Behavior tests for grouping, scoring, and plain-language verdicts."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from whats_slow.analyze import build_report
from whats_slow.demo import demo_report
from whats_slow.events import parse_faulting_app
from whats_slow.model import DiskUsage, EventHit, EventInfo, Proc, Sample
from whats_slow.names import service_from_cmdline
from whats_slow.render import render_html, render_text
from whats_slow.sampler import parse_proc_stat

GB = 1024**3
MB = 1024**2


def proc(**kwargs) -> Proc:
    base = dict(
        pid=1,
        name="app.exe",
        exe=r"C:\Apps\app.exe",
        username="UnitTestUser",
        ppid=1,
        status="running",
        cpu_raw=0.0,
        rss=10 * MB,
        mem_percent=0.1,
        read_bps=0.0,
        write_bps=0.0,
        io_known=True,
        faults_per_sec=None,
        major_faults_per_sec=None,
        ctx_per_sec=None,
        threads=2,
        handles=10,
        hung=False,
        service=None,
    )
    base.update(kwargs)
    return Proc(**base)


def sample(procs, **kwargs) -> Sample:
    base = dict(
        duration_s=8.0,
        cpu_percent=20.0,
        iowait_percent=None,
        cpu_count=8,
        ram_total=16 * GB,
        ram_used=4 * GB,
        ram_percent=25.0,
        swap_total=0,
        swap_used=0,
        swap_percent=0.0,
        disk_read_bps=1 * MB,
        disk_write_bps=1 * MB,
        disks=[],
        process_count=len(procs),
        unreadable=0,
        disk_sleep_count=0,
        zombie_count=0,
        hot_c=None,
        platform="Windows-11",
        procs=procs,
        own_cpu_share=0.0,
        own_rss=0,
    )
    base.update(kwargs)
    return Sample(**base)


def quiet_events() -> EventInfo:
    return EventInfo(available=True, reason="", window_minutes=15, events=[])


class GroupingTests(unittest.TestCase):
    def test_same_program_is_added_together(self):
        report = build_report(
            [
                sample(
                    [
                        proc(pid=1, name="chrome.exe", exe=r"C:\Chrome\chrome.exe", cpu_raw=20, mem_percent=10, rss=GB),
                        proc(pid=2, name="chrome.exe", exe=r"C:\Chrome\chrome.exe", cpu_raw=15, mem_percent=8, rss=GB),
                    ]
                )
            ],
            quiet_events(),
        )
        chrome = next(p for p in report.programs if p.display_name == "Google Chrome")
        self.assertEqual(chrome.count, 2)
        self.assertAlmostEqual(chrome.cpu_share, 35.0)
        self.assertIn("same program", " ".join(chrome.sentences))

    def test_svchost_uses_the_service_name(self):
        self.assertEqual(
            service_from_cmdline(
                "svchost.exe",
                ["svchost.exe", "-k", "LocalSystemNetworkRestricted", "-p", "-s", "SysMain"],
            ),
            "SysMain",
        )
        report = build_report(
            [sample([proc(name="svchost.exe", exe=r"C:\Windows\System32\svchost.exe", service="SysMain", cpu_raw=4)])],
            quiet_events(),
        )
        self.assertEqual(report.programs[0].display_name, "SysMain")
        self.assertIn("Windows service", report.programs[0].sentences[0])

    def test_idle_is_not_blamed(self):
        report = build_report(
            [sample([proc(pid=0, name="System Idle Process", exe=None, cpu_raw=90, username="SYSTEM")])],
            quiet_events(),
        )
        self.assertEqual(report.programs, [])
        self.assertIn("no program used enough", report.headlines[0])


class VerdictTests(unittest.TestCase):
    def test_heavy_cpu_says_it_impedes_others(self):
        report = build_report(
            [sample([proc(name="chrome.exe", exe=r"C:\Chrome\chrome.exe", cpu_raw=58, mem_percent=10, rss=2 * GB)], cpu_percent=90)],
            quiet_events(),
        )
        chrome = report.programs[0]
        self.assertEqual(chrome.severity, "blocking")
        text = " ".join(chrome.sentences)
        self.assertIn("belongs to Google Chrome", text)
        self.assertIn("other programs", text)
        self.assertIn("processor", text.lower())

    def test_disk_hog_is_named(self):
        report = build_report(
            [
                sample(
                    [
                        proc(
                            name="OneDrive.exe",
                            exe=r"C:\OneDrive.exe",
                            cpu_raw=3,
                            read_bps=5 * MB,
                            write_bps=40 * MB,
                        )
                    ],
                    disk_read_bps=10 * MB,
                    disk_write_bps=50 * MB,
                )
            ],
            quiet_events(),
        )
        text = " ".join(report.programs[0].sentences)
        self.assertIn("OneDrive", report.programs[0].display_name)
        self.assertEqual(report.programs[0].severity, "slowing")
        self.assertIn("disk", text.lower())

    def test_memory_pressure_faults_are_explained(self):
        report = build_report(
            [
                sample(
                    [proc(name="chrome.exe", exe=r"C:\Chrome\chrome.exe", cpu_raw=5, mem_percent=20, rss=4 * GB, faults_per_sec=80_000)],
                    ram_percent=94,
                    swap_total=8 * GB,
                    swap_percent=40,
                    swap_used=3 * GB,
                )
            ],
            quiet_events(),
        )
        text = " ".join(report.programs[0].sentences)
        self.assertIn("stutter", text)

    def test_linux_major_faults_count_even_without_the_windows_counter(self):
        report = build_report(
            [
                sample(
                    [proc(name="blender", exe="/usr/bin/blender", cpu_raw=5, major_faults_per_sec=80)],
                    platform="Linux",
                    ram_percent=50,
                )
            ],
            EventInfo(available=False, reason="no windows log", window_minutes=15),
        )
        self.assertIn("memory-to-disk", " ".join(report.programs[0].sentences))

    def test_one_crash_is_not_called_a_storm(self):
        events = EventInfo(
            available=True,
            reason="",
            window_minutes=15,
            events=[
                EventHit("t", "Application", "Application Error", 1000, "Faulting application name: chrome.exe,", "chrome.exe"),
                EventHit("t", "Application", "Application Error", 1000, "Faulting application name: chrome.exe,", "chrome.exe"),
            ],
        )
        report = build_report(
            [sample([proc(name="chrome.exe", exe=r"C:\Chrome\chrome.exe", cpu_raw=58)])],
            events,
        )
        text = " ".join(report.programs[0].sentences)
        self.assertIn("small burst", text)
        self.assertNotIn("stream of failures", text)

    def test_error_stream_on_a_normal_app_does_not_blame_unrelated_programs(self):
        hits = [
            EventHit("t", "Application", "Application Error", 1000, "Faulting application name: Widgets.exe,", "Widgets.exe")
            for _ in range(18)
        ]
        report = build_report(
            [sample([proc(name="Widgets.exe", exe=r"C:\Widgets\Widgets.exe", cpu_raw=0.2)])],
            EventInfo(available=True, reason="", window_minutes=15, events=hits),
        )
        text = " ".join(report.programs[0].sentences)
        self.assertIn("stream of failures", text)
        self.assertIn("unrelated", text)

    def test_error_stream_on_sync_can_impede_others(self):
        hits = [
            EventHit("t", "Application", "Application Error", 1000, "Faulting application name: OneDrive.exe,", "OneDrive.exe")
            for _ in range(40)
        ]
        report = build_report(
            [sample([proc(name="OneDrive.exe", exe=r"C:\OneDrive.exe", cpu_raw=1)])],
            EventInfo(available=True, reason="", window_minutes=15, events=hits),
        )
        text = " ".join(report.programs[0].sentences)
        self.assertIn("other programs", text)
        self.assertEqual(report.programs[0].severity, "slowing")

    def test_hung_window(self):
        report = build_report(
            [sample([proc(name="WINWORD.EXE", exe=r"C:\Office\WINWORD.EXE", cpu_raw=1, hung=True)])],
            quiet_events(),
        )
        self.assertIn("not responding", " ".join(report.programs[0].sentences))
        self.assertEqual(report.programs[0].severity, "slowing")

    def test_full_disk_is_a_whole_pc_problem(self):
        report = build_report(
            [sample([], disks=[DiskUsage("C:\\", 97, 5 * GB, 200 * GB)])],
            quiet_events(),
        )
        self.assertTrue(any("97%" in note and "free" in note for note in report.notes))

    def test_quiet_pc_mentions_the_network(self):
        report = build_report([sample([proc(cpu_raw=1)])], quiet_events())
        self.assertIn("network", " ".join(report.headlines))

    def test_spike_is_not_treated_as_constant(self):
        busy = sample([proc(name="chrome.exe", exe=r"C:\Chrome\chrome.exe", cpu_raw=70)])
        calm = sample([proc(name="chrome.exe", exe=r"C:\Chrome\chrome.exe", cpu_raw=1)])
        report = build_report([busy, calm, calm], quiet_events())
        text = " ".join(report.programs[0].sentences)
        self.assertIn("1 of 3", text)
        self.assertNotEqual(report.programs[0].severity, "blocking")

    def test_event_does_not_match_the_word_system_inside_unrelated_text(self):
        events = EventInfo(
            available=True,
            reason="",
            window_minutes=15,
            events=[
                EventHit("t", "System", "disk", 7, "The device has a bad block.", None),
            ],
        )
        report = build_report(
            [sample([proc(name="System", exe=None, cpu_raw=1)])],
            events,
        )
        # The kernel process may be listed, but the disk error stays a PC-wide note.
        self.assertTrue(any("disk error" in note.lower() for note in report.notes))
        for program in report.programs:
            self.assertEqual(program.events, [])

    def test_html_escapes_program_names(self):
        report = build_report(
            [sample([proc(name="<script>.exe", exe=r"C:\Apps\<script>.exe", cpu_raw=60)])],
            quiet_events(),
        )
        page = render_html(report)
        self.assertNotIn("<script>", page)
        self.assertIn("&" + "lt;script&" + "gt;", page)

    def test_demo_report_covers_the_main_ideas(self):
        report = demo_report()
        text = render_text(report)
        self.assertIn("DEMO DATA", text)
        self.assertIn("Google Chrome", text)
        self.assertIn("OneDrive", text)
        self.assertIn("not responding", text)
        self.assertIn("disk error", text.lower())
        self.assertNotIn("System Idle", text)
        self.assertIn("HOW TO JUDGE", text)


class ProcStatTests(unittest.TestCase):
    def test_parse_proc_stat_skips_spaces_in_the_command_name(self):
        line = "12 (my app) R 1 1 1 0 -1 0 10 0 4 0 1 1 0 0 20 0 1 0 100"
        self.assertEqual(parse_proc_stat(line), (10, 4))

    def test_faulting_application_parser(self):
        self.assertEqual(
            parse_faulting_app("Application Error", "Faulting application name: chrome.exe, version: 1"),
            "chrome.exe",
        )


if __name__ == "__main__":
    unittest.main()
