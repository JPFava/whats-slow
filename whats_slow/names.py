"""Turn process file names into words a person can recognize."""

from __future__ import annotations

import os
import re

# Exact process / exe names that are symptoms or idle time, not apps to quit.
SYMPTOM_NAMES = {
    "system idle process",
    "idle",
    "memory compression",
    "memcompression",
    "secure system",
    "registry",
    "kswapd0",
    "kswapd",
    "kcompactd0",
}

# These sit on the path of everyday actions (files, search, scans, updates).
# When they thrash or error, other programs feel it.
INTERFERES = {
    "onedrive.exe",
    "filecoauth.exe",
    "dropbox.exe",
    "googledrivefs.exe",
    "explorer.exe",
    "searchindexer.exe",
    "searchhost.exe",
    "searchprotocolhost.exe",
    "searchfilterhost.exe",
    "msmpeng.exe",
    "nissrv.exe",
    "dllhost.exe",
    "sysmain",
    "wsearch",
    "spoolsv.exe",
    "trustedinstaller.exe",
    "tiworker.exe",
    "dosvc",
    "wuauserv",
}

FRIENDLY = {
    "chrome.exe": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Firefox",
    "brave.exe": "Brave",
    "opera.exe": "Opera",
    "code.exe": "Visual Studio Code",
    "slack.exe": "Slack",
    "discord.exe": "Discord",
    "outlook.exe": "Microsoft Outlook",
    "olk.exe": "Outlook",
    "winword.exe": "Microsoft Word",
    "excel.exe": "Microsoft Excel",
    "powerpnt.exe": "PowerPoint",
    "onenote.exe": "OneNote",
    "teams.exe": "Microsoft Teams",
    "ms-teams.exe": "Microsoft Teams",
    "onedrive.exe": "Microsoft OneDrive",
    "filecoauth.exe": "Office file collaboration",
    "searchindexer.exe": "Windows Search",
    "searchhost.exe": "Windows Search",
    "searchprotocolhost.exe": "Windows Search",
    "searchfilterhost.exe": "Windows Search",
    "msmpeng.exe": "Windows Security",
    "nissrv.exe": "Windows Security",
    "securityhealthservice.exe": "Windows Security",
    "explorer.exe": "File Explorer",
    "dwm.exe": "Desktop Window Manager",
    "csrss.exe": "Windows core process",
    "lsass.exe": "Windows sign-in",
    "services.exe": "Windows service manager",
    "wininit.exe": "Windows startup",
    "smss.exe": "Windows session manager",
    "taskmgr.exe": "Task Manager",
    "dllhost.exe": "COM Surrogate",
    "runtimebroker.exe": "Windows app broker",
    "sihost.exe": "Windows shell",
    "ctfmon.exe": "Windows text input",
    "spoolsv.exe": "Print Spooler",
    "trustedinstaller.exe": "Windows Update",
    "tiworker.exe": "Windows Update",
    "mousocoreworker.exe": "Windows Update",
    "compatelrunner.exe": "Windows compatibility task",
    "startmenuexperiencehost.exe": "Start menu",
    "shellexperiencehost.exe": "Windows shell",
    "widgets.exe": "Windows Widgets",
    "widgetservice.exe": "Windows Widgets",
    "steam.exe": "Steam",
    "spotify.exe": "Spotify",
    "node.exe": "Node.js",
    "python.exe": "Python",
    "pythonw.exe": "Python",
    "java.exe": "Java",
    "javaw.exe": "Java",
    "nvcontainer.exe": "NVIDIA helper",
    "nvdisplay.container.exe": "NVIDIA display",
    "audiodg.exe": "Windows audio",
    "conhost.exe": "Console window host",
    "vmmem.exe": "Virtual machine memory",
    "vmmemwsl.exe": "Linux subsystem (WSL)",
    "docker desktop.exe": "Docker Desktop",
    "dropbox.exe": "Dropbox",
    "googledrivefs.exe": "Google Drive",
    "zoom.exe": "Zoom",
    "whatsapp.exe": "WhatsApp",
    "devenv.exe": "Visual Studio",
    "photoshop.exe": "Photoshop",
    "system": "Windows kernel (System)",
    "systemd": "Linux system manager",
}

SERVICE_NAMES = {
    "sysmain": "SysMain",
    "wsearch": "Windows Search",
    "wuauserv": "Windows Update",
    "usosvc": "Windows Update",
    "dosvc": "Delivery Optimization",
    "bits": "Background transfer",
    "spooler": "Print Spooler",
    "wersvc": "Windows Error Reporting",
    "diagtrack": "Windows telemetry",
    "dps": "Diagnostic Policy",
    "schedule": "Task Scheduler",
    "eventlog": "Event Log",
    "windefend": "Windows Security",
    "mpssvc": "Windows Firewall",
    "nlasvc": "Network location",
    "dhcp": "DHCP client",
    "dnscache": "DNS client",
    "lanmanserver": "File sharing",
    "lanmanworkstation": "Network files",
    "themes": "Desktop themes",
    "audiosrv": "Windows Audio",
    "wscsvc": "Security Center",
    "trustedinstaller": "Windows Update",
    "waasmedicsvc": "Windows Update medic",
    "camsvc": "Capability access",
    "cdpsvc": "Connected devices",
    "pcasvc": "Program Compatibility Assistant",
}

