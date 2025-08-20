from __future__ import annotations
import shlex
from typing import Literal, Tuple
from ..models import Mode, SessionConfig

LOW_READONLY_BINARIES = {
    "echo","cat","head","tail","ls","stat","file","strings","sha256sum",
    "curl","wget","dig","nslookup","whois","openssl"
}

DENY_PATTERNS = [
    "rm -rf", "mkfs", "dd of=/dev", "reboot", "shutdown",
    "nc -e", "bash -i >&", "chmod -R 777 /",
]

def classify_and_check(cmd: str) -> Tuple[Literal["low","medium"], bool, str]:
    txt = cmd.strip().lower()
    for pat in DENY_PATTERNS:
        if pat in txt:
            return "medium", False, f"Denied pattern: {pat}"

    # Parse head token
    try:
        parts = shlex.split(cmd)
        head = parts[0] if parts else ""
    except Exception:
        head = cmd.split()[0] if cmd.split() else ""

    if head in {"curl"}:
        # allow only HEAD/metadata
        if " -I" in cmd or " --head" in cmd:
            return "low", True, "curl with --head/-I (metadata only)"
        return "medium", False, "curl without --head/-I is not read-only safe by default"

    if head in {"wget"}:
        if " --spider" in cmd:
            return "low", True, "wget --spider (metadata only)"
        return "medium", False, "wget without --spider is not read-only safe by default"

    if head in LOW_READONLY_BINARIES:
        return "low", True, f"{head} considered read-only (MVP allowlist)"

    # Everything else is at least medium and needs approval
    return "medium", False, f"{head or 'command'} requires approval"

def enforce(cfg: SessionConfig, cmd: str) -> Tuple[bool, bool, str]:
    """
    Returns (allow_execute, needs_approval, reason)
    """
    risk, readonly_ok, why = classify_and_check(cmd)
    from .scope import in_scope_command
    scope_ok, scope_reason = in_scope_command(cfg, cmd)

    if not scope_ok:
        return False, True, f"Out of scope: {scope_reason}"

    if cfg.mode in ("PLAN_ONLY", "SIMULATE"):
        return False, True, f"Mode={cfg.mode} forbids execution"

    if cfg.mode == "AUTO_READONLY":
        if risk == "low" and readonly_ok:
            return True, False, f"Allowed in AUTO_READONLY: {why}"
        return False, True, f"Needs approval in AUTO_READONLY: {why}"

    if cfg.mode == "EXECUTE_WITH_APPROVAL":
        # Require approval in the UI flow; function returns 'needs_approval' so the caller can prompt
        return False, True, f"Approval required: {why}"

    return False, True, "Unknown mode"
