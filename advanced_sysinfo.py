#!/usr/bin/env python3
"""Advanced cross-platform system information detector with verbose output."""

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
from collections import OrderedDict
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

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


def bytes2human(value: int, suffix: str = "B") -> str:
    if value is None:
        return "n/a"
    units = ["", "K", "M", "G", "T", "P", "E"]
    abs_value = abs(value)
    for unit in units:
        if abs_value < 1024.0:
            return f"{value:.2f}{unit}{suffix}"
        value /= 1024.0
        abs_value = abs(value)
    return f"{value:.2f}{units[-1]}{suffix}"


def safe_subprocess(cmd: Sequence[str], timeout: float = 5.0) -> Mapping[str, Any]:
    """Run a command safely; return stdout/stderr even if it fails."""

    result: MutableMapping[str, Any] = {"command": " ".join(cmd), "stdout": "", "stderr": "", "returncode": None}
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        result["stdout"] = completed.stdout.strip()
        result["stderr"] = completed.stderr.strip()
        result["returncode"] = completed.returncode
    except (subprocess.SubprocessError, OSError) as exc:  
        result["stderr"] = str(exc)
    return result


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
                value = raw_value.strip().strip('"')
                info[key] = value
    except OSError:  # pragma: no cover
        pass
    return info


def gather_system_overview(args: argparse.Namespace) -> Mapping[str, Any]:
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
    }
    tz = datetime.datetime.now(datetime.timezone.utc).astimezone().tzname() or "unknown"
    overview["Local timezone"] = tz
    if psutil:
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time(), datetime.timezone.utc).astimezone()
        overview["Boot time"] = boot_time.isoformat()
        uptime = datetime.datetime.now(datetime.timezone.utc).astimezone() - boot_time
        overview["Uptime"] = str(uptime).split(".")[0]
    else:
        overview["Boot time"] = "psutil missing"
    return overview


def gather_os_details(args: argparse.Namespace) -> Mapping[str, Any]:
    info: MutableMapping[str, Any] = {}
    if _distro:
        info["Name"] = _distro.name(pretty=True) or _distro.name()
        info["Version"] = _distro.version()
        info["Codename"] = _distro.codename()
        info["Like"] = _distro.like()
    else:
        info["OS (fallback)"] = platform.system()
        info["Release (fallback)"] = platform.release()
        os_release = parse_os_release()
        if os_release:
            info["/etc/os-release"] = dict(sorted(os_release.items()))
    return info


def gather_memory(args: argparse.Namespace) -> Mapping[str, Any]:
    memory: MutableMapping[str, Any] = {}
    if psutil:
        vm = psutil.virtual_memory()
        memory["Virtual total"] = bytes2human(vm.total)
        memory["Available"] = bytes2human(vm.available)
        memory["Used"] = bytes2human(vm.used)
        memory["Usage"] = f"{vm.percent:.1f}%"
        swap = psutil.swap_memory()
        memory["Swap total"] = bytes2human(swap.total)
        memory["Swap used"] = bytes2human(swap.used)
        memory["Swap usage"] = f"{swap.percent:.1f}%"
    else:
        memory["Virtual memory"] = "psutil missing"
    return memory


def gather_cpu(args: argparse.Namespace) -> Mapping[str, Any]:
    cpu: MutableMapping[str, Any] = {}
    cpu["Physical cores"] = psutil.cpu_count(logical=False) if psutil else "psutil missing"
    cpu["Logical cores"] = psutil.cpu_count(logical=True) if psutil else "psutil missing"
    if psutil:
        freq = psutil.cpu_freq()
        if freq:
            cpu["Max frequency"] = f"{freq.max:.2f} MHz"
            cpu["Min frequency"] = f"{freq.min:.2f} MHz"
            cpu["Current frequency"] = f"{freq.current:.2f} MHz"
        cpu["Usage (per core)"] = [f"{x:.1f}%" for x in psutil.cpu_percent(percpu=True, interval=0.5)]
        cpu["Usage (total)"] = f"{psutil.cpu_percent():.1f}%"
    else:
        cpu["Usage"] = "psutil missing"
        cpu.update(gather_cpu_fallback(args))
    return cpu


def gather_cpu_fallback(args: argparse.Namespace) -> Mapping[str, Any]:
    info: MutableMapping[str, Any] = {}
    info["Logical cores (os)"] = os.cpu_count()
    info["Processor"] = platform.processor() or platform.machine()
    lscpu = shutil.which("lscpu")
    if lscpu:
        info["lscpu"] = safe_subprocess([lscpu])
    return info

