# Advanced System Information Detector

Advanced cross-platform system information detector with verbose output. This Python script provides a detailed overview of your system's hardware, operating system, and running processes, with options for various output formats and content filtering.

## Features

-   **System Overview:** General system information (kernel, hostname, architecture, Python version, boot time, uptime, timezone).
-   **Operating System Details:** OS name, version, codename, and `/etc/os-release` details (Linux).
-   **CPU Information:** Physical/logical cores, frequencies, and per-core/total usage.
-   **Memory Usage:** Virtual and swap memory details (total, used, available, percentage).
-   **Disk Information:** Partitions, mount points, file system types, usage, and I/O statistics.
-   **Network:** Interfaces, IP addresses, network statistics, and active internet connections.
-   **GPU Information:** Detected GPUs, load, memory, and temperature (requires `GPUtil`). Includes fallbacks using `lspci` and `glxinfo`.
-   **Sensor Readings:** Temperatures and fan speeds (requires `psutil`).
-   **Processes:** Top N processes by CPU and memory usage.
-   **Python Environment:** Python executable path, version, flags, and installed pip packages.
-   **Environment Variables:** Key environment variables (HOME, PATH, SHELL) and additional variables.
-   **Users & Sessions:** Active user sessions.
-   **Command Outputs:** Outputs of common system commands like `uname -a`, `whoami`, `env`.
-   **Virtualization Detection:** Detects common virtualization environments (Docker, containers, systemd-detect-virt).
-   **Health Snapshot:** Quick “health score” with ASCII usage bars for CPU, memory, and root disk plus contextual warnings when thresholds are exceeded (powered by a fast psutil sample).
-   **Baseline Comparison:** Load or save JSON reports to compare current metrics against a known-good baseline, surfacing deltas for CPU/memory/disk usage and flagging drift over time.

## Installation

1.  **Clone the repository or download the script:**
    ```bash
    git clone https://github.com/ef-code/advanced_sysinfo.git
    cd advanced_sysinfo
    ```

2.  **Install dependencies (recommended for full features):**
    ```bash
    pip install psutil distro GPUtil
    ```
    *   `psutil`: Highly recommended for detailed CPU, Memory, Disk, Network, Sensor, and Process information.
    *   `distro`: Recommended for detailed Linux distribution information.
    *   `GPUtil`: Recommended for NVIDIA GPU details.

## Usage

Run the script from your terminal:

```bash
python3 advanced_sysinfo.py
```

### Command-line Arguments

-   `--json`: Emit JSON output instead of human-readable text.
-   `--output <file_path>`, `-o <file_path>`: Write the report to a specified file instead of stdout.
-   `--sections <section_name> [<section_name> ...]`: Specify which sections to include (e.g., `cpu memory`). Default is all sections. Use names from report headers or section keys (e.g., `os`, `network`).
-   `--exclude-sections <section_name> [<section_name> ...]`: Specify sections to omit, even if `--sections` includes them implicitly (e.g., `all`).
-   `--max-processes <N>`: Limit the number of top processes listed (default: 10).
-   `--max-packages <N>`: Limit the number of pip packages listed (default: 20, for JSON output).
-   `--indent <N>`: Set the indent spacing for text output (default: 2).
-   `--baseline <path>`: Compare the current run to a previously saved JSON report; useful for monitoring regressions after deployments.
-   `--save-baseline <path>`: Persist this report as a future baseline.

### Examples

**Basic Usage:**
```bash
python3 advanced_sysinfo.py
```

**JSON Output:**
```bash
python3 advanced_sysinfo.py --json --indent 4
```

**Specific Sections (CPU and Memory):**
```bash
python3 advanced_sysinfo.py --sections cpu memory
```

**Output to a file:**
```bash
python3 advanced_sysinfo.py -o system_report.txt
```

**Exclude specific sections:**
```bash
python3 advanced_sysinfo.py --exclude-sections commands virtualization
```

**Health snapshot only (with health score and bars):**
```bash
python3 advanced_sysinfo.py --json --sections health
```

**Compare against a previous baseline:**
```bash
python3 advanced_sysinfo.py --json --baseline last_good.json
```

**Update the baseline after resolving issues:**
```bash
python3 advanced_sysinfo.py --json --save-baseline last_good.json
```

## Contributing

Contributions are welcome.
