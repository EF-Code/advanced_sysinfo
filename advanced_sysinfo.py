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