def gather_disks(args: argparse.Namespace) -> Mapping[str, Any]:
    disks: MutableMapping[str, Any] = {}
    if not psutil:
        disks["Disk info"] = "psutil missing"
        return disks
    partitions = []
    for partition in psutil.disk_partitions(all=False):
        usage = psutil.disk_usage(partition.mountpoint)
        partitions.append(
            {
                "Device": partition.device,
                "Mountpoint": partition.mountpoint,
                "Type": partition.fstype,
                "Total": bytes2human(usage.total),
                "Used": bytes2human(usage.used),
                "Free": bytes2human(usage.free),
                "Percent": f"{usage.percent:.1f}%",
            }
        )
    disks["Partitions"] = partitions
    io_counters = psutil.disk_io_counters(perdisk=False)
    if io_counters:
        disks["IO"] = {
            "Read": bytes2human(io_counters.read_bytes),
            "Write": bytes2human(io_counters.write_bytes),
            "Read ops": io_counters.read_count,
            "Write ops": io_counters.write_count,
        }
    return disks


def gather_network(args: argparse.Namespace) -> Mapping[str, Any]:
    network: MutableMapping[str, Any] = {}
    if not psutil:
        network["Network info"] = "psutil missing"
        return network
    interfaces = {}
    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
    except (PermissionError, OSError) as exc:  
        network["Network error"] = str(exc)
        return network
    for name, addr_list in addrs.items():
        interface: MutableMapping[str, Any] = {}
        interface["Addresses"] = [serialize_address(addr) for addr in addr_list]
        stats_entry = stats.get(name)
        if stats_entry:
            interface["Up"] = stats_entry.isup
            interface["Speed"] = f"{stats_entry.speed}Mbps" if stats_entry.speed else "unknown"
            interface["Duplex"] = stats_entry.duplex
            interface["MTU"] = stats_entry.mtu
        interfaces[name] = interface
    network["Interfaces"] = interfaces
    try:
        connections = psutil.net_connections(kind="inet")
    except (PermissionError, OSError) as exc:
        network["Connection error"] = str(exc)
        return network
    summary = {
        "Total sockets": len(connections),
        "TCP": len([c for c in connections if c.type == socket.SOCK_STREAM]),
        "UDP": len([c for c in connections if c.type == socket.SOCK_DGRAM]),
    }
    network["Connection summary"] = summary
    network["Connection sample"] = serialize_connections(connections, limit=10)
    return network

def serialize_address(addr: psutil._common.snicaddr) -> Mapping[str, Any]: 
    data: MutableMapping[str, Any] = {"Address": addr.address}
    if addr.netmask:
        data["Netmask"] = addr.netmask
    if addr.broadcast:
        data["Broadcast"] = addr.broadcast
    if addr.ptp:
        data["PTP"] = addr.ptp
    return data


def serialize_connections(connections: Sequence[psutil._common.sconn], limit: int = 10) -> Sequence[Mapping[str, Any]]: 
    results: list[Mapping[str, Any]] = []
    for conn in connections[:limit]:
        results.append(
            {
                "fd": conn.fd,
                "family": conn.family.name if hasattr(conn.family, "name") else str(conn.family),
                "type": conn.type.name if hasattr(conn.type, "name") else str(conn.type),
                "laddr": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else None,
                "raddr": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else None,
                "status": conn.status,
                "pid": conn.pid,
            }
        )
    return results

def gather_gpu(args: argparse.Namespace) -> Mapping[str, Any]:
    info: MutableMapping[str, Any] = {}
    if _gputil:
        gpus = _gputil.getGPUs()
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
    else:
        info["GPU info"] = "GPUtil not installed"
        info["Fallback"] = gather_gpu_fallback()
    return info


def gather_gpu_fallback() -> Mapping[str, Any]:
    info: MutableMapping[str, Any] = {}
    lspci = shutil.which("lspci")
    if lspci:
        info["lspci"] = safe_subprocess([lspci, "-nnk"])
    glxinfo = shutil.which("glxinfo")
    if glxinfo:
        info["glxinfo"] = safe_subprocess([glxinfo, "-B"])
    if not info:
        info["status"] = "no fallback commands available"
    return info


def gather_sensors(args: argparse.Namespace) -> Mapping[str, Any]:
    readings: MutableMapping[str, Any] = {}
    if not psutil:
        readings["Sensors"] = "psutil missing"
        return readings
    temps = psutil.sensors_temperatures(fahrenheit=False)
    if temps:
        readings["Temperatures"] = {
            sensor: [f"{entry.current:.1f}°C" for entry in entries]
            for sensor, entries in temps.items()
        }
    fans = psutil.sensors_fans()
    if fans:
        readings["Fans"] = {
            fan: [f"{entry.current} RPM" for entry in entries]
            for fan, entries in fans.items()
        }
    return readings

def gather_processes(args: argparse.Namespace) -> Mapping[str, Any]:
    data: MutableMapping[str, Any] = {}
    if not psutil:
        data["Processes"] = "psutil missing"
        return data
    processes = [proc for proc in psutil.process_iter(attrs=["pid", "name", "cpu_percent", "memory_percent"])]
    proc_sorted = sorted(processes, key=lambda p: (p.info.get("cpu_percent", 0), p.info.get("memory_percent", 0)), reverse=True)
    data["Top processes"] = [
        {
            "pid": proc.info["pid"],
            "name": proc.info["name"],
            "cpu%": f"{proc.info.get('cpu_percent', 0):.1f}",
            "mem%": f"{proc.info.get('memory_percent', 0):.1f}",
        }
        for proc in proc_sorted[: args.max_processes]
    ]
    return data

