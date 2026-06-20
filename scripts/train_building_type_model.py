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
from addressforge.api.server import AddressPlatformService, AddressRequest

def train_building_type_model(workspace_name="default"):
    print(f"--- Phase 17: Training BuildingTypeModel for workspace: {workspace_name} ---")
    
    query = """
        SELECT 
            g.label_json as gold_json,
            r.raw_address_text
        FROM gold_label g
        JOIN (
            SELECT source_id, MAX(gold_label_id) AS latest_gold_label_id
            FROM gold_label
            WHERE workspace_name = %s
              AND review_status = 'accepted'
            GROUP BY source_id
        ) latest ON latest.latest_gold_label_id = g.gold_label_id
        JOIN raw_address_record r ON g.source_id = CAST(r.raw_id AS CHAR)
        WHERE g.workspace_name = %s
          AND g.source_id REGEXP '^[0-9]+$'
    """
    rows = fetch_all(query, (workspace_name, workspace_name))
    
    if not rows:
        print("No gold labels found for BuildingType training.")
        return

    print(f"Found {len(rows)} samples. Validating on-the-fly to extract latest features...")
    
    service = AddressPlatformService()
    extractor = AddressFeatureExtractor()
    X_list = []
    y_list = []
    
    # Class mapping
    # 0 = single_unit, 1 = multi_unit, 2 = commercial
    class_map = {"single_unit": 0, "multi_unit": 1, "commercial": 2}
    
    for i, row in enumerate(rows):
        if i % 100 == 0:
            print(f"Processing sample {i}/{len(rows)}...")
        raw_text = row["raw_address_text"]
        gold_json = json.loads(row["gold_json"]) if isinstance(row["gold_json"], str) else row["gold_json"]
        
        building_type = gold_json.get("building_type")
        if building_type not in class_map:
            continue
            
        target = class_map[building_type]
        
        try:
            val_res = service.validate(AddressRequest(
                raw_address_text=raw_text,
                city=gold_json.get("city"),
                province=gold_json.get("province"),
                postal_code=gold_json.get("postal_code"),
            ))
        except Exception as e:
            print(f"Error validating on-the-fly: {e}")
            continue
            
        best = val_res.get("best_candidate") or {}
        parsed = best.get("parsed") or {}
        
        validation_ctx = {
            "confidence": val_res.get("confidence", 0.5),
            "hints": val_res.get("hints", {})
        }
        reference_ctx = val_res.get("reference") or {}
        semantic_alignment = best.get("semantic_alignment", 0.0)

        features = extractor.extract_features(
            raw_text, 
            parsed, 
            parser_name=best.get("parser_name", "hybrid"),
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
