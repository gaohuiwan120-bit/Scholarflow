"""Static policy checks before execution (defense in depth, not a full sandbox)."""

from __future__ import annotations

import ast
import re

_ALWAYS_DENIED = {
    "subprocess",
    "multiprocessing",
    "ctypes",
    "cffi",
    "pty",
    "fcntl",
    "signal",
}

_NETWORK_MODULES = {
    "socket",
    "ssl",
    "http",
    "urllib",
    "urllib3",
    "requests",
    "aiohttp",
    "ftplib",
    "telnetlib",
    "httpx",
}

_DENIED_CALLS = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "breakpoint",
    "input",
    "exit",
    "quit",
}

_PATH_ESCAPE = re.compile(
    r"(?:\.\./|\.\.\\|/etc/|/proc/|/sys/|C:\\\\Windows|C:/Windows|"
    r"%USERPROFILE%|%SystemRoot%)",
    re.IGNORECASE,
)


def _root_module(name: str | None) -> str:
    return (name or "").split(".")[0]


def validate_python_source(code: str, *, allow_network: bool) -> list[str]:
    """Return list of rejection reasons (empty = ok)."""
    reasons: list[str] = []
    if "\x00" in code:
        reasons.append("null_byte_in_source")
    if _PATH_ESCAPE.search(code):
        reasons.append("suspicious_path_literal")

    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"syntax_error: {exc}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = _root_module(alias.name)
                if root in _ALWAYS_DENIED:
                    reasons.append(f"denied_import:{alias.name}")
                elif root in _NETWORK_MODULES and not allow_network:
                    reasons.append(f"network_import_denied:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = _root_module(node.module)
            if root in _ALWAYS_DENIED:
                reasons.append(f"denied_import_from:{node.module}")
            elif root in _NETWORK_MODULES and not allow_network:
                reasons.append(f"network_import_denied:{node.module}")
        elif isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in _DENIED_CALLS:
                reasons.append(f"denied_call:{name}")
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                if func.value.id == "os" and func.attr in {
                    "system",
                    "popen",
                    "execl",
                    "execv",
                    "spawnl",
                    "spawnv",
                }:
                    reasons.append(f"denied_os_call:{func.attr}")

    seen: set[str] = set()
    out: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out