ABOUT = {
    "chrome.exe": "Every Chrome process here is one program: the browser, its tabs, and its extensions. This check cannot see which tab.",
    "msedge.exe": "Every Edge process here is one program: the browser, its tabs, and its extensions. This check cannot see which tab.",
    "firefox.exe": "Every Firefox process here is one program: the browser and its tabs. This check cannot see which tab.",
    "brave.exe": "Every Brave process here is one program: the browser and its tabs. This check cannot see which tab.",
    "msmpeng.exe": "This is Windows Security scanning files. A burst of disk or processor use during a scan is normal and should settle. Hours of this, with nothing else going on, means a scan may be stuck.",
    "searchindexer.exe": "Windows is building the catalog that makes file search fast. It is often heavy after many new files, then quiets down. If it never quiets down, indexing may be stuck.",
    "sysmain": "SysMain (once called Superfetch) preloads programs it thinks you will open. On a spinning hard drive this often makes the whole PC feel busy. On an SSD it is usually harmless.",
    "trustedinstaller.exe": "Windows is installing updates. The PC often feels slow until this finishes. Letting it finish is safer than force-closing it.",
    "tiworker.exe": "Windows is installing updates. The PC often feels slow until this finishes. Letting it finish is safer than force-closing it.",
    "mousocoreworker.exe": "This is a Windows Update worker. A burst is normal. Hours of heavy use means updates may be stuck.",
    "wuauserv": "This is the Windows Update service. A burst is normal while updates download. Hours of heavy disk use means an update may be stuck.",
    "usosvc": "This is the Windows Update service. A burst is normal while updates download.",
    "onedrive.exe": "OneDrive is syncing files. While it checks or uploads a lot of files it holds the disk, and File Explorer feels slow because it waits on those same files.",
    "dropbox.exe": "Dropbox is syncing files. While it checks or uploads a lot of files it holds the disk, and File Explorer feels slow because it waits on those same files.",
    "googledrivefs.exe": "Google Drive is syncing files. While it checks or uploads a lot of files it holds the disk, and File Explorer feels slow because it waits on those same files.",
    "explorer.exe": "This is the taskbar, Start menu, and file windows. If it is the busy one, the slowdown is File Explorer itself or an add-in inside it.",
    "dwm.exe": "This draws the desktop. Heavy use can mean a display-driver problem, a second monitor, or a lot of animated windows.",
    "system": "This is the Windows kernel, not an app you opened. High disk use here is often a driver, antivirus, or the PC running out of memory.",
    "vmmem.exe": "This is the processor and memory used by a virtual machine or Linux under Windows (WSL). The real work is inside that machine.",
    "vmmemwsl.exe": "This is the processor and memory used by Linux under Windows (WSL). The real work is inside Linux.",
    "dllhost.exe": "A Windows helper that hosts small add-ins, including some file previews. One busy copy can make folders open slowly.",
    "audiodg.exe": "Windows audio. A little use is normal. Constant high use is not.",
    "compatelrunner.exe": "A Windows compatibility task. It should be occasional, not a constant load.",
    "diagtrack": "A Windows telemetry service. It should not be one of the heaviest things on the PC.",
    "dosvc": "Delivery Optimization downloads Windows updates and can share them with other PCs. It can use a lot of disk after an update.",
    "wsearch": "The Windows Search service. It is often heavy after many new files, then settles.",
    "conhost.exe": "This draws the window for a command-line tool. The program that opened the console is usually the real workload.",
    "runtimebroker.exe": "A small Windows helper for Store apps. Light use is normal.",
    "svchost.exe": "Windows runs many background services inside svchost. The service name in the title is the part that is actually busy.",
    "spoolsv.exe": "The print spooler. It should be quiet unless something is printing or a print job is stuck.",
    "kswapd0": "The kernel is shuffling memory because RAM is overfull. The large programs are the cause, not kswapd itself.",
}

