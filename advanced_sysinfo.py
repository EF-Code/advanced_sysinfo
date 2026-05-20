#!/usr/bin/env python3
"""Advanced system information detector with safer, more robust defaults."""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from collections import OrderedDict
from typing import Any, Callable, Iterable, Mapping, MutableMapping, Sequence

try:
    import psutil
except ImportError:
    psutil = None

try:
    import distro as _distro
except ImportError:
    _distro = None

try:
    import GPUtil as _gputil
except ImportError:
    _gputil = None


SectionData = Mapping[str, Any]
SectionFactory = Callable[[argparse.Namespace], SectionData]
SENSITIVE_ENV_MARKERS = (
    "API_KEY",
    "ACCESS_KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASS",
    "COOKIE",
    "AUTH",
    "PRIVATE",
    "CREDENTIAL",
)
SENSITIVE_ENV_EXACT_KEYS = {
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "DATABASE_URL",
    "DB_URL",
    "GITHUB_TOKEN",
    "OPENAI_API_KEY",
    "SSH_AUTH_SOCK",
}
SAFE_ENV_KEYS = (
    "HOME",
    "PATH",
    "SHELL",
    "USER",
    "LANG",
    "TERM",
    "PYTHONPATH",
    "VIRTUAL_ENV",
)


def bytes2human(value: float | int | None, suffix: str = "B") -> str:
    if value is None:
        return "n/a"
    value = float(value)
    units = ["", "K", "M", "G", "T", "P", "E"]
    abs_value = abs(value)
    for unit in units:
        if abs_value < 1024.0:
            return f"{value:.2f}{unit}{suffix}"
        value /= 1024.0
        abs_value = abs(value)
    return f"{value:.2f}{units[-1]}{suffix}"


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than 0")
    return parsed


def non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be 0 or greater")
    return parsed


def short_repr(value: Any, max_width: int = 200) -> str:
    if value is None:
        return "null"
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    text = str(value)
    return text if len(text) <= max_width else text[:max_width] + "..."


def safe_subprocess(cmd: Sequence[str], timeout: float = 5.0) -> Mapping[str, Any]:
    """Run a command safely and return structured output."""

    result: MutableMapping[str, Any] = {
        "command": " ".join(cmd),
        "stdout": "",
        "stderr": "",
        "returncode": None,
    }
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        result["stdout"] = completed.stdout.strip()
        result["stderr"] = completed.stderr.strip()
        result["returncode"] = completed.returncode
    except (subprocess.SubprocessError, OSError) as exc:
        result["stderr"] = str(exc)
    return result


def safe_call(func: Callable[..., Any], *args: Any, **kwargs: Any) -> tuple[Any, str | None]:
    try:
        return func(*args, **kwargs), None
    except Exception as exc:  # pragma: no cover - broad by design for resilience
        return None, str(exc)


def safe_disk_usage(path: str) -> tuple[Any, str | None]:
    if not psutil:
        return None, "psutil missing"
    return safe_call(psutil.disk_usage, path)


def parse_os_release() -> Mapping[str, str]:
    release_file = "/etc/os-release"
    info: MutableMapping[str, str] = {}
    if not os.path.exists(release_file):
        return info
    try:
        with open(release_file, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if "=" not in line:
                    continue
                key, _, raw_value = line.partition("=")
                info[key] = raw_value.strip().strip('"')
    except OSError:
        pass
    return info


def gather_system_overview(args: argparse.Namespace) -> SectionData:
    uname = platform.uname()
    overview: MutableMapping[str, Any] = {
        "System": uname.system,
        "Node": uname.node,
        "Release": uname.release,
        "Version": uname.version,
        "Machine": uname.machine,
        "Processor": uname.processor or platform.processor(),
        "Platform": platform.platform(terse=False),
        "Architecture": platform.architecture()[0],
        "Python": platform.python_implementation(),
        "Python version": platform.python_version(),
        "Local timezone": datetime.datetime.now(datetime.timezone.utc).astimezone().tzname() or "unknown",
    }
    if psutil:
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time(), datetime.timezone.utc).astimezone()
        overview["Boot time"] = boot_time.isoformat()
        overview["Uptime"] = str(datetime.datetime.now(datetime.timezone.utc).astimezone() - boot_time).split(".")[0]
    else:
        overview["Boot time"] = "psutil missing"
        overview["Uptime"] = "psutil missing"
    return overview


