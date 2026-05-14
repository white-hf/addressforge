import sys
import os
import json
import pandas as pd
import numpy as np
from pathlib import Path
from catboost import CatBoostClassifier

# Add src to path
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from addressforge.core.common import fetch_all
from addressforge.core.features import AddressFeatureExtractor

def train_building_type_model(workspace_name="default"):
    print(f"--- Phase 17: Training BuildingTypeModel for workspace: {workspace_name} ---")
    
    query = """
        SELECT 
            g.label_json as gold_json,
            r.raw_address_text,
            c.parser_json,
            c.validation_json,
            c.reference_json
        FROM gold_label g
        JOIN raw_address_record r ON g.source_id = CAST(r.raw_id AS CHAR)
        JOIN address_cleaning_result c ON r.raw_id = c.raw_id
        WHERE g.workspace_name = %s
          AND g.review_status = 'accepted'
          AND g.source_id REGEXP '^[0-9]+$'
    """
    rows = fetch_all(query, (workspace_name,))
    
    if not rows:
        print("No gold labels found for BuildingType training.")
        return

    print(f"Found {len(rows)} samples. Extracting features...")
    
    extractor = AddressFeatureExtractor()
    X_list = []
    y_list = []
    
    # Class mapping
    # 0 = single_unit, 1 = multi_unit, 2 = commercial
    class_map = {"single_unit": 0, "multi_unit": 1, "commercial": 2}
    
    for row in rows:
        raw_text = row["raw_address_text"]
        gold_json = json.loads(row["gold_json"]) if isinstance(row["gold_json"], str) else row["gold_json"]
        
        building_type = gold_json.get("building_type")
        if building_type not in class_map:
            continue
            
        target = class_map[building_type]
        
        parser_json = json.loads(row["parser_json"]) if row.get("parser_json") else {}
        parsed = parser_json.get("best_candidate", {}).get("parsed", {})
        
        validation_ctx = json.loads(row["validation_json"]) if row.get("validation_json") else {}
        reference_ctx = json.loads(row["reference_json"]) if row.get("reference_json") else {}

        # Semantic alignment simulation
        semantic_alignment = 1.0 if reference_ctx.get("external_id") else 0.0

        features = extractor.extract_features(
            raw_text, 
            parsed, 
            parser_name="hybrid",
            validation_context=validation_ctx,
            reference_context=reference_ctx,
            semantic_alignment=semantic_alignment
        )
        vector = extractor.vectorize(features)
        
        X_list.append(vector)
        y_list.append(target)

    if not X_list:
        print("No valid training samples generated.")
        return

    X = pd.DataFrame(X_list)
    y = pd.Series(y_list)
    
    print(f"Label distribution: {y.value_counts().to_dict()} (0: single, 1: multi, 2: comm)")
    print(f"Training 3-class CatBoost BuildingType model (X shape: {X.shape})...")
    
    model = CatBoostClassifier(
        iterations=500,
        depth=6,
        learning_rate=0.08,
        loss_function='MultiClass',
        verbose=100,
        random_seed=42,
        auto_class_weights='Balanced'
    )
    
    model.fit(X, y)
    
    artifact_dir = Path("runtime/models")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / "building_type_catboost_v1.cbm"
    model.save_model(str(model_path))
    
    print(f"BuildingType model saved to {model_path}")
    
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
    train_building_type_model()
