from __future__ import annotations
import asyncio
from pathlib import Path
from typing import List, Tuple
from ..models import Observation, SessionConfig

REDACTIONS = [
    (r"(?i)(authorization:\s*)(\S+)", r"\1[REDACTED]"),
    (r"(?i)(password=)(\S+)", r"\1[REDACTED]"),
    (r"(?i)(aws_secret_access_key=)(\S+)", r"\1[REDACTED]"),
    (r"([A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+)", r"[JWT_REDACTED]"),
]

def _redact(text: str) -> str:
    import re
    for pat, repl in REDACTIONS:
        text = re.sub(pat, repl, text)
    return text

async def run_command(cfg: SessionConfig, block_id: str, idx: int, cmd: str, timeout: int = 20) -> Tuple[int, str, str, Path, Path]:
    # Use shell=False whenever possible. For MVP, we split simple commands.
    import shlex
    parts = shlex.split(cmd)
    # Ensure commands run inside the session output directory (safe workspace)
    cwd = str(cfg.output_dir)
    proc = await asyncio.create_subprocess_exec(
        *parts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "", "Timeout", Path(), Path()

    stdout = out.decode("utf-8", errors="ignore")
    stderr = err.decode("utf-8", errors="ignore")

    stdout = _redact(stdout)
    stderr = _redact(stderr)

    logs_dir = cfg.output_dir / "logs"
    o = logs_dir / f"{block_id}_{idx}.out"
    e = logs_dir / f"{block_id}_{idx}.err"
    o.write_text(stdout)
    e.write_text(stderr)
    return proc.returncode, stdout, stderr, o, e

def make_observation(block_id: str, all_results: List[Tuple[int,str,str,Path,Path]]) -> Observation:
    exit_code = max((rc for rc, *_ in all_results), default=0)
    combined = "".join((s for _, s, *_ in all_results))
    key_lines = (combined.splitlines()[:20] + ["..."] + combined.splitlines()[-10:]) if combined else []
    bytes_out = sum((len(s.encode()) for _, s, *_ in all_results))
    log_paths = []
    for _, _, _, o, e in all_results:
        if o:
            log_paths.append(str(o))
        if e:
            log_paths.append(str(e))
    summary = f"{len(all_results)} command(s), exit={exit_code}, bytes={bytes_out}"
    return Observation(block_id=block_id, exit_code=exit_code, key_lines=key_lines, bytes_out=bytes_out, summary=summary, log_paths=log_paths)