def gather_os_details(args: argparse.Namespace) -> SectionData:
    info: MutableMapping[str, Any] = {
        "System": platform.system(),
        "Release": platform.release(),
        "Version": platform.version(),
    }
    if _distro:
        info["Distribution"] = {
            "Name": _distro.name(pretty=True) or _distro.name(),
            "Version": _distro.version(),
            "Codename": _distro.codename(),
            "Like": _distro.like(),
        }
    os_release = parse_os_release()
    if os_release:
        info["/etc/os-release"] = dict(sorted(os_release.items()))
    return info


def gather_memory(args: argparse.Namespace) -> SectionData:
    memory: MutableMapping[str, Any] = {}
    if not psutil:
        memory["status"] = "psutil missing"
        return memory
    vm = psutil.virtual_memory()
    memory["Virtual total"] = bytes2human(vm.total)
    memory["Available"] = bytes2human(vm.available)
    memory["Used"] = bytes2human(vm.used)
    memory["Usage"] = f"{vm.percent:.1f}%"
    swap = psutil.swap_memory()
    memory["Swap total"] = bytes2human(swap.total)
    memory["Swap used"] = bytes2human(swap.used)
    memory["Swap usage"] = f"{swap.percent:.1f}%"
    return memory


def gather_cpu_fallback(args: argparse.Namespace) -> SectionData:
    info: MutableMapping[str, Any] = {
        "Logical cores": os.cpu_count(),
        "Processor": platform.processor() or platform.machine(),
    }
    lscpu = shutil.which("lscpu")
    if lscpu:
        info["lscpu"] = safe_subprocess([lscpu], timeout=3)
    return info


def gather_cpu(args: argparse.Namespace) -> SectionData:
    cpu: MutableMapping[str, Any] = {}
    if not psutil:
        cpu["status"] = "psutil missing"
        cpu.update(gather_cpu_fallback(args))
        return cpu
    cpu["Physical cores"] = psutil.cpu_count(logical=False)
    cpu["Logical cores"] = psutil.cpu_count(logical=True)
    freq, freq_error = safe_call(psutil.cpu_freq)
    if freq_error:
        cpu["Frequency error"] = freq_error
    elif freq:
        cpu["Max frequency"] = f"{freq.max:.2f} MHz"
        cpu["Min frequency"] = f"{freq.min:.2f} MHz"
        cpu["Current frequency"] = f"{freq.current:.2f} MHz"
    cpu["Usage (per core)"] = [f"{x:.1f}%" for x in psutil.cpu_percent(percpu=True, interval=args.cpu_interval)]
    cpu["Usage (total)"] = f"{psutil.cpu_percent(interval=None):.1f}%"
    return cpu


def gather_disks(args: argparse.Namespace) -> SectionData:
    disks: MutableMapping[str, Any] = {}
    if not psutil:
        disks["status"] = "psutil missing"
        df = shutil.which("df")
        if df:
            disks["df -h"] = safe_subprocess([df, "-h"], timeout=3)
        return disks

    partitions = []
    seen_mounts: set[str] = set()
    for partition in psutil.disk_partitions(all=False):
        if partition.mountpoint in seen_mounts:
            continue
        seen_mounts.add(partition.mountpoint)
        usage, error = safe_disk_usage(partition.mountpoint)
        entry: MutableMapping[str, Any] = {
            "Device": partition.device,
            "Mountpoint": partition.mountpoint,
            "Type": partition.fstype,
        }
        if error:
            entry["Error"] = error
        elif usage:
            entry["Total"] = bytes2human(usage.total)
            entry["Used"] = bytes2human(usage.used)
            entry["Free"] = bytes2human(usage.free)
            entry["Percent"] = f"{usage.percent:.1f}%"
        partitions.append(entry)
    disks["Partitions"] = partitions
    io_counters, io_error = safe_call(psutil.disk_io_counters, perdisk=False)
    if io_error:
        disks["IO error"] = io_error
    elif io_counters:
        disks["IO"] = {
            "Read": bytes2human(io_counters.read_bytes),
            "Write": bytes2human(io_counters.write_bytes),
            "Read ops": io_counters.read_count,
            "Write ops": io_counters.write_count,
        }
    return disks


