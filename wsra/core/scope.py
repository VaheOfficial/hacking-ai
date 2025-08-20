from __future__ import annotations
import re
from pathlib import Path
from typing import Tuple
import shlex
from ..models import SessionConfig

IP_RE = re.compile(r"\b(?:(?:\d{1,3}\.){3}\d{1,3})\b")
HOST_RE = re.compile(r"\b([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b")
URL_RE = re.compile(r"https?://([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})")

def _extract_targets(cmd: str) -> set[str]:
    targets: set[str] = set()
    for pat in (URL_RE, HOST_RE, IP_RE):
        for m in pat.findall(cmd):
            targets.add(m if isinstance(m, str) else m[0])
    return targets

def _extract_paths(cmd: str) -> set[str]:
    # Absolute paths only: tokens that start with '/'
    try:
        tokens = shlex.split(cmd)
    except Exception:
        tokens = cmd.split()
    return {tok for tok in tokens if tok.startswith("/")}

def in_scope_command(cfg: SessionConfig, cmd: str) -> Tuple[bool, str]:
    targets = _extract_targets(cmd)
    if targets:
        # At least one of the targets must be in allowed domains/hosts
        allowed = set(cfg.scope.domains + cfg.scope.hosts)
        disallowed = set(cfg.scope.out_of_scope)
        if any(t in disallowed for t in targets):
            return False, f"Target {targets & disallowed} is explicitly out-of-scope."
        if not any(any(allow == t or t.endswith("." + allow) for allow in cfg.scope.domains) or
                   t in cfg.scope.hosts for t in targets):
            return False, f"No referenced target {targets} is in allowed domains/hosts."
    # Local paths: only allow absolute paths under whitelisted roots (relative paths OK)
    abs_paths = _extract_paths(cmd)
    if abs_paths:
        allowed_roots = [Path(p).resolve() for p in cfg.scope.paths]
        for ap in abs_paths:
            rp = Path(ap).resolve()
            if not any(str(rp).startswith(str(root)) for root in allowed_roots):
                return False, f"Absolute path {ap} not under allowed roots {cfg.scope.paths}"
    return True, "In scope"
