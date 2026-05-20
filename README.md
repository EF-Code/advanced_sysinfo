# Advanced System Information Detector

`advanced_sysinfo.py` is a single-file Python CLI that collects system diagnostics and renders them as either human-readable text or JSON.

The program is designed to degrade gracefully when optional dependencies or platform-specific commands are unavailable. It now also defaults to safer output for environment data so the report is less likely to leak secrets by accident.

## What It Reports

- System overview: host, kernel, architecture, Python runtime, boot time, uptime, timezone.
- Operating system details: platform metadata plus `/etc/os-release` when available.
- CPU: core counts, frequencies, total usage, and per-core usage.
- Memory: virtual and swap usage.
- Disks: partitions, usage, and aggregate I/O, with per-mount error isolation.
- Network: interfaces, addresses, I/O counters, and a bounded sample of active sockets.
- GPU: NVIDIA details through `GPUtil`, with command fallbacks when available.
- Sensors: temperature and fan readings when the current platform exposes them.
- Processes: sampled top processes by CPU and memory usage.
- Python environment: interpreter details and installed packages.
- Environment: a safe summary by default, with full values only on explicit request.
- Users and sessions.
- Command outputs: `uname` and `whoami` by default, full `env` only on explicit request.
- Virtualization markers.
- Health snapshot: CPU, memory, root disk bars, warnings, and score.
- Baseline comparison: compare current metrics to a previous JSON report.

## Dependencies

The script runs with the Python standard library alone, but several sections are improved by optional packages:

```bash
pip install psutil distro GPUtil
```

- `psutil`: CPU, memory, disk, network, processes, users, sensors, health metrics.
- `distro`: richer Linux distribution reporting.
- `GPUtil`: NVIDIA GPU inventory and usage.

## Usage

```bash
python3 advanced_sysinfo.py
```

### Output modes

- Default: text report to stdout.
- `--json`: emit JSON.
- `--output FILE`: write the rendered report to a file.
- `--save-baseline FILE`: save the full JSON report as a future baseline.
- `--list-sections`: print all available section keys and exit.

### Section selection

- `--sections cpu memory network`
- `--exclude-sections environment commands`
- Section names accept either internal keys such as `cpu` or visible headers such as `CPU`.
- Unknown section names do not crash the program; they are reported in metadata or a warnings block.
- The report metadata includes runtime capability detection and per-section timing so automation can explain partial output.

### Safety controls

- Full environment values are hidden by default.
- Raw `env` command output is skipped by default.
- `--include-sensitive` enables both of those behaviors explicitly.

### Sampling and comparison controls

- `--max-processes N`: limit process rows.
- `--max-packages N`: limit package rows.
- `--connection-limit N`: limit socket samples.
- `--cpu-interval SECONDS`: CPU sampling window for aggregate CPU usage.
- `--process-interval SECONDS`: sampling window for per-process CPU usage.
- `--baseline FILE`: compare current metrics with a saved baseline.
- `--baseline-threshold VALUE`: minimum absolute metric delta required before drift is flagged.
- `--fail-on-warnings`: return a non-zero exit code when the report contains section-selection warnings or collector failures.

## Examples

Basic report:

```bash
python3 advanced_sysinfo.py
```

JSON output:

```bash
python3 advanced_sysinfo.py --json --indent 4
```

CPU and memory only:

```bash
python3 advanced_sysinfo.py --sections cpu memory
```

Health snapshot only:

```bash
python3 advanced_sysinfo.py --sections health
```

Write a report to disk:

```bash
python3 advanced_sysinfo.py --output system_report.txt
```

Compare against a baseline:

```bash
python3 advanced_sysinfo.py --json --baseline last_good.json
```

Save a new baseline:

```bash
python3 advanced_sysinfo.py --json --save-baseline last_good.json
```

Include full environment values intentionally:

```bash
python3 advanced_sysinfo.py --sections environment commands --include-sensitive
```

## Testing

Run the unit tests with:

```bash
python3 -m unittest discover -s tests -v
```

## Notes On Platform Coverage

This tool works across platforms at a basic level, but some sections depend on what the host OS exposes. Linux-specific files and commands are used opportunistically rather than assumed to exist. Missing commands or unsupported APIs should result in partial section output instead of a full program failure.