def serialize_address(addr: Any) -> Mapping[str, Any]:
    data: MutableMapping[str, Any] = {"Address": addr.address}
    if getattr(addr, "netmask", None):
        data["Netmask"] = addr.netmask
    if getattr(addr, "broadcast", None):
        data["Broadcast"] = addr.broadcast
    if getattr(addr, "ptp", None):
        data["PTP"] = addr.ptp
    return data


def serialize_connections(connections: Sequence[Any], limit: int) -> Sequence[Mapping[str, Any]]:
    results: list[Mapping[str, Any]] = []
    for conn in connections[:limit]:
        laddr = conn.laddr if getattr(conn, "laddr", None) else None
        raddr = conn.raddr if getattr(conn, "raddr", None) else None
        results.append(
            {
                "fd": conn.fd,
                "family": conn.family.name if hasattr(conn.family, "name") else str(conn.family),
                "type": conn.type.name if hasattr(conn.type, "name") else str(conn.type),
                "laddr": f"{laddr.ip}:{laddr.port}" if laddr else None,
                "raddr": f"{raddr.ip}:{raddr.port}" if raddr else None,
                "status": conn.status,
                "pid": conn.pid,
            }
        )
    return results


def gather_network(args: argparse.Namespace) -> SectionData:
    network: MutableMapping[str, Any] = {}
    if not psutil:
        network["status"] = "psutil missing"
        return network
    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
    except (PermissionError, OSError) as exc:
        network["error"] = str(exc)
        return network

    interfaces = {}
    for name, addr_list in addrs.items():
        interface: MutableMapping[str, Any] = {"Addresses": [serialize_address(addr) for addr in addr_list]}
        stats_entry = stats.get(name)
        if stats_entry:
            interface["Up"] = stats_entry.isup
            interface["Speed"] = f"{stats_entry.speed}Mbps" if stats_entry.speed else "unknown"
            interface["Duplex"] = str(stats_entry.duplex)
            interface["MTU"] = stats_entry.mtu
        interfaces[name] = interface
    network["Interfaces"] = interfaces

    counters, counter_error = safe_call(psutil.net_io_counters, pernic=False)
    if counter_error:
        network["IO error"] = counter_error
    elif counters:
        network["IO"] = {
            "Bytes sent": bytes2human(counters.bytes_sent),
            "Bytes received": bytes2human(counters.bytes_recv),
            "Packets sent": counters.packets_sent,
            "Packets received": counters.packets_recv,
        }

    try:
        connections = psutil.net_connections(kind="inet")
    except (PermissionError, OSError) as exc:
        network["Connection error"] = str(exc)
        return network
    network["Connection summary"] = {
        "Total sockets": len(connections),
        "TCP": sum(1 for conn in connections if conn.type == socket.SOCK_STREAM),
        "UDP": sum(1 for conn in connections if conn.type == socket.SOCK_DGRAM),
    }
    network["Connection sample"] = serialize_connections(connections, limit=args.connection_limit)
    return network


def gather_gpu_fallback() -> SectionData:
    info: MutableMapping[str, Any] = {}
    lspci = shutil.which("lspci")
    if lspci:
        info["lspci"] = safe_subprocess([lspci, "-nnk"], timeout=5)
    glxinfo = shutil.which("glxinfo")
    if glxinfo:
        info["glxinfo"] = safe_subprocess([glxinfo, "-B"], timeout=5)
    if not info:
        info["status"] = "No fallback commands available"
    return info


