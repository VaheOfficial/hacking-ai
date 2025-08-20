from __future__ import annotations
from pathlib import Path
from typing import List, Dict
import os

import chromadb
from chromadb.config import Settings

from ..core.session import SessionManager


class VectorStore:
    def __init__(self, base_dir: Path, collection_name: str):
        self.base_dir = base_dir
        self.client = chromadb.PersistentClient(path=str(base_dir), settings=Settings(anonymized_telemetry=False))
        self.collection = self.client.get_or_create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})
        self._embedder = self._init_embedder()

    def _init_embedder(self):
        # Prefer OpenAI embeddings to avoid local torch dependency on Python 3.13/WSL
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
        # Fallback to local model
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model

    @classmethod
    def for_session(cls, ses: SessionManager) -> "VectorStore":
        vs_dir = ses.root / "vector"
        vs_dir.mkdir(parents=True, exist_ok=True)
        return cls(vs_dir, collection_name=f"session-{ses.root.name}")

    def _gather_session_texts(self) -> List[Dict[str, str]]:
        texts: List[Dict[str, str]] = []
        for rel in ["logs", "evidence", "scans", "journal.md", "assessment_log.jsonl", "findings.jsonl", "tasks.jsonl", "memory/messages.jsonl"]:
            p = self.base_dir.parent / rel
            if p.is_file():
                try:
                    texts.append({"id": f"file::{p.name}", "text": p.read_text(encoding="utf-8", errors="ignore"), "source": str(p)})
                except Exception:
                    continue
            elif p.is_dir():
                for sub in p.rglob("*"):
                    if sub.is_file() and sub.stat().st_size < 5_000_000:
                        try:
                            texts.append({"id": f"file::{sub.relative_to(self.base_dir.parent)}", "text": sub.read_text(encoding="utf-8", errors="ignore"), "source": str(sub)})
                        except Exception:
                            continue
        return texts

    def index_session_artifacts(self) -> int:
        docs = self._gather_session_texts()
        if not docs:
            return 0
        ids = [d["id"] for d in docs]
        metadatas = [{"source": d["source"]} for d in docs]
        texts = [d["text"] for d in docs]
        # Compute embeddings using chosen backend
        try:
            # OpenAIEmbeddingFunction supports batch via __call__
            embeddings = self._embedder(texts)  # type: ignore
        except TypeError:
            # SentenceTransformer path
            embeddings = self._embedder.encode(texts, normalize_embeddings=True).tolist()  # type: ignore
        # Upsert in chunks to avoid large payloads
        B = 64
        for i in range(0, len(docs), B):
            sl = slice(i, i+B)
            self.collection.upsert(ids=ids[sl], embeddings=embeddings[sl], metadatas=metadatas[sl], documents=texts[sl])
        return len(docs)

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        try:
            q_emb = self._embedder([query])[0]  # type: ignore
        except TypeError:
            q_emb = self._embedder.encode([query], normalize_embeddings=True).tolist()[0]  # type: ignore
        res = self.collection.query(query_embeddings=[q_emb], n_results=top_k, include=["documents", "metadatas", "distances"])
        out: List[Dict] = []
        for idx in range(len(res["ids"][0])):
            out.append({
                "score": 1 - res["distances"][0][idx],
                "text": res["documents"][0][idx],
                "source": res["metadatas"][0][idx].get("source", "unknown"),
            })
        return out


