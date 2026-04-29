from __future__ import annotations

import json
from typing import Any, List, Dict
from addressforge.core.common import fetch_all, db_cursor, dumps_payload, finish_run, create_run
from addressforge.core.config import ADDRESSFORGE_WORKSPACE_NAME
from addressforge.core.utils import logger
from addressforge.core.common import canonicalize_unit_number, normalize_street_name

class ParserRerankerTrainer:
    """
    Trains a calibration model to rank and select the best parser output.
    训练一个校准模型，用于对解析器输出进行排序和筛选。
    """
    
    def __init__(self, workspace_name: str = ADDRESSFORGE_WORKSPACE_NAME):
        self.workspace_name = workspace_name

    def collect_training_features(self, limit: int = 2000) -> List[Dict[str, Any]]:
        """
        Extracts advanced features from both the rule-engine and LLM outcomes.
        从规则引擎和 LLM 结果中提取高级特征。
        """
        # Fetch gold labels with detailed metadata
        # 获取带有元数据的金标数据
        query = """
            SELECT
                g.label_json,
                acr.confidence as system_conf,
                acr.parser_json,
                acr.validation_json,
                acr.building_type,
                acr.suggested_unit_number,
                acr.decision,
                r.raw_address_text,
                r.postal_code
            FROM gold_label g
            JOIN address_cleaning_result acr
              ON g.workspace_name = acr.workspace_name
             AND CAST(acr.raw_id AS CHAR) = g.source_id
            JOIN raw_address_record r
              ON acr.workspace_name = r.workspace_name
             AND acr.raw_id = r.raw_id
            WHERE g.workspace_name = %s AND g.review_status = 'accepted'
            LIMIT %s
        """
        rows = fetch_all(query, (self.workspace_name, limit))
        
        features = []
        for row in rows:
            raw_text = row["raw_address_text"]
            try:
                label_json = json.loads(row["label_json"] or "{}")
            except Exception:
                label_json = {}
            try:
                parser_json = json.loads(row["parser_json"] or "{}")
            except Exception:
                parser_json = {}
            try:
                v_json = json.loads(row["validation_json"] or "{}")
            except Exception:
                v_json = {}
            best_candidate = (parser_json or {}).get("best_candidate") or {}
            best_parsed = best_candidate.get("parsed") or {}
            f_vec = best_parsed.get("feature_vector") or {}
            predicted_decision = str(row.get("decision") or "").strip().lower()
            predicted_building = str(row.get("building_type") or "").strip().lower()
            predicted_unit = canonicalize_unit_number(row.get("suggested_unit_number"))
            gold_decision = str(label_json.get("decision") or "").strip().lower()
            gold_building = str(label_json.get("building_type") or label_json.get("structure_type") or "").strip().lower()
            gold_unit = canonicalize_unit_number(
                label_json.get("unit_number")
                or label_json.get("suggested_unit_number")
                or ((label_json.get("canonical") or {}).get("unit_number"))
            )
            
            # Cross-feature: FSA (Forward Sortation Area) prefix
            # 交叉特征：FSA (邮编前缀)
            pc = row["postal_code"] or ""
            fsa = pc[:3].upper() if len(pc) >= 3 else "UNK"
            parser_source = (
                best_candidate.get("parser_name")
                or best_parsed.get("unit_source")
                or "unknown"
            )
            predicted_street_name = normalize_street_name(best_parsed.get("street_name"))
            gold_street_name = normalize_street_name(
                label_json.get("street_name")
                or ((label_json.get("canonical") or {}).get("street_name"))
            )
            target_is_correct = int(
                predicted_decision == gold_decision
                and predicted_building == gold_building
                and predicted_unit == gold_unit
                and (gold_street_name is None or predicted_street_name == gold_street_name)
            )

            feat = {
                "unit_source": parser_source,
                "text_length": len(raw_text),
                "has_unit_keyword": f_vec.get("regex_hit", 0),
                "is_commercial_hit": f_vec.get("is_commercial", 0),
                "system_confidence": float(row["system_conf"] or 0),
                "llm_was_involved": 1 if v_json.get("llm_refinement") else 0,
                "fsa_prefix": fsa,
                "target_is_correct": target_is_correct,
            }
            features.append(feat)
        return features


    def train_reranking_weights(self) -> Dict[str, Any]:
        """
        Calculates optimal weights and saves them as a versioned model artifact.
        计算最优权重并将其保存为版本化的模型产物。
        """
        from pathlib import Path
        from addressforge.core.config import ADDRESSFORGE_MODEL_ARTIFACT_DIR
        import datetime

        run_id = create_run("reranking_train", notes="Parser reranking weight calibration")
        logger.info("Starting reranking calibration for workspace: %s", self.workspace_name)
        
        try:
            features = self.collect_training_features()
            if not features:
                logger.warning("Insufficient gold data to train reranker.")
                return {"status": "skipped", "reason": "insufficient_gold_data"}

            # Calculate precision for each parser source
            # 为每个解析源计算精确率
            source_stats = {}
            for f in features:
                src = f.get("unit_source", "unknown")
                if src not in source_stats:
                    source_stats[src] = {"total": 0, "correct": 0}
                source_stats[src]["total"] += 1
                # If LLM was involved and result was accepted, boost source reliability
                # 如果 LLM 参与且结果被接受，则提升源可靠性
                if f.get("target_is_correct") == 1:
                    source_stats[src]["correct"] += 1
            
            # Final weights (Confidence Scores)
            # 最终权重 (置信度分值)
            weights = {src: round(s["correct"] / s["total"], 4) for src, s in source_stats.items()}
            
            # Export as artifact
            # 作为产物导出
            version = f"reranker_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            artifact_dir = Path(ADDRESSFORGE_MODEL_ARTIFACT_DIR)
            artifact_dir.mkdir(parents=True, exist_ok=True)
            
            weight_path = artifact_dir / f"{version}_weights.json"
            with open(weight_path, "w") as f:
                json.dump(weights, f, indent=2)

            metadata = {
                "model_version": version,
                "weights": weights,
                "artifact_path": str(weight_path),
                "sample_size": len(features)
            }
            
            finish_run(run_id, "completed", notes=dumps_payload(metadata))
            logger.info("Reranker training completed: %s", version)
            return metadata

        except Exception as exc:
            logger.exception("Reranking training failed: %s", exc)
            finish_run(run_id, "failed", notes=str(exc))
            raise
