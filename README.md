# What is slowing this PC?

A small check you run **on the PC that feels slow**. It watches for a few seconds, groups processes under the real program they belong to, and says in plain language whether that program is using enough processor, memory, or disk — or failing often enough — to get in the way of everything else.

It does not close programs. It does not change settings. It does not send the report anywhere.

## Is this possible?

Yes, with a clear limit.

The operating system will tell a program like this:

- which processes are running, and the program file they belong to (`chrome.exe` is Google Chrome, even when Chrome is split into dozens of processes)
- how much of the **whole PC** those processes used during the sample: processor, memory, and disk
- whether Windows itself has already marked a window as **not responding**
- whether Windows **wrote errors to its log** in the last 15 minutes (crashes, hangs, disk errors)

The operating system will **not** tell anyone the exceptions a program caught and hid inside itself. There is no honest "this app threw 400 errors per second" number unless the program, or Windows, recorded those errors. A slow PC is usually resource contention, not a hidden error counter. This check says so when that is the case, instead of inventing a rate.

A website cannot do this for you. The check has to run on your machine, because that is where the processes are.

## Install and run on Windows

You do not need Git.

1. Install Python 3.9 or newer from [python.org/downloads](https://www.python.org/downloads/). On the first installer screen, check **Add python.exe to PATH**.
2. Open this repository in a browser: [github.com/JPFava/whats-slow](https://github.com/JPFava/whats-slow).
3. Click the green **Code** button, then **Download ZIP**.
4. Right-click the zip and choose **Extract All**. Open the extracted folder.
5. Double-click **`run.bat`**.

The window looks paused for several seconds. That pause is the measurement. Leave the slow programs open while it watches. When it finishes, your browser opens the report. A copy is in the `reports` folder next to `run.bat`.

If Windows says Python was not found, and you already installed it: open **Settings → Apps → Advanced app settings → App execution aliases** and turn **off** the aliases for `python.exe` and `python3.exe`. Then run `run.bat` again.

If the report says many processes could not be measured, right-click `run.bat` and choose **Run as administrator**. The tool still only reads.

You can open `run.bat` in Notepad first. It is a short list of commands, not an installer.

### Useful Windows runs

Open Command Prompt in this folder (click the address bar of the folder, type `cmd`, press Enter) and run:

```bat
run.bat --demo
run.bat --seconds 20 --repeat 3
```

- `--demo` is a **made-up** overloaded PC, so you can practice reading a report. It is not your computer.
- `--seconds 20 --repeat 3` watches for 20 seconds, three times. Use this to tell a real load from a one-time spike.

A page on this PC only (other computers cannot open it):

```bat
run.bat --serve
```

Then open `http://127.0.0.1:8765` in your browser. If Windows asks about a network, you can cancel and instead open the HTML file in `reports`. The page is bound to this PC only.

## Install and run on a Mac or Linux

```bash
git clone https://github.com/JPFava/whats-slow.git
cd whats-slow
bash run.sh
```

Or, without Git, download the ZIP, unzip it, and run `bash run.sh` from that folder.

Practice first: `bash run.sh --demo`

A more reliable check while the machine feels slow: `bash run.sh --seconds 20 --repeat 3`

Error totals are collected on Windows. On a Mac or Linux the report still covers processor, memory, and disk, and it says that the Windows error log is not available.

## What the report is answering

For each program that matters, the report says four things, in this order:

1. **Which program** the processes belong to, and the file on disk. Twenty Chrome processes are one program.
2. **What it is using**, as a share of the whole PC. "55% of the processor" means 55% of the entire computer, not 55% of one core. Task Manager's number for the same process is often higher, because 100% there can mean a single core.
3. **Whether that is enough to slow other programs**, and why: they are waiting for the processor, waiting for memory, waiting behind disk activity, waiting on a frozen window, or waiting on a program that keeps failing.
4. **What to do next.** Suggestions only. Nothing is closed for you.

Programs that are quiet are counted and then left off the page, so the list stays short.

## How to evaluate the results

Do this in order. The same instructions are printed at the bottom of every report.

1. **Practice on the demo** (`run.bat --demo` or `bash run.sh --demo`). You should see Google Chrome, OneDrive, and Word called out, a nearly full drive, a disk error, and a note that two Chrome errors are a small burst rather than a storm. [examples/sample-report.txt](examples/sample-report.txt) is that same demo, saved.
2. **Run it while the PC feels slow**, not after it has recovered. A check taken when things feel fine will look fine.
3. **Read the summary first.** It names the programs that are in the way, and it names whole-PC problems (memory almost full, a drive almost full, the PC waiting on the disk, heat).
4. **Confirm before you quit something important.** Run `run.bat --seconds 20 --repeat 3`. 
   - High in **all** samples: it is a real load.
   - High in **one** sample: it was probably a spike (an update, a scan, a file copy). Run once more later before treating it as the cause.
5. **Read the error sentence carefully.**
   - No errors, or one or two in 15 minutes: that is a crash or a small burst. Judge the slowdown from processor, memory, and disk, not from that burst.
   - Several per minute: that program is actually failing in a stream. If it is file sync, search, File Explorer, security, or Windows Update, other programs can stall behind it. If it is an ordinary app, the failures make **that** app unreliable. They do not, by themselves, prove it is slowing unrelated programs.
6. **Check the "processor is only N% busy" line.** If the processor is mostly free and memory is not full, quitting apps will not fix a PC that only feels slow in the browser. That is the network, or one site, not a program hogging the computer.
7. **Use the rules of thumb below** if you want to see why a program was or was not listed. They are the rules in the program, not a lab measurement of your hardware.

### Rules of thumb

These are applied to the **average across the samples**, so one brief spike does not dominate. "Processor" is the share of the whole PC.

| What was measured | Worth watching | Slowing other programs | Slowing other programs a lot |
| --- | --- | --- | --- |
| Processor | 15% | 30% | 50% |
| Memory | 12% of RAM | 25% | 45% |
| Disk, sustained during the check | 8 MB/s | 25 MB/s | 70 MB/s |
| A window Windows already calls not responding | | listed as slowing | |
| Errors from a sync, search, Explorer, security, or update program | a small burst is only mentioned | about 2 per minute | |

Also called out for the **whole PC**, because they slow every program at once:

- A drive **90% full or more** (updates fail, and Windows itself gets slow, under about 15% free).
- Memory **about 90% full and already using the disk as extra RAM**.
- The processor spending a large share of its time **waiting on the disk**.
- **Disk errors** in the Windows log. That is a storage warning. Back up files you cannot replace.
- A very high temperature reading, when the PC exposes one. Heat makes the PC slow itself down.

The impact number (out of 100) only **ranks** programs against each other. It is not a health grade and it is not a virus score. Read the sentences.

### What a result usually means

| What you see | Reasonable next step |
| --- | --- |
| One browser, heavy every sample | Close unused tabs and turn off extensions you do not recognize. Restart the browser. This check cannot see which tab. |
| OneDrive, Dropbox, or Google Drive busy on the disk | Pause syncing. If the PC feels normal, the sync backlog was the cause. |
| Windows Security heavy | If a scan just started, let it finish. If it is heavy all day, see whether a scan is stuck. |
| Windows Update heavy | Let it finish, then restart. Force-closing the installer can leave an update half-done. |
| SysMain heavy on a spinning hard drive | This service preloads apps and often makes a hard drive feel busy. On an SSD it is usually harmless. |
| File Explorer heavy, or "not responding" | Restart File Explorer from Task Manager. A slow folder is often one cloud file or a preview add-in. |
| Memory almost full, page activity called out | Close the largest program. A PC with 8 GB of RAM can be filled by a browser plus Office with nothing else broken. |
| Drive almost full | Free space until at least 15% is free, then restart. |
| Disk errors | Back up, then check the drive or have a shop do it. This is not fixed by uninstalling an app. |
| Nothing listed, processor mostly free | The slowness is likely the network, a spike this sample missed, or a program that is waiting rather than working. Run the 20-second, 3-repeat check during the slow moment. |
| System Idle Process would have been "high" | That is not a program. A high idle figure means the processor is **free**. This check does not list it as a cause. |

## What this cannot tell you

- Which browser tab or extension is the heavy one. Only the whole browser.
- Hidden exceptions that never reached the Windows log.
- Whether a program is malicious. A heavy unknown program is a reason to be curious, not a verdict. If you do not recognize the program file, search the file name before you delete anything, and do not download a "cleaner" to do it.
- Internet speed, Wi-Fi, or a slow website.
- A failing drive that has not yet written an error and is not showing up as long waits. If the PC is slow and this report is quiet every time, a technician can still check the drive and the memory separately.

## Privacy and safety

- The check reads performance counters and, on Windows, recent error events. It does not read your documents.
- Reports are written only into the `reports` folder. They include program names, file paths, and sometimes the Windows account name a process is running as. Command lines are not printed, because those can contain private text.
- Nothing is uploaded. There is no account and no telemetry.
- To erase a check, delete the `reports` folder.
- Some antivirus tools warn about any program that looks at other programs. You can read every file in this repository. The entry point is `whats_slow/__main__.py`. The verdict rules are in `whats_slow/analyze.py`.

## Check the rules themselves

From this folder, after Python is installed:

```bat
python -m unittest discover -s tests -v
```

On a Mac or Linux, use `python3` instead of `python`. The tests feed in fake process data, including the demo PC, and check the sentences. They do not need a slow computer. They passed when this repository was published: 19 tests.

## Remove it

Delete the folder you extracted or cloned. That removes the tool, its private Python environment (`.venv`), and the reports.

## License

MIT. See [LICENSE](LICENSE).
