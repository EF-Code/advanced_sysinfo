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