ADVICE = {
    "chrome.exe": "Close tabs you are not using and turn off extensions you do not recognize. Then restart Chrome. If it is still this heavy with one window, the problem is an extension or a single site.",
    "msedge.exe": "Close tabs you are not using and turn off extensions you do not recognize. Then restart Edge.",
    "firefox.exe": "Close tabs you are not using and turn off extensions you do not recognize. Then restart Firefox.",
    "brave.exe": "Close tabs you are not using and turn off extensions you do not recognize. Then restart Brave.",
    "msmpeng.exe": "If a virus scan just started, let it finish. If Windows Security is this heavy all day, open Windows Security and see whether a scan is stuck.",
    "searchindexer.exe": "If you just copied a lot of files, give Windows Search an hour. If it is still heavy tomorrow, indexing may be stuck on a particular folder.",
    "wsearch": "If you just copied a lot of files, give Windows Search an hour. If it is still heavy tomorrow, indexing may be stuck on a particular folder.",
    "onedrive.exe": "Click the OneDrive cloud icon, choose Pause syncing, and see if the PC feels normal. If it does, a sync backlog was the cause.",
    "dropbox.exe": "Pause Dropbox syncing and see if the PC feels normal. If it does, a sync backlog was the cause.",
    "googledrivefs.exe": "Pause Google Drive syncing and see if the PC feels normal. If it does, a sync backlog was the cause.",
    "trustedinstaller.exe": "Let Windows Update finish, then restart the PC. Force-closing the installer can leave an update half-done.",
    "tiworker.exe": "Let Windows Update finish, then restart the PC. Force-closing the installer can leave an update half-done.",
    "mousocoreworker.exe": "Let Windows Update finish, then restart the PC.",
    "wuauserv": "Let Windows Update finish, then restart the PC.",
    "usosvc": "Let Windows Update finish, then restart the PC.",
    "sysmain": "On a spinning hard drive, SysMain often causes the slowness. A technician can disable that service. On an SSD, leave it alone unless it stays this busy for days.",
    "explorer.exe": "Save your work and restart File Explorer (Task Manager, find File Explorer, Restart). If folders are slow only in one directory, a preview add-in or a cloud file there is the usual cause.",
    "dwm.exe": "Restart the PC. If Desktop Window Manager is heavy every day, update the display driver from the PC or graphics-card maker, not from a random download site.",
    "vmmem.exe": "The load is inside a virtual machine or WSL. Shut that down if you are not using it.",
    "vmmemwsl.exe": "The load is inside Linux (WSL). Close that window if you are not using it.",
}


def exe_basename(exe: str | None, name: str) -> str:
    """File name only. Accepts both Windows and Unix separators."""
    raw = exe or name or "unknown"
    normalized = raw.replace("\\", "/")
    return os.path.basename(normalized)


def service_from_cmdline(name: str, cmdline: list[str] | None) -> str | None:
    """Pull the Windows service name out of a svchost command line.

    Modern Windows looks like: svchost.exe -k Group -p -s ServiceName
    Older Windows only has -k Group, which is a bundle of services.
    """
    base = os.path.basename(name or "").lower()
    if base not in {"svchost.exe", "svchost"}:
        return None
    args = cmdline or []
    lowered = [a.lower() for a in args]
    if "-s" in lowered:
        i = lowered.index("-s")
        if i + 1 < len(args):
            token = args[i + 1].strip()
            if token and not token.startswith("-"):
                return token
    if "-k" in lowered:
        i = lowered.index("-k")
        if i + 1 < len(args):
            token = args[i + 1].strip()
            if token and not token.startswith("-"):
                return token
    return None


def _lookup_about(exe_name: str, service: str | None) -> str:
    if service:
        key = service.lower()
        if key in ABOUT:
            return ABOUT[key]
    base = exe_name.lower()
    return ABOUT.get(base, "")


def interferes(exe_name: str, service: str | None) -> bool:
    if exe_name.lower() in INTERFERES:
        return True
    if service and service.lower() in INTERFERES:
        return True
    return False


def is_symptom_name(exe_name: str, proc_name: str) -> bool:
    a = exe_name.lower()
    b = proc_name.lower()
    stem = os.path.splitext(a)[0]
    return a in SYMPTOM_NAMES or b in SYMPTOM_NAMES or stem in SYMPTOM_NAMES


def friendly_name(exe_name: str, service: str | None) -> str:
    if service:
        key = service.lower()
        pretty = SERVICE_NAMES.get(key)
        if pretty:
            return pretty
        # "-k netsvcs" style bundle: keep it readable, do not shout the raw token.
        if key.endswith("services"):
            return "Windows services (" + service[: -len(" services")] + ")"
        spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", service).strip()
        return spaced or service
    base = exe_name.lower()
    if base in FRIENDLY:
        return FRIENDLY[base]
    stem = os.path.splitext(exe_name)[0]
    if not stem:
        return "Unknown program"
    return stem


def about_for(exe_name: str, service: str | None) -> str:
    return _lookup_about(exe_name, service)


def advice_for(program_exe: str, service: str | None, display: str, kind: str) -> str:
    """kind is 'cpu', 'memory', 'disk', 'hung', or 'errors' — the main reason."""
    for key in (service.lower() if service else "", program_exe.lower()):
        if key and key in ADVICE:
            return ADVICE[key]
    if kind == "hung":
        return (
            f"Save anything open in {display} if you can, then close it. "
            "A window Windows already calls 'not responding' usually will not recover on its own."
        )
    if kind == "memory":
        return (
            f"Close {display} to give memory back. If this PC has 8 GB of RAM or less, "
            "a browser plus Office can fill it with nothing else broken."
        )
    if kind == "disk":
        return (
            f"{display} is the program busy on the disk. If you started a copy, scan, or update, wait. "
            "If you did not, quit it and see whether folders open faster."
        )
    if kind == "errors":
        return (
            f"{display} is the program the errors point at. Quit and reopen it. "
            "If the same errors return every hour, reinstall that program or ask whoever supports it."
        )
    return (
        f"Save your work in {display} and close it. If the PC immediately feels normal, that program was the load. "
        "If it is heavy every time it starts, check its own settings or reinstall it."
    )
