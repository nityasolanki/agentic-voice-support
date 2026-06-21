"""
Qdrant vector database service for RAG and memory.
"""
from typing import Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, Filter,
    FieldCondition, MatchValue
)
from sentence_transformers import SentenceTransformer
from config.settings import get_settings
import uuid

settings = get_settings()

_client: Optional[QdrantClient] = None
_embedder: Optional[SentenceTransformer] = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    return _client


def get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(settings.embedding_model)
    return _embedder


def embed(text: str) -> list[float]:
    return get_embedder().encode(text).tolist()


async def ensure_collections():
    """Create collections if they don't exist."""
    client = get_client()
    existing = {c.name for c in client.get_collections().collections}

    for name in [settings.qdrant_collection_kb, settings.qdrant_collection_memory]:
        if name not in existing:
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=settings.embedding_dimension,
                    distance=Distance.COSINE,
                ),
            )


async def upsert_document(
    text: str,
    metadata: dict,
    collection: str = None,
    doc_id: Optional[str] = None,
):
    """Embed and upsert a document into Qdrant."""
    client = get_client()
    collection = collection or settings.qdrant_collection_kb
    vector = embed(text)
    point = PointStruct(
        id=doc_id or str(uuid.uuid4()),
        vector=vector,
        payload={**metadata, "text": text},
    )
    client.upsert(collection_name=collection, points=[point])


async def search(
    query: str,
    collection: str = None,
    top_k: int = 5,
    filter_key: Optional[str] = None,
    filter_value: Optional[str] = None,
) -> list[dict]:
    """Semantic search in Qdrant. Returns list of matched payload dicts."""
    client = get_client()
    collection = collection or settings.qdrant_collection_kb
    vector = embed(query)

    query_filter = None
    if filter_key and filter_value:
        query_filter = Filter(
            must=[FieldCondition(key=filter_key, match=MatchValue(value=filter_value))]
        )

    results = client.search(
        collection_name=collection,
        query_vector=vector,
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    )

    return [
        {"score": r.score, **r.payload}
        for r in results
    ]


async def store_conversation_memory(
    session_id: str,
    customer_id: str,
    role: str,
    content: str,
):
    """Store a conversation turn in vector memory."""
    await upsert_document(
        text=content,
        metadata={
            "session_id": session_id,
            "customer_id": customer_id,
            "role": role,
        },
        collection=settings.qdrant_collection_memory,
    )


async def recall_conversation(session_id: str, query: str, top_k: int = 5) -> list[dict]:
    """Retrieve relevant past turns from a session."""
    return await search(
        query=query,
        collection=settings.qdrant_collection_memory,
        top_k=top_k,
        filter_key="session_id",
        filter_value=session_id,
    )
