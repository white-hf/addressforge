import sys
import os
import json
import pandas as pd
import numpy as np
from pathlib import Path
from catboost import CatBoostClassifier, Pool

# Add src to path
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from addressforge.core.common import fetch_all
from addressforge.core.features import AddressFeatureExtractor

def train_decision_model(workspace_name="default"):
    print(f"Exporting 3-class training data for workspace: {workspace_name}")
    
    # Query gold labels and associated cleaning results for 3-class labels
    query = """
        SELECT 
            g.review_status as gold_status,
            c.decision as system_decision,
            r.raw_address_text,
            c.parser_json,
            c.validation_json,
            c.reference_json
        FROM gold_label g
        JOIN raw_address_record r ON g.source_id = CAST(r.raw_id AS CHAR)
        LEFT JOIN address_cleaning_result c ON r.raw_id = c.raw_id
        WHERE g.workspace_name = %s
          AND (g.review_status IN ('accepted', 'rejected'))
          AND g.source_id REGEXP '^[0-9]+$'
    """
    rows = fetch_all(query, (workspace_name,))
    
    if not rows:
        print("No gold labels found for training.")
        return

    print(f"Found {len(rows)} samples. Extracting features...")
    
    extractor = AddressFeatureExtractor()
    X_list = []
    y_list = []
    
    # Class mapping: 0=reject, 1=accept, 2=review
    for row in rows:
        gold_status = row["gold_status"]
        system_dec = row["system_decision"]
        
        if gold_status == "rejected":
            target = 0
        elif system_dec == "review":
            target = 2
        else:
            target = 1
            
        raw_text = row["raw_address_text"]
        parser_json = json.loads(row["parser_json"]) if row.get("parser_json") else {}
        parsed = parser_json.get("best_candidate", {}).get("parsed", {})
        
        validation_ctx = json.loads(row["validation_json"]) if row.get("validation_json") else {}
        reference_ctx = json.loads(row["reference_json"]) if row.get("reference_json") else {}

        # For decision model, we assume semantic alignment is high for accepted/reviewed samples 
        # that had a reference match
        semantic_alignment = 1.0 if reference_ctx.get("external_id") else 0.0

        # Extract features
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

    # Convert to DataFrame
    X = pd.DataFrame(X_list)
    y = pd.Series(y_list)
    
    print(f"Label distribution: {y.value_counts().to_dict()}")
    
    print(f"Training 3-class CatBoost model (X shape: {X.shape})...")
    
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
    
    # Save model
    artifact_dir = Path("runtime/models")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    model_path = artifact_dir / "decision_catboost_v1.cbm"
    model.save_model(str(model_path))
    
    print(f"Model saved to {model_path}")
    
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
    train_decision_model()
