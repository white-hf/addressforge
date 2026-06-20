"""
AddressForge Vector Retrieval Engine (Phase 12)
==============================================
Semantic retrieval bedrock for resolving geospatial entities using Embeddings and FAISS.
"""

from __future__ import annotations

import os
import json
import numpy as np
from pathlib import Path
from typing import Any, Dict, List

from addressforge.core.utils import logger

class VectorRetrievalEngine:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", index_dir: str = "runtime/vector_index"):
        self.model_name = model_name
        self.index_dir = Path(index_dir)
        self.model = None
        self.index = None
        self.metadata = []
        self._initialized = False

    def _initialize(self):
        if self._initialized:
            return
            
        try:
            from sentence_transformers import SentenceTransformer
            import faiss
            
            logger.info(f"Loading embedding model: {self.model_name}")
            # Ensure model doesn't download on every worker reload, using local cache if available
            self.model = SentenceTransformer(self.model_name)
            
            index_path = self.index_dir / "geonova.index"
            meta_path = self.index_dir / "geonova_meta.json"
            
            if index_path.exists() and meta_path.exists():
                logger.info(f"Loading FAISS index from {index_path}")
                self.index = faiss.read_index(str(index_path))
                with open(meta_path, 'r', encoding='utf-8') as f:
                    self.metadata = json.load(f)
                logger.info(f"Loaded {len(self.metadata)} reference vectors.")
            else:
                logger.warning("No pre-built FAISS index found. Vector retrieval will be disabled.")
                
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize Vector Retrieval Engine: {e}")

    def reload_models(self) -> None:
        """
        Hot-reloads the FAISS index from disk.
        从磁盘热重载 FAISS 索引。
        """
        logger.info("Hot-reloading FAISS index...")
        self._initialized = False
        self._initialize()

    def build_index(self, records: List[Dict[str, Any]]):
        """
        Builds the FAISS index from a list of reference records.
        """
        try:
            from sentence_transformers import SentenceTransformer
            import faiss
            
            if not self.model:
                self.model = SentenceTransformer(self.model_name)
                
            logger.info(f"Building vector index for {len(records)} records...")
            
            # Extract texts for embedding
            # Format: "Street Number Street Name, City"
            texts = []
            for r in records:
                sn = r.get("street_number", "")
                st = r.get("street_name", "")
                city = r.get("city", "") or r.get("municipality", "") or ""
                text = f"{sn} {st}, {city}".strip()
                texts.append(text)
                
            # Compute embeddings
            logger.info("Computing embeddings...")
            embeddings = self.model.encode(texts, batch_size=256, show_progress_bar=True, normalize_embeddings=True)
            embeddings = np.array(embeddings).astype('float32')
            
            # Build FAISS Index (L2 distance on normalized vectors = Cosine Similarity)
            dimension = embeddings.shape[1]
            self.index = faiss.IndexFlatIP(dimension) # Inner Product for normalized vectors
            self.index.add(embeddings)
            
            self.metadata = records
            
            # Handle Decimal objects from DB when saving to JSON
            # 在保存为 JSON 时处理来自数据库的 Decimal 对象
            class DecimalEncoder(json.JSONEncoder):
                def default(self, obj):
                    from decimal import Decimal
                    if isinstance(obj, Decimal):
                        return float(obj)
                    return super(DecimalEncoder, self).default(obj)
            
            # Save index
            self.index_dir.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self.index, str(self.index_dir / "geonova.index"))
            with open(self.index_dir / "geonova_meta.json", 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, cls=DecimalEncoder)
                
            logger.info(f"Index successfully built and saved to {self.index_dir}")
            self._initialized = True
            
        except Exception as e:
            logger.error(f"Failed to build vector index: {e}")

    def retrieve(
        self,
        query_text: str,
        top_k: int = 5,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves the top-k most semantically similar reference records,
        optionally filtering or sorting based on physical GPS distance.
        """
        if not self._initialized:
            self._initialize()
            
        if not self.index or not self.model:
            return []
            
        try:
            # Encode query
            query_emb = self.model.encode([query_text], normalize_embeddings=True)
            query_emb = np.array(query_emb).astype('float32')
            
            # Safely parse query coordinates
            try:
                q_lat = float(latitude) if latitude is not None else None
                q_lon = float(longitude) if longitude is not None else None
            except (ValueError, TypeError):
                q_lat, q_lon = None, None
                
            has_query_gps = (q_lat is not None and q_lon is not None)
            
            # Determine search size
            search_k = top_k
            if has_query_gps:
                search_k = max(top_k * 5, 30)
                
            if self.index:
                search_k = min(search_k, self.index.ntotal)
                
            if search_k <= 0:
                return []
                
            # Search index
            distances, indices = self.index.search(query_emb, search_k)
            
            # Local imports to prevent circular references
            from addressforge.core.common import haversine_meters
            from addressforge.core.config import ADDRESSFORGE_GPS_CONFLICT_METERS
            
            max_dist = ADDRESSFORGE_GPS_CONFLICT_METERS
            
            raw_candidates = []
            for i in range(search_k):
                idx = indices[0][i]
                if idx != -1 and idx < len(self.metadata):
                    score = float(distances[0][i])
                    record = dict(self.metadata[idx])
                    record["vector_score"] = score
                    
                    if has_query_gps:
                        cand_lat = record.get("reference_lat")
                        cand_lon = record.get("reference_lon")
                        try:
                            c_lat = float(cand_lat) if cand_lat is not None else None
                            c_lon = float(cand_lon) if cand_lon is not None else None
                        except (ValueError, TypeError):
                            c_lat, c_lon = None, None
                            
                        if c_lat is not None and c_lon is not None:
                            dist = haversine_meters(q_lat, q_lon, c_lat, c_lon)
                            record["distance_meters"] = dist
                            if dist <= max_dist:
                                record["gps_conflict"] = False
                            else:
                                record["gps_conflict"] = True
                        else:
                            record["distance_meters"] = None
                            record["gps_conflict"] = False
                    else:
                        record["distance_meters"] = None
                        record["gps_conflict"] = False
                        
                    raw_candidates.append(record)
                    
            if has_query_gps:
                within_range = [
                    r for r in raw_candidates
                    if r.get("distance_meters") is not None and r["distance_meters"] <= max_dist
                ]
                if within_range:
                    within_range.sort(key=lambda r: r["vector_score"], reverse=True)
                    return within_range[:top_k]
                else:
                    # Fallback to returning raw semantic top-k candidates, flagged with distance and gps_conflict=True
                    raw_candidates.sort(key=lambda r: r["vector_score"], reverse=True)
                    return raw_candidates[:top_k]
            else:
                raw_candidates.sort(key=lambda r: r["vector_score"], reverse=True)
                return raw_candidates[:top_k]
                
        except Exception as e:
            logger.error(f"Vector retrieval failed for query '{query_text}': {e}")
            return []

_engine = None

def get_vector_engine() -> VectorRetrievalEngine:
    global _engine
    if _engine is None:
        _engine = VectorRetrievalEngine()
    return _engine
