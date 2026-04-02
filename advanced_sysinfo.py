#!/usr/bin/env python3
"""Advanced cross-platform system information detector with verbose output."""
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
    except OSError:  
        pass
    return info
