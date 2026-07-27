"""Knowledge engine — ChromaDB-based pattern retrieval and storage."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from uuid import uuid4

from utils.config_models import KnowledgeConfig
from utils.logging import get_logger

logger = get_logger("knowledge.engine")


class KnowledgeEngine(ABC):
    """Abstract base class for knowledge engine."""

    @abstractmethod
    def retrieve(self, query: str, collection: str, top_k: int = 5) -> list[dict]: ...

    @abstractmethod
    def store_migration(
        self,
        project_id: str,
        job_id: str,
        artifacts: dict[str, str],
        confidence: float,
    ) -> None: ...

    @abstractmethod
    def store_correction(self, pattern: str, correction: str, context: str) -> None: ...


class ChromaKnowledgeEngine(KnowledgeEngine):
    """ChromaDB-backed knowledge engine with sentence-transformers embeddings."""

    def __init__(self, config: KnowledgeConfig) -> None:
        self.config = config
        self._client = None
        self._collections: dict[str, object] = {}
        self._embedding_fn = None

    def _ensure_initialized(self) -> None:
        if self._client is not None:
            return
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            persist_dir = Path(self.config.chroma_persist_dir)
            persist_dir.mkdir(parents=True, exist_ok=True)

            self._client = chromadb.PersistentClient(path=str(persist_dir))
            self._embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=self.config.embedding_model
            )

            for collection_name in self.config.collections:
                self._collections[collection_name] = self._client.get_or_create_collection(
                    name=collection_name,
                    embedding_function=self._embedding_fn,
                )
            logger.info("Knowledge engine initialized", extra={"collections": list(self._collections.keys())})
        except ImportError:
            logger.warning("ChromaDB not available, using in-memory fallback")
            self._client = "fallback"
            self._collections = {name: [] for name in self.config.collections}

    def retrieve(self, query: str, collection: str, top_k: int = 5) -> list[dict]:
        self._ensure_initialized()
        top_k = top_k or self.config.top_k

        if self._client == "fallback":
            return []

        coll = self._collections.get(collection)
        if coll is None:
            return []

        try:
            results = coll.query(query_texts=[query], n_results=top_k)
            matches = []
            if results and results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    matches.append({
                        "content": doc,
                        "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                        "distance": results["distances"][0][i] if results["distances"] else 0.0,
                    })
            return matches
        except Exception as e:
            logger.warning(f"Knowledge retrieval failed: {e}")
            return []

    def store_migration(
        self,
        project_id: str,
        job_id: str,
        artifacts: dict[str, str],
        confidence: float,
    ) -> None:
        self._ensure_initialized()
        if self._client == "fallback":
            return

        entry_id = f"ke_{uuid4().hex[:12]}"
        for collection_name in ["glue_patterns", "synapse_patterns"]:
            coll = self._collections.get(collection_name)
            if coll is None:
                continue

            content_key = "converted_code" if collection_name == "synapse_patterns" else "Understanding.md"
            content = artifacts.get(content_key, "")
            if not content:
                continue

            try:
                coll.add(
                    ids=[f"{entry_id}_{collection_name}"],
                    documents=[content[:4000]],
                    metadatas=[{
                        "project_id": project_id,
                        "job_id": job_id,
                        "confidence": confidence,
                        "source": "migration",
                    }],
                )
            except Exception as e:
                logger.warning(f"Failed to store in {collection_name}: {e}")

        logger.info("Migration stored in knowledge base", extra={"project_id": project_id, "job_id": job_id})

    def store_correction(self, pattern: str, correction: str, context: str) -> None:
        self._ensure_initialized()
        if self._client == "fallback":
            return

        coll = self._collections.get("corrections")
        if coll is None:
            return

        entry_id = f"corr_{uuid4().hex[:12]}"
        try:
            coll.add(
                ids=[entry_id],
                documents=[f"Pattern: {pattern}\nCorrection: {correction}\nContext: {context}"],
                metadatas=[{"source": "developer_correction"}],
            )
        except Exception as e:
            logger.warning(f"Failed to store correction: {e}")

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Search across all collections."""
        all_matches = []
        for collection_name in self.config.collections:
            matches = self.retrieve(query, collection_name, top_k)
            for m in matches:
                m["collection"] = collection_name
            all_matches.extend(matches)
        all_matches.sort(key=lambda x: x.get("distance", 1.0))
        return all_matches[:top_k]