def gather_gpu(args: argparse.Namespace) -> SectionData:
    info: MutableMapping[str, Any] = {}
    if not _gputil:
        info["status"] = "GPUtil not installed"
        info["Fallback"] = gather_gpu_fallback()
        return info
    gpus, error = safe_call(_gputil.getGPUs)
    if error:
        info["error"] = error
        return info
    info["Count"] = len(gpus)
    info["GPUs"] = [
        {
            "id": gpu.id,
            "name": gpu.name,
            "load": f"{gpu.load * 100:.1f}%",
            "memory": f"{gpu.memoryTotal}MB total, {gpu.memoryUsed}MB used",
            "temperature": f"{gpu.temperature} C",
        }
        for gpu in gpus
    ]
    return info


def gather_sensors(args: argparse.Namespace) -> SectionData:
    readings: MutableMapping[str, Any] = {}
    if not psutil:
        readings["status"] = "psutil missing"
        return readings
    temps, temp_error = safe_call(psutil.sensors_temperatures, fahrenheit=False)
    if temp_error:
        readings["Temperature error"] = temp_error
    elif temps:
        readings["Temperatures"] = {
            sensor: [f"{entry.current:.1f}C" for entry in entries]
            for sensor, entries in temps.items()
        }
    fans, fan_error = safe_call(psutil.sensors_fans)
    if fan_error:
        readings["Fan error"] = fan_error
    elif fans:
        readings["Fans"] = {
            fan: [f"{entry.current} RPM" for entry in entries]
            for fan, entries in fans.items()
        }
    if not readings:
        readings["status"] = "No sensor data available"
    return readings


