from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
from pydantic import ValidationError
from ..models import SessionConfig, Scope, ROE

SESSION_FILE = "session.json"

class SessionManager:
    def __init__(self, root: Path, config: SessionConfig):
        self.root = root
        self.config = config
        self._ensure_dirs()

    @classmethod
    def init_wizard(cls, output_dir: Optional[Path] = None) -> "SessionManager":
        root = Path(output_dir or "./wsra-session").resolve()
        root.mkdir(parents=True, exist_ok=True)

        print("\n== WSRA Initialization Wizard (MVP) ==")
        auth = input("AUTHORIZATION_DOC (short text or link): ").strip() or "AUTHORIZED TEST (demo)"
        modes = ["PLAN_ONLY","EXECUTE_WITH_APPROVAL","AUTO_READONLY","SIMULATE"]
        mode = input(f"MODE {modes} [AUTO_READONLY]: ").strip() or "AUTO_READONLY"
        kill = input('KILL_SWITCH phrase [ABORT WSRA NOW]: ').strip() or "ABORT WSRA NOW"

        domains = input("In-scope domains (comma): ").strip()
        hosts = input("In-scope hosts/IPs (comma): ").strip()
        paths = input("Allowed local paths (comma) [.] : ").strip() or "."

        scope = Scope(
            domains=[d.strip() for d in domains.split(",") if d.strip()],
            hosts=[h.strip() for h in hosts.split(",") if h.strip()],
            paths=[p.strip() for p in paths.split(",") if p.strip()],
        )
        roe = ROE()
        cfg = SessionConfig(
            authorization_doc=auth,
            scope=scope,
            roe=roe,
            mode=mode,  # type: ignore
            output_dir=root,
            kill_switch=kill
        )
        mgr = cls(root, cfg)
        mgr.save()
        print(f"\nSaved session at: {root / SESSION_FILE}\n")
        return mgr

    @classmethod
    def load_or_init(cls, output_dir: Optional[Path] = None) -> "SessionManager":
        root = Path(output_dir or "./wsra-session").resolve()
        f = root / SESSION_FILE
        if f.exists():
            with f.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            try:
                cfg = SessionConfig(**data)
            except ValidationError as e:
                raise SystemExit(f"Invalid session.json: {e}")
            return cls(root, cfg)
        return cls.init_wizard(output_dir=root)

    def save(self) -> None:
        f = self.root / SESSION_FILE
        with f.open("w", encoding="utf-8") as fh:
            json.dump(self.config.model_dump(mode="json"), fh, indent=2)

    def _ensure_dirs(self) -> None:
        (self.root / "logs").mkdir(parents=True, exist_ok=True)
        (self.root / "evidence").mkdir(parents=True, exist_ok=True)
        (self.root / "journal.md").touch(exist_ok=True)
        (self.root / "assessment_log.jsonl").touch(exist_ok=True)
        (self.root / "tasks.jsonl").touch(exist_ok=True)
        (self.root / "findings.jsonl").touch(exist_ok=True)
