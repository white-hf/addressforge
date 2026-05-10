import sys
import os
import json
import pandas as pd
import numpy as np
from pathlib import Path
from catboost import CatBoostClassifier

# Add src to path
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from addressforge.core.common import fetch_all, canonicalize_unit_number, normalize_street_name
from addressforge.core.features import AddressFeatureExtractor

def train_reranker_model(workspace_name="default"):
    print(f"Exporting reranking data for workspace: {workspace_name}")
    
    query = """
        SELECT 
            g.label_json as gold_json,
            r.raw_address_text,
            c.parser_json
        FROM gold_label g
        JOIN raw_address_record r ON g.source_id = CAST(r.raw_id AS CHAR)
        JOIN address_cleaning_result c ON r.raw_id = c.raw_id
        WHERE g.workspace_name = %s
          AND g.review_status = 'accepted'
          AND g.source_id REGEXP '^[0-9]+$'
    """
    rows = fetch_all(query, (workspace_name,))
    
    if not rows:
        print("No gold labels found for reranker training.")
        return

    print(f"Found {len(rows)} samples. Extracting candidate features...")
    
    extractor = AddressFeatureExtractor()
    X_list = []
    y_list = []
    
    for row in rows:
        raw_text = row["raw_address_text"]
        gold_json = json.loads(row["gold_json"]) if isinstance(row["gold_json"], str) else row["gold_json"]
        parser_json = json.loads(row["parser_json"]) if isinstance(row["parser_json"], str) else row["parser_json"]
        
        candidates = parser_json.get("candidates", [])
        if not candidates:
            continue
            
        # Define "Correct" target values from gold label
        gold_sn = str(gold_json.get("street_number") or "").strip()
        gold_st = normalize_street_name(gold_json.get("street_name"))
        gold_un = canonicalize_unit_number(gold_json.get("unit_number"))
        gold_base_key = gold_json.get("base_address_key")
        
        # First pass: find the top heuristic score for this sample
        best_h_score = max([float(c.get("score") or 0.5) for c in candidates])
        
        for cand in candidates:
            parsed = cand.get("parsed", {})
            cand_sn = str(parsed.get("street_number") or "").strip()
            cand_st = normalize_street_name(parsed.get("street_name"))
            cand_un = canonicalize_unit_number(parsed.get("unit_number"))
            cand_base_key = parsed.get("base_address_key")
            
            # Match logic
            is_match = (cand_sn == gold_sn and cand_st == gold_st and cand_un == gold_un)
            
            # Phase 13: Simulate semantic alignment
            semantic_alignment = 1.0 if gold_base_key and cand_base_key and gold_base_key == cand_base_key else 0.0

            # Extract features for this candidate
            features = extractor.extract_features(
                raw_text, 
                parsed, 
                parser_name=cand.get("parser_name", "unknown"),
                best_candidate_score=best_h_score,
                semantic_alignment=semantic_alignment
            )
            vector = extractor.vectorize(features)
            
            X_list.append(vector)
            y_list.append(1 if is_match else 0)

    if not X_list:
        print("No training pairs generated.")
        return

    # Convert to DataFrame
    X = pd.DataFrame(X_list)
    y = pd.Series(y_list)
    
    print(f"Training Reranker model (X shape: {X.shape}, Positive: {sum(y)})...")
    
    model = CatBoostClassifier(
        iterations=500,
        depth=6,
        learning_rate=0.05,
        loss_function='Logloss',
        verbose=100,
        random_seed=42,
        auto_class_weights='Balanced'
    )
    
    model.fit(X, y)
    
    # Save model
    artifact_dir = Path("runtime/models")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / "reranker_catboost_v1.cbm"
    model.save_model(str(model_path))
    
    # Print feature importance
    importance = model.get_feature_importance()
    feature_names = [
        "text_len", "token_count", "digit_block_count", 
        "has_comma", "has_hyphen", "has_directional",
        "has_street_number", "has_street_name", "has_unit", 
        "has_city", "has_postal", "is_province_valid", 
        "is_city_valid", "is_unit_redundant", "has_double_number", 
        "is_numbered_road", "has_hwy_keyword", "has_explicit_unit_hint",
        "has_org_indicator", "excess_token_count", "has_heavy_excess",
        "confidence", "reference_score", "gps_conflict", "parser_disagreement",
        "parse_confidence", "score_delta", "semantic_alignment"
    ]
    fi_df = pd.DataFrame({'feature': feature_names, 'importance': importance}).sort_values('importance', ascending=False)
    print("\nFeature Importance:")
    print(fi_df)

if __name__ == "__main__":
    train_reranker_model()