def sample_processes(interval: float) -> list[Mapping[str, Any]]:
    if not psutil:
        return []
    processes = []
    for proc in psutil.process_iter(attrs=["pid", "name", "memory_percent"]):
        try:
            proc.cpu_percent(interval=None)
            processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if interval > 0:
        time.sleep(interval)
    sampled = []
    for proc in processes:
        try:
            sampled.append(
                {
                    "pid": proc.pid,
                    "name": proc.info.get("name") or "<unknown>",
                    "cpu_percent": proc.cpu_percent(interval=None),
                    "memory_percent": proc.memory_percent(),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return sampled


def gather_processes(args: argparse.Namespace) -> SectionData:
    data: MutableMapping[str, Any] = {}
    if not psutil:
        data["status"] = "psutil missing"
        return data
    sampled = sample_processes(args.process_interval)
    proc_sorted = sorted(
        sampled,
        key=lambda proc: (proc.get("cpu_percent", 0.0), proc.get("memory_percent", 0.0)),
        reverse=True,
    )
    data["Sampling window (seconds)"] = args.process_interval
    data["Top processes"] = [
        {
            "pid": proc["pid"],
            "name": proc["name"],
            "cpu%": f"{proc['cpu_percent']:.1f}",
            "mem%": f"{proc['memory_percent']:.1f}",
        }
        for proc in proc_sorted[: args.max_processes]
    ]
    return data


def gather_python(args: argparse.Namespace) -> SectionData:
    python: MutableMapping[str, Any] = {
        "Executable": sys.executable,
        "Version": sys.version.replace("\n", " "),
        "Path": sys.path,
        "Flags": {
            flag: getattr(sys.flags, flag)
            for flag in dir(sys.flags)
            if not flag.startswith("_") and isinstance(getattr(sys.flags, flag), int)
        },
    }
    python["pip"] = safe_subprocess([sys.executable, "-m", "pip", "--version"], timeout=5)
    if args.max_packages > 0:
        packages = safe_subprocess([sys.executable, "-m", "pip", "list", "--format=json"], timeout=10)
        if packages.get("stdout"):
            try:
                python["installed_packages"] = json.loads(packages["stdout"])[: args.max_packages]
            except json.JSONDecodeError:
                python["installed_packages"] = packages["stdout"]
        elif packages.get("stderr"):
            python["installed_packages_error"] = packages["stderr"]
    return python


def is_sensitive_env_key(key: str) -> bool:
    upper_key = key.upper()
    if upper_key in SENSITIVE_ENV_EXACT_KEYS:
        return True
    return any(marker in upper_key for marker in SENSITIVE_ENV_MARKERS)


def gather_environment(args: argparse.Namespace) -> SectionData:
    safe_values = {key: os.environ.get(key) for key in SAFE_ENV_KEYS if os.environ.get(key) is not None}
    env: MutableMapping[str, Any] = {
        "Selected vars": safe_values,
        "Total vars": len(os.environ),
    }
    sensitive_keys = sorted(key for key in os.environ if is_sensitive_env_key(key))
    env["Sensitive var names"] = sensitive_keys
    if args.include_sensitive:
        env["All vars"] = dict(sorted(os.environ.items()))
    else:
        env["Redaction"] = "Use --include-sensitive to include full environment values."
    return env


def gather_users(args: argparse.Namespace) -> SectionData:
    users: MutableMapping[str, Any] = {}
    if not psutil:
        users["status"] = "psutil missing"
        return users
    sessions, error = safe_call(psutil.users)
    if error:
        users["error"] = error
        return users
    users["Active sessions"] = [
        {
            "name": session.name,
            "terminal": session.terminal,
            "host": session.host,
            "started": datetime.datetime.fromtimestamp(session.started).isoformat(),
        }
        for session in sessions
    ]
    return users


def gather_commands(args: argparse.Namespace) -> SectionData:
    data: MutableMapping[str, Any] = {}
    commands: list[tuple[str, Sequence[str]]] = [
        ("uname", ["uname", "-a"]),
        ("whoami", ["whoami"]),
    ]
    if args.include_sensitive:
        commands.append(("env", ["env"] if os.name != "nt" else ["set"]))
    else:
        data["env"] = {
            "status": "Skipped by default to avoid leaking environment values.",
            "hint": "Re-run with --include-sensitive to capture full environment output.",
        }
    for name, cmd in commands:
        data[name] = safe_subprocess(cmd, timeout=3)
    return data


def gather_virtualization(args: argparse.Namespace) -> SectionData:
    info: MutableMapping[str, Any] = {}
    markers = {
        "/.dockerenv": "Docker",
        "/.containerenv": "Container",
        "/proc/sys/fs/binfmt_misc/emuinfo": "Binary emulation",
    }
    info["Detected"] = [label for path, label in markers.items() if os.path.exists(path)] or ["none detected"]
    cmd = shutil.which("systemd-detect-virt")
    if cmd:
        info["systemd-detect-virt"] = safe_subprocess([cmd], timeout=3)
    else:
        info["systemd-detect-virt"] = {"status": "command not available"}
    return info


def capture_metrics() -> Mapping[str, float]:
    metrics: MutableMapping[str, float] = {}
    if not psutil:
        return metrics
    metrics["cpu_percent"] = psutil.cpu_percent(interval=0.1)
    vm = psutil.virtual_memory()
    metrics["memory_percent"] = vm.percent
    io, io_error = safe_call(psutil.net_io_counters, pernic=False)
    if not io_error and io:
        metrics["bytes_sent_mb"] = io.bytes_sent / (1024.0 * 1024.0)
        metrics["bytes_recv_mb"] = io.bytes_recv / (1024.0 * 1024.0)
    disk, disk_error = safe_disk_usage(os.path.abspath(os.sep))
    if not disk_error and disk:
        metrics["root_disk_percent"] = disk.percent
    return metrics


def compute_health_score(cpu: float | None, memory: float | None, disk: float | None) -> int:
    score = 100.0
    if cpu is not None:
        score -= max(cpu - 60.0, 0.0) * 0.8
    if memory is not None:
        score -= max(memory - 70.0, 0.0) * 1.0
    if disk is not None:
        score -= max(disk - 75.0, 0.0) * 1.2
    return max(0, min(100, int(round(score))))


def format_progress_bar(percent: float, width: int = 30) -> str:
    filled = int(min(max(percent, 0.0), 100.0) / 100.0 * width)
    return f"[{'#' * filled}{' ' * (width - filled)}] {percent:.1f}%"


def gather_health_insights(args: argparse.Namespace) -> SectionData:
    insights: MutableMapping[str, Any] = {}
    metrics = getattr(args, "metric_snapshot", {})
    if not metrics:
        insights["status"] = "psutil missing or metrics unavailable"
        return insights
    cpu = metrics.get("cpu_percent")
    mem = metrics.get("memory_percent")
    disk = metrics.get("root_disk_percent")
    warnings: list[str] = []
    if cpu is not None:
        insights["CPU usage"] = format_progress_bar(cpu)
        if cpu >= 85:
            warnings.append("High CPU usage")
    if mem is not None:
        insights["Memory usage"] = format_progress_bar(mem)
        if mem >= 90:
            warnings.append("High memory pressure")
    if disk is not None:
        insights["Root disk usage"] = format_progress_bar(disk)
        if disk >= 90:
            warnings.append("Root volume nearly full")
    score = compute_health_score(cpu, mem, disk)
    insights["Health score"] = f"{score}/100"
    insights["Status"] = "Attention needed" if warnings else "Operating normally"
    if warnings:
        insights["Warnings"] = warnings
    return insights


def gather_baseline_comparison(args: argparse.Namespace) -> SectionData:
    comparison: MutableMapping[str, Any] = {}
    baseline = getattr(args, "baseline_report", None)
    baseline_error = getattr(args, "baseline_error", None)
    if baseline_error:
        comparison["error"] = baseline_error
        return comparison
    if not baseline:
        comparison["status"] = "No baseline file loaded (use --baseline <path>)"
        return comparison

    metrics = getattr(args, "metric_snapshot", {})
    baseline_metrics = baseline.get("metrics", {})
    diffs: MutableMapping[str, Mapping[str, str]] = {}
    drifted: list[str] = []
    for key, current_value in metrics.items():
        baseline_value = baseline_metrics.get(key)
        if not isinstance(current_value, (int, float)) or not isinstance(baseline_value, (int, float)):
            continue
        delta = current_value - baseline_value
        diffs[key] = {
            "current": f"{current_value:.2f}",
            "baseline": f"{baseline_value:.2f}",
            "delta": f"{delta:+.2f}",
        }
        if abs(delta) >= args.baseline_threshold:
            drifted.append(key)

    comparison["Baseline generated"] = baseline.get("generated")
    comparison["Baseline file"] = getattr(args, "baseline", None)
    comparison["Threshold"] = f"{args.baseline_threshold:.2f}"
    comparison["Metric differences"] = diffs or "No comparable metrics in baseline"
    comparison["Drift detected"] = drifted or ["none"]
    return comparison


SECTION_FACTORIES: "OrderedDict[str, tuple[str, SectionFactory]]" = OrderedDict(
    [
        ("overview", ("System overview", gather_system_overview)),
        ("health", ("Health snapshot", gather_health_insights)),
        ("os", ("Operating system", gather_os_details)),
        ("cpu", ("CPU", gather_cpu)),
        ("memory", ("Memory", gather_memory)),
        ("disks", ("Disks", gather_disks)),
        ("network", ("Network", gather_network)),
        ("gpu", ("GPU", gather_gpu)),
        ("sensors", ("Sensors", gather_sensors)),
        ("processes", ("Processes", gather_processes)),
        ("python", ("Python and pip", gather_python)),
        ("environment", ("Environment", gather_environment)),
        ("users", ("Users & sessions", gather_users)),
        ("commands", ("Command outputs", gather_commands)),
        ("virtualization", ("Virtualization", gather_virtualization)),
        ("baseline", ("Baseline comparison", gather_baseline_comparison)),
    ]
)
SECTION_TITLE_LOOKUP = {title.lower(): key for key, (title, _) in SECTION_FACTORIES.items()}


def normalize_section_name(section: str) -> str:
    key = section.strip().lower()
    return SECTION_TITLE_LOOKUP.get(key, key)


def resolve_section_selection(
    requested: Iterable[str] | None,
    excluded: Iterable[str] | None,
) -> tuple[list[str], list[str]]:
    valid_keys = set(SECTION_FACTORIES)
    selected = list(SECTION_FACTORIES.keys())
    errors: list[str] = []

    if requested:
        normalized = {normalize_section_name(section) for section in requested if section.strip()}
        if normalized and "all" not in normalized:
            selected = [key for key in SECTION_FACTORIES if key in normalized]
            unknown = sorted(normalized - valid_keys)
            if unknown:
                errors.append(f"Unknown sections requested: {', '.join(unknown)}")

    if excluded:
        normalized_excluded = {normalize_section_name(section) for section in excluded if section.strip()}
        unknown = sorted(normalized_excluded - valid_keys - {"all"})
        if unknown:
            errors.append(f"Unknown sections excluded: {', '.join(unknown)}")
        if "all" in normalized_excluded:
            selected = []
        else:
            selected = [key for key in selected if key not in normalized_excluded]

    return selected, errors


def gather_section(args: argparse.Namespace, key: str, title: str, factory: SectionFactory) -> SectionData:
    started = time.perf_counter()
    try:
        result = factory(args)
    except Exception as exc:  # pragma: no cover - broad by design for resilience
        result = {
            "error": str(exc),
            "section": key,
            "status": "failed",
        }
    timings = getattr(args, "section_timings", None)
    if isinstance(timings, MutableMapping):
        timings[key] = round(time.perf_counter() - started, 4)
    return result


def build_report(args: argparse.Namespace) -> OrderedDict[str, Any]:
    report: "OrderedDict[str, Any]" = OrderedDict()
    report["generated"] = datetime.datetime.now().isoformat()
    report["sections"] = OrderedDict()
    report["metadata"] = {
        "sensitive_mode": args.include_sensitive,
        "selected_sections": [],
        "selection_errors": [],
        "section_timings_seconds": {},
        "runtime_capabilities": detect_runtime_capabilities(),
        "summary": {
            "section_count": 0,
            "selection_warning_count": 0,
            "section_failure_count": 0,
        },
    }

    selected, errors = resolve_section_selection(args.sections, args.exclude_sections)
    report["metadata"]["selected_sections"] = selected
    report["metadata"]["selection_errors"] = errors

    args.section_timings = report["metadata"]["section_timings_seconds"]
    for key in selected:
        if key == "baseline" and not getattr(args, "baseline", None):
            continue
        title, factory = SECTION_FACTORIES[key]
        report["sections"][title] = gather_section(args, key, title, factory)
    report["metadata"]["summary"] = {
        "section_count": len(report["sections"]),
        "selection_warning_count": len(errors),
        "section_failure_count": sum(
            1
            for section in report["sections"].values()
            if isinstance(section, Mapping) and section.get("status") == "failed"
        ),
    }
    report["metrics"] = getattr(args, "metric_snapshot", {})
    return report


def render_value(value: Any, indent: int = 0, indent_width: int = 2) -> list[str]:
    spacing = " " * (indent * indent_width)
    lines: list[str] = []
    if isinstance(value, Mapping):
        for key, val in value.items():
            if isinstance(val, (Mapping, list)):
                lines.append(f"{spacing}{key}:")
                lines.extend(render_value(val, indent + 1, indent_width))
            else:
                lines.append(f"{spacing}{key}: {short_repr(val)}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (Mapping, list)):
                lines.append(f"{spacing}-")
                lines.extend(render_value(item, indent + 1, indent_width))
            else:
                lines.append(f"{spacing}- {short_repr(item)}")
    else:
        lines.append(f"{spacing}{short_repr(value)}")
    return lines


def format_text_report(report: OrderedDict[str, Any], args: argparse.Namespace) -> str:
    lines = [f"Generated: {report['generated']}"]
    metadata = report.get("metadata", {})
    if metadata.get("selection_errors"):
        lines.append("")
        lines.append("Warnings")
        lines.append("========")
        lines.extend(render_value({"Selection errors": metadata["selection_errors"]}, indent=args.indent))
    for title, section in report["sections"].items():
        lines.append("")
        lines.append(title)
        lines.append("=" * len(title))
        lines.extend(render_value(section, indent=args.indent))
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable text.")
    parser.add_argument("--list-sections", action="store_true", help="List available section keys and exit.")
    parser.add_argument("--output", "-o", type=str, help="Write report to a file instead of stdout.")
    parser.add_argument(
        "--sections",
        nargs="*",
        help="Sections to include (default = all). Use section keys or report headers.",
    )
    parser.add_argument(
        "--exclude-sections",
        nargs="*",
        help="Sections to omit after inclusion is resolved.",
    )
    parser.add_argument("--max-processes", type=positive_int, default=10, help="Top N processes to list.")
    parser.add_argument("--max-packages", type=int, default=20, help="Limit installed package output.")
    parser.add_argument("--indent", type=positive_int, default=2, help="Indent width for text or JSON output.")
    parser.add_argument("--baseline", type=str, help="Compare against an existing JSON report for drift.")
    parser.add_argument("--save-baseline", type=str, help="Save this report as a reusable JSON baseline.")
    parser.add_argument(
        "--baseline-threshold",
        type=non_negative_float,
        default=10.0,
        help="Minimum absolute metric delta required before baseline drift is flagged.",
    )
    parser.add_argument(
        "--include-sensitive",
        action="store_true",
        help="Include full environment values and raw env command output.",
    )
    parser.add_argument(
        "--connection-limit",
        type=positive_int,
        default=10,
        help="Maximum number of network connections to sample.",
    )
    parser.add_argument(
        "--cpu-interval",
        type=non_negative_float,
        default=0.5,
        help="Sampling interval for aggregate CPU usage.",
    )
    parser.add_argument(
        "--process-interval",
        type=non_negative_float,
        default=0.2,
        help="Sampling window for per-process CPU usage.",
    )
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Exit non-zero when section selection warnings or section failures are present.",
    )
    return parser.parse_args(argv)


def load_baseline(path: str) -> tuple[Mapping[str, Any] | None, str | None]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return None, str(exc)
    if not isinstance(data, Mapping):
        return None, "Baseline file must contain a JSON object."
    return data, None


def detect_runtime_capabilities() -> Mapping[str, Any]:
    return {
        "psutil": psutil is not None,
        "distro": _distro is not None,
        "GPUtil": _gputil is not None,
        "commands": {
            "systemd-detect-virt": shutil.which("systemd-detect-virt") is not None,
            "lscpu": shutil.which("lscpu") is not None,
            "lspci": shutil.which("lspci") is not None,
            "glxinfo": shutil.which("glxinfo") is not None,
            "df": shutil.which("df") is not None,
        },
    }


def write_text_file(path: str, payload: str) -> str | None:
    try:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(payload)
    except OSError as exc:
        return str(exc)
    return None


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_packages < 0:
        print("--max-packages must be 0 or greater", file=sys.stderr)
        return 2
    if args.list_sections:
        for key, (title, _) in SECTION_FACTORIES.items():
            print(f"{key}\t{title}")
        return 0
    args.metric_snapshot = capture_metrics()
    args.baseline_report = None
    args.baseline_error = None
    if args.baseline:
        args.baseline_report, args.baseline_error = load_baseline(args.baseline)

    report = build_report(args)
    payload = json.dumps(report, indent=args.indent) if args.json else format_text_report(report, args)

    if args.save_baseline:
        baseline_error = write_text_file(args.save_baseline, json.dumps(report, indent=args.indent))
        if baseline_error:
            print(f"Failed to write baseline: {baseline_error}", file=sys.stderr)
            return 1

    if args.output:
        output_error = write_text_file(args.output, payload)
        if output_error:
            print(f"Failed to write output: {output_error}", file=sys.stderr)
            return 1
    else:
        print(payload)

    metadata = report.get("metadata", {})
    has_selection_warnings = bool(metadata.get("selection_errors"))
    has_section_failures = bool(metadata.get("summary", {}).get("section_failure_count"))
    if args.fail_on_warnings and (has_selection_warnings or has_section_failures):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
