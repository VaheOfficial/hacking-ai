from __future__ import annotations
import json
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Dict, List, Optional

import keyring
from openai import OpenAI
from pydantic import BaseModel, Field

from ..models import CommandBlock, SessionConfig
from .session import SessionManager


SERVICE_NAME = "wsra-openai"
API_USERNAME = "default"


class AIMessage(BaseModel):
    role: str
    content: str
    meta: Dict = Field(default_factory=dict)


@dataclass
class MemoryPaths:
    root: Path
    messages: Path

    @staticmethod
    def for_session(ses: SessionManager) -> "MemoryPaths":
        mem = ses.root / "memory"
        mem.mkdir(parents=True, exist_ok=True)
        return MemoryPaths(root=mem, messages=mem / "messages.jsonl")


class SecureKeys:
    VAULT_DIR = Path.home() / ".wsra"
    VAULT_FILE = VAULT_DIR / "keys.json"

    @classmethod
    def _read_vault(cls) -> Dict:
        try:
            if cls.VAULT_FILE.exists():
                return json.loads(cls.VAULT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    @classmethod
    def _write_vault(cls, data: Dict) -> None:
        try:
            cls.VAULT_DIR.mkdir(parents=True, exist_ok=True)
            cls.VAULT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
            try:
                os.chmod(cls.VAULT_DIR, 0o700)
                os.chmod(cls.VAULT_FILE, 0o600)
            except Exception:
                pass
        except Exception as e:
            raise SystemExit(f"Failed to write local key vault: {e}")

    @classmethod
    def set_openai_key(cls, key: str) -> str:
        # Try system keyring first
        try:
            keyring.set_password(SERVICE_NAME, API_USERNAME, key)
            return "keyring"
        except Exception:
            # Fallback to local file vault
            data = cls._read_vault()
            data.setdefault("openai", {})[API_USERNAME] = key
            cls._write_vault(data)
            return "file"

    @classmethod
    def get_openai_key(cls) -> Optional[str]:
        # 1) Environment variable takes precedence in headless/CI
        env = os.getenv("OPENAI_API_KEY")
        if env:
            return env
        # 2) System keyring
        try:
            val = keyring.get_password(SERVICE_NAME, API_USERNAME)
            if val:
                return val
        except Exception:
            pass
        # 3) Local file vault
        data = cls._read_vault()
        return data.get("openai", {}).get(API_USERNAME)


class AIClient:
    def __init__(self, api_key: str, model: str = "gpt-5" ):
        # Placeholder: use the latest lightweight thinking-capable model available to you
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def chat(self, messages: List[Dict]) -> str:
        # messages: list of {role, content}
        resp = self.client.chat.completions.create(model=self.model, messages=messages, temperature=1)
        return resp.choices[0].message.content or ""


class MemoryStore:
    def __init__(self, paths: MemoryPaths):
        self.paths = paths
        if not self.paths.messages.exists():
            self.paths.messages.touch()

    def append(self, msg: AIMessage) -> None:
        rec = msg.model_dump()
        with self.paths.messages.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")

    def load(self, last_n: Optional[int] = None) -> List[AIMessage]:
        out: List[AIMessage] = []
        if not self.paths.messages.exists():
            return out
        with self.paths.messages.open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    data = json.loads(line)
                    out.append(AIMessage(**data))
                except Exception:
                    continue
        return out[-last_n:] if last_n else out


def build_system_prompt(ses: SessionManager) -> str:
    return (
        "You are WSRA AI, a safe-by-design security research copilot. "
        "Follow Rules of Engagement and scope. Propose read-only commands first.\n"
        "Output format: return ONLY a JSON array of command blocks (no markdown fences, no prose).\n"
        "Each block must include keys: id, intent, scope_check, commands (array of strings), expected_observation, risk.\n"
        "Example: [ {\"id\":\"1\",\"intent\":\"...\",\"scope_check\":\"...\",\"commands\":[\"cmd\"],\"expected_observation\":\"...\",\"risk\":\"low\"} ].\n"
        "Await human approval before execution. Iterate until the objective is met."
    )


def _extract_blocks_json(text: str) -> List[Dict]:
    # 1) Try direct parse
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "blocks" in data:
            data = data["blocks"]
        if isinstance(data, list):
            return data
    except Exception:
        pass
    # 2) Try fenced ```json blocks
    import re
    fence = re.search(r"```json\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        try:
            data = json.loads(fence.group(1))
            if isinstance(data, dict) and "blocks" in data:
                data = data["blocks"]
            if isinstance(data, list):
                return data
        except Exception:
            pass
    # 3) Try to locate first JSON array substring
    start = text.find("[")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            ch = text[i]
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i+1]
                    try:
                        data = json.loads(candidate)
                        if isinstance(data, list):
                            return data
                    except Exception:
                        break
    return []


def _normalize_block_dict(b: Dict, idx: int) -> Dict:
    out: Dict = {}
    out["id"] = b.get("id") or f"AI-{idx:03d}"
    out["intent"] = b.get("intent") or ""
    out["scope_check"] = b.get("scope_check") or ""
    cmds = b.get("commands") or []
    if isinstance(cmds, str):
        cmds = [cmds]
    out["commands"] = [str(c) for c in cmds]
    out["expected_observation"] = b.get("expected_observation") or ""
    risk = (b.get("risk") or "low").strip().lower()
    # Normalize variants like "low:", "Low", "Low: ..."
    if risk.startswith("low"):
        risk = "low"
    elif risk.startswith("med"):
        risk = "medium"
    out["risk"] = risk
    out["preconditions"] = b.get("preconditions") or []
    out["rollback"] = b.get("rollback") or "None (read-only)"
    return out


def _vector_context_snippets(ses: SessionManager, query: str, k: int = 4) -> str:
    try:
        # Lazy import to avoid heavy deps on non-AI paths
        from ..vector.store import VectorStore  # type: ignore
        vs = VectorStore.for_session(ses)
        hits = vs.search(query, top_k=k)
        if not hits:
            return ""
        parts = []
        for h in hits:
            parts.append(f"Source: {h['source']}\n{h['text'][:500]}")
        return "\n\n".join(parts)
    except Exception:
        return ""


def propose_blocks_from_ai(ai: AIClient, mem: MemoryStore, ses: SessionManager, user_goal: str) -> List[CommandBlock]:
    messages = [{"role": "system", "content": build_system_prompt(ses)}]
    # Load some recent memory for context
    recent = mem.load(last_n=50)
    for m in recent:
        messages.append({"role": m.role, "content": m.content})
    ctx = _vector_context_snippets(ses, query=user_goal, k=4)
    if ctx:
        messages.append({"role": "system", "content": f"Relevant context from prior artifacts:\n\n{ctx}"})
    messages.append({"role": "user", "content": f"Objective: {user_goal}. Please propose the next safe step as a JSON array of blocks."})
    text = ai.chat(messages)
    mem.append(AIMessage(role="assistant", content=text))
    # Extract JSON array from response
    blocks: List[CommandBlock] = []
    data = _extract_blocks_json(text)
    if not data:
        # One retry with explicit correction
        retry = ai.chat([
            {"role": "system", "content": build_system_prompt(ses)},
            {"role": "user", "content": "Your previous reply was not valid JSON. Return ONLY a JSON array of blocks as specified."}
        ])
        mem.append(AIMessage(role="assistant", content=retry))
        data = _extract_blocks_json(retry)
    if not data:
        # Fallback: search latest assistant message in memory for a valid blocks array
        hist = mem.load(last_n=500)
        for m in reversed(hist):
            if m.role != "assistant":
                continue
            prev = _extract_blocks_json(m.content)
            if prev:
                data = prev
                break
    for idx, b in enumerate(data or [], start=1):
        try:
            clean = _normalize_block_dict(b, idx)
            blocks.append(CommandBlock(**clean))
        except Exception:
            continue
    return blocks


