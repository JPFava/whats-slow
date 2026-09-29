"""Run one or more samples and build the report."""

from __future__ import annotations

import sys
import time

from .analyze import build_report
from .events import EventInfo, collect_events
from .model import Report
from .sampler import take_sample


def run_scan(
    seconds: float = 8,
    repeats: int = 1,
    gap: float = 2,
    include_events: bool = True,
    log=None,
) -> Report:
    say = log or (lambda message: print(message, file=sys.stderr, flush=True))
    repeats = max(1, int(repeats))
    samples = []
    for index in range(repeats):
        say(
            f"Sample {index + 1} of {repeats}: watching the PC for {seconds:.0f} seconds. "
            "Leave your programs as they are."
        )
        samples.append(take_sample(seconds))
        if index + 1 < repeats and gap > 0:
            say(f"Pausing {gap:.0f} seconds before the next sample.")
            time.sleep(gap)
    if include_events:
        say("Checking recent Windows error events, if this is Windows.")
        events = collect_events()
    else:
        events = EventInfo(
            available=False,
            reason="Error events were not requested for this check.",
            window_minutes=15,
        )
    return build_report(samples, events)
