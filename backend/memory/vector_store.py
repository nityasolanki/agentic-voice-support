"""
Qdrant vector store — knowledge base RAG + session memory.
Uses Ollama embeddings via LangChain.
"""
from __future__ import annotations
import uuid
from typing import Any
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter,
    FieldCondition, MatchValue
)
from langchain_ollama import OllamaEmbeddings

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from config.settings import get_settings

settings = get_settings()

EMBEDDING_DIM = 768  # nomic-embed-text default; adjust per model
KB_COLLECTION = settings.qdrant_collection
MEMORY_COLLECTION = "session_memory"


class VectorStore:
    def __init__(self):
        self.client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
        self.embeddings = OllamaEmbeddings(
            base_url=settings.ollama_base_url,
            model="nomic-embed-text",
        )
        self._ensure_collections()

    def _ensure_collections(self):
        existing = {c.name for c in self.client.get_collections().collections}
        for name in [KB_COLLECTION, MEMORY_COLLECTION]:
            if name not in existing:
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
                )

    # ── Knowledge Base ───────────────────────────────────────
    def seed_knowledge_base(self, documents: list[dict[str, str]]):
        """Load FAQ / policy documents into Qdrant."""
        points = []
        for doc in documents:
            vector = self.embeddings.embed_query(doc["content"])
            points.append(PointStruct(
                id=str(uuid.uuid4()),
                vector=vector,
                payload={"title": doc["title"], "content": doc["content"]},
            ))
        self.client.upsert(collection_name=KB_COLLECTION, points=points)

    def search_knowledge_base(self, query: str, top_k: int = 3) -> list[dict]:
        """Semantic search over knowledge base."""
        vector = self.embeddings.embed_query(query)
        results = self.client.search(
            collection_name=KB_COLLECTION,
            query_vector=vector,
            limit=top_k,
        )
        return [
            {"title": r.payload["title"], "content": r.payload["content"], "score": r.score}
            for r in results
        ]

    # ── Session Memory ────────────────────────────────────────
    def save_interaction(self, session_id: str, role: str, content: str, metadata: dict | None = None):
        """Persist a conversation turn to Qdrant for semantic recall."""
        vector = self.embeddings.embed_query(content)
        payload: dict[str, Any] = {
            "session_id": session_id,
            "role": role,
            "content": content,
        }
        if metadata:
            payload.update(metadata)
        self.client.upsert(
            collection_name=MEMORY_COLLECTION,
            points=[PointStruct(id=str(uuid.uuid4()), vector=vector, payload=payload)],
        )

    def recall_session(self, session_id: str, query: str, top_k: int = 5) -> list[dict]:
        """Retrieve the most relevant past turns for a session."""
        vector = self.embeddings.embed_query(query)
        results = self.client.search(
            collection_name=MEMORY_COLLECTION,
            query_vector=vector,
            query_filter=Filter(
                must=[FieldCondition(key="session_id", match=MatchValue(value=session_id))]
            ),
            limit=top_k,
        )
        return [
            {"role": r.payload["role"], "content": r.payload["content"], "score": r.score}
            for r in results
        ]
