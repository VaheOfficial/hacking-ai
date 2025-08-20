from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional, Tuple, List, Dict
from pydantic import BaseModel, Field

Mode = Literal["PLAN_ONLY", "EXECUTE_WITH_APPROVAL", "AUTO_READONLY", "SIMULATE"]

class Scope(BaseModel):
    cidrs: List[str] = []     # (MVP: not enforced yet)
    domains: List[str] = []   # example.com, sub.example.com
    hosts: List[str] = []     # IPs or hostnames
    paths: List[str] = ["."]
    out_of_scope: List[str] = []

class ROE(BaseModel):
    rate_limit_per_sec: Optional[int] = None
    time_window: Optional[Tuple[str, str]] = None  # ISO strings (MVP: informational)
    no_touch: List[str] = []
    notes: Optional[str] = None

class SessionConfig(BaseModel):
    authorization_doc: str
    scope: Scope
    roe: ROE
    mode: Mode = "AUTO_READONLY"
    output_dir: Path
    kill_switch: str = "ABORT WSRA NOW"

class Task(BaseModel):
    id: str
    title: str
    detail: str = ""
    target: Optional[str] = None
    deps: List[str] = []
    status: Literal["todo", "doing", "blocked", "done", "deferred"] = "todo"
    owner: Literal["WSRA", "user"] = "WSRA"
    created_ts: datetime = Field(default_factory=datetime.utcnow)
    updated_ts: datetime = Field(default_factory=datetime.utcnow)
    evidence: List[str] = []
    notes: Optional[str] = None

class CommandBlock(BaseModel):
    id: str
    intent: str
    scope_check: str
    preconditions: List[str] = []
    commands: List[str]
    expected_observation: str
    risk: Literal["low", "medium"] = "low"
    rollback: str = "None (read-only)"
    created_ts: datetime = Field(default_factory=datetime.utcnow)

class Observation(BaseModel):
    ts: datetime = Field(default_factory=datetime.utcnow)
    block_id: str
    exit_code: int
    key_lines: List[str]
    bytes_out: int
    summary: str
    log_paths: List[str]

class Finding(BaseModel):
    id: str
    title: str
    asset: str
    category: str = "exposure"
    severity: Literal["info", "low", "medium", "high", "critical"] = "info"
    justification: str = ""
    evidence: List[Dict] = []
    reproduction: str = "Non-destructive steps only"
    remediation: str = ""
    status: Literal["open", "verified", "mitigated", "accepted", "deferred"] = "open"
    references: List[str] = []

class AuditEvent(BaseModel):
    ts: datetime = Field(default_factory=datetime.utcnow)
    type: Literal["plan","proposal","exec","observation","finding","task","note","error"]
    block_id: Optional[str] = None
    scope_ok: bool = True
    cmd: Optional[str] = None
    exit_code: Optional[int] = None
    bytes_out: Optional[int] = None
    summary: str = ""