def gather_python(args: argparse.Namespace) -> Mapping[str, Any]:
    python: MutableMapping[str, Any] = {
        "Executable": sys.executable,
        "Version": sys.version.replace("\n", " "),
        "Path": sys.path,
        "Flags": {flag: getattr(sys.flags, flag) for flag in dir(sys.flags) if not flag.startswith("_") and isinstance(getattr(sys.flags, flag), int)},
    }
    pip = safe_subprocess([sys.executable, "-m", "pip", "--version"])
    python["pip"] = pip
    if args.max_packages:
        packages = safe_subprocess([sys.executable, "-m", "pip", "list", "--format=json"], timeout=10)
        if packages.get("stdout"):
            try:
                python["installed_packages"] = json.loads(packages["stdout"])[: args.max_packages]
            except json.JSONDecodeError:
                python["installed_packages"] = packages["stdout"]
    return python


def gather_environment(args: argparse.Namespace) -> Mapping[str, Any]:
    env = {"HOME": os.environ.get("HOME"), "PATH": os.environ.get("PATH"), "SHELL": os.environ.get("SHELL")}
    env["Additional vars"] = {key: value for key, value in os.environ.items() if key not in env}
    return env

def gather_users(args: argparse.Namespace) -> Mapping[str, Any]:
    users: MutableMapping[str, Any] = {}
    if psutil:
        users["Active sessions"] = [
            {"name": u.name, "terminal": u.terminal, "host": u.host, "started": datetime.datetime.fromtimestamp(u.started).isoformat()}
            for u in psutil.users()
        ]
    else:
        users["Active sessions"] = "psutil missing"
    return users

def gather_commands(args: argparse.Namespace) -> Mapping[str, Any]:
    data: MutableMapping[str, Any] = {}
    for name, cmd in [
        ("uname", ["uname", "-a"]),
        ("whoami", ["whoami"]),
        ("env", ["env"] if os.name != "nt" else ["set"]),
    ]:
        data[name] = safe_subprocess(cmd, timeout=3)
    return data


def gather_virtualization(args: argparse.Namespace) -> Mapping[str, Any]:
    info: MutableMapping[str, Any] = {}
    markers = {
        "/.dockerenv": "Docker",
        "/.containerenv": "Container",
        "/proc/sys/fs/binfmt_misc/emuinfo": "Binary emulation",
    }
    detected: list[str] = []
    for path, label in markers.items():
        if os.path.exists(path):
            detected.append(label)
    info["Detected"] = detected or ["none detected"]
    virtualization = safe_subprocess(["systemd-detect-virt"])
    info["systemd-detect-virt"] = virtualization
    return info

SECTION_FACTORIES = OrderedDict(
    [
        ("overview", ("System overview", gather_system_overview)),
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
    ]
)


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


def short_repr(value: Any, max_width: int = 200) -> str:
    if value is None:
        return "null"
    if isinstance(value, str) and len(value) > max_width:
        return value[:max_width] + "..."
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="ignore")
    return str(value)


def build_report(args: argparse.Namespace) -> OrderedDict[str, Any]:
    report = OrderedDict()
    report["generated"] = datetime.datetime.now().isoformat()
    report["sections"] = OrderedDict()
    include_sections = {name for name in SECTION_FACTORIES}
    if args.sections:
        include_sections = {section.strip().lower() for section in args.sections}
    if args.exclude_sections:
        include_sections -= {section.strip().lower() for section in args.exclude_sections}
    for key, (title, factory) in SECTION_FACTORIES.items():
        if include_sections != {"all"} and key not in include_sections and title.lower() not in include_sections:
            continue
        report["sections"][title] = factory(args)
    return report


def format_text_report(report: OrderedDict[str, Any], args: argparse.Namespace) -> str:
    lines: list[str] = []
    lines.append(f"Generated: {report['generated']}")
    for title, section in report["sections"].items():
        lines.append("")
        lines.append(title)
        lines.append("=" * len(title))
        lines.extend(render_value(section, indent=args.indent))
    return "\n".join(lines)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human text.")
    parser.add_argument("--output", "-o", type=str, help="Write report to a file instead of stdout.")
    parser.add_argument(
        "--sections",
        nargs="*",
        help="Sections to include (default = all). Use names from the report headers or the section keys."
    )
    parser.add_argument(
        "--exclude-sections",
        nargs="*",
        help="Sections to omit even if --sections includes all."
    )
    parser.add_argument("--max-processes", type=int, default=10, help="Top N processes to list.")
    parser.add_argument("--max-packages", type=int, default=20, help="Limit for pip packages (JSON output)."
    )
    parser.add_argument("--indent", type=int, default=2, help="Indent spacing for text output.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(args)
    if args.json:
        payload = json.dumps(report, indent=args.indent)
    else:
        payload = format_text_report(report, args)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(payload)
    else:
        print(payload)


if __name__ == "__main__":
    main()
