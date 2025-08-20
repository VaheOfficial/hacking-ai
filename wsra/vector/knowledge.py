from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict
import uuid

import chromadb
from chromadb.config import Settings
import os


@dataclass
class KBConfig:
    root: Path = Path.home() / ".wsra" / "kb"
    collection: str = "wsra-knowledge"


class KnowledgeBank:
    def __init__(self, cfg: KBConfig | None = None):
        self.cfg = cfg or KBConfig()
        self.cfg.root.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(self.cfg.root), settings=Settings(anonymized_telemetry=False))
        self.collection = self.client.get_or_create_collection(name=self.cfg.collection, metadata={"hnsw:space": "cosine"})
        self._embedder = self._init_embedder()

    def _init_embedder(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            try:
                from ..core.ai import SecureKeys  # lazy import
                api_key = SecureKeys.get_openai_key() or None
            except Exception:
                api_key = None
        if api_key:
            try:
                from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction  # type: ignore
                return OpenAIEmbeddingFunction(api_key=api_key, model_name="text-embedding-3-small")
            except Exception:
                pass
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("all-MiniLM-L6-v2")

    def add_entry(self, session_root: Path, title: str, note: str) -> str:
        entry_id = str(uuid.uuid4())
        text = f"Title: {title}\nSession: {session_root.name}\n\n{note}"
        try:
            emb = self._embedder([text])[0]  # type: ignore
        except TypeError:
            emb = self._embedder.encode([text], normalize_embeddings=True).tolist()[0]  # type: ignore
        self.collection.add(ids=[entry_id], embeddings=[emb], metadatas=[{"title": title, "session": session_root.name}], documents=[text])
        # Append to a local JSONL for human-readable archive
        archive = self.cfg.root / "knowledge.jsonl"
        archive.open("a", encoding="utf-8").write(f"{{\"id\":\"{entry_id}\",\"session\":\"{session_root.name}\",\"title\":\"{title}\"}}\n")
        return entry_id

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        try:
            q_emb = self._embedder([query])[0]  # type: ignore
        except TypeError:
            q_emb = self._embedder.encode([query], normalize_embeddings=True).tolist()[0]  # type: ignore
        res = self.collection.query(query_embeddings=[q_emb], n_results=top_k, include=["documents", "metadatas", "distances"])
        rows: List[Dict] = []
        for idx in range(len(res["ids"][0])):
            md = res["metadatas"][0][idx]
            rows.append({
                "score": 1 - res["distances"][0][idx],
                "title": md.get("title", "(untitled)"),
                "session": md.get("session", "unknown"),
                "text": res["documents"][0][idx],
            })
        return rows


