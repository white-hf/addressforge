"""
AddressForge NER Training Engine (Phase 12)
==========================================
Foundation for training Transformer-based NER models for address parsing.
Currently supports dataset preparation for spaCy/HuggingFace formats.

地址治理 NER 训练引擎 (第 12 阶段)
==============================
用于训练基于 Transformer 的地址解析 NER 模型的基础。
目前支持 spaCy/HuggingFace 格式的数据集准备。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from addressforge.core.common import fetch_all
from addressforge.core.utils import logger

class NERDatasetGenerator:
    """
    Generates training data for NER models from Gold Labels.
    从金标生成 NER 模型训练数据。
    """
    
    def __init__(self, workspace_name: str = "default"):
        self.workspace_name = workspace_name

    def generate_spacy_format(self, output_path: Path):
        """
        Converts gold labels to spaCy JSONL format.
        将金标转换为 spaCy JSONL 格式。
        """
        query = """
            SELECT r.raw_address_text, g.label_json 
            FROM gold_label g
            JOIN raw_address_record r ON g.source_id = CAST(r.raw_id AS CHAR)
            WHERE g.workspace_name = %s AND g.review_status = 'accepted'
        """
        rows = fetch_all(query, (self.workspace_name,))
        
        count = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for row in rows:
                text = row["raw_address_text"]
                label = json.loads(row["label_json"]) if isinstance(row["label_json"], str) else row["label_json"]
                
                entities = []
                # Simple heuristic matching to find entity spans (for bootstrapping)
                # 简单的启发式匹配以查找实体跨度（用于引导）
                for field in ["street_number", "street_name", "unit_number", "city", "province", "postal_code"]:
                    val = label.get(field)
                    if val and str(val) in text:
                        start = text.find(str(val))
                        end = start + len(str(val))
                        entities.append((start, end, field.upper()))
                
                if entities:
                    f.write(json.dumps({"text": text, "entities": entities}) + "\n")
                    count += 1
                    
        logger.info("Generated %d NER samples in spaCy format at %s", count, output_path)
        return count

def prepare_ner_foundation(workspace_name: str = "default"):
    generator = NERDatasetGenerator(workspace_name)
    data_dir = Path("runtime/datasets/ner")
    data_dir.mkdir(parents=True, exist_ok=True)
    
    generator.generate_spacy_format(data_dir / "gold_ner_v1.jsonl")

if __name__ == "__main__":
    prepare_ner_foundation()
