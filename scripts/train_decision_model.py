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
    print(f"Exporting training data for workspace: {workspace_name}")
    
    # Query gold labels and associated raw/cleaning data
    # Only include labels where source_id is numeric (representing raw_id)
    query = """
        SELECT 
            g.review_status as label_decision,
            g.label_json as gold_json,
            r.raw_address_text,
            c.parser_json,
            c.validation_json,
            c.reference_json,
            c.confidence as heuristic_confidence
        FROM gold_label g
        JOIN raw_address_record r ON g.source_id = CAST(r.raw_id AS CHAR)
        LEFT JOIN address_cleaning_result c ON r.raw_id = c.raw_id
        WHERE g.workspace_name = %s
          AND g.review_status IN ('accepted', 'rejected')
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
    
    for row in rows:
        raw_text = row["raw_address_text"]
        parser_json = json.loads(row["parser_json"]) if row["parser_json"] else {}
        # Use the best candidate from parser_json if available
        parsed = parser_json.get("best_candidate", {}).get("parsed", {})
        
        # New: Include contexts for richer feature extraction
        # 新增：包含上下文以进行更丰富的特征提取
        validation_ctx = json.loads(row["validation_json"]) if row.get("validation_json") else {}
        reference_ctx = json.loads(row["reference_json"]) if row.get("reference_json") else {}

        # Extract features
        features = extractor.extract_features(
            raw_text, 
            parsed, 
            parser_name="hybrid",
            validation_context=validation_ctx,
            reference_context=reference_ctx
        )
        vector = extractor.vectorize(features)
        
        X_list.append(vector)
        
        # Label: accepted -> 1, rejected -> 0 (or multi-class if we add 'review')
        # Since we only have accepted/rejected in training set for now
        y_list.append(1 if row["label_decision"] == "accepted" else 0)

    # Convert to DataFrame
    X = pd.DataFrame(X_list)
    y = pd.Series(y_list)
    
    print(f"Training CatBoost model (X shape: {X.shape})...")
    
    model = CatBoostClassifier(
        iterations=500,
        depth=6,
        learning_rate=0.1,
        loss_function='Logloss',
        verbose=100,
        random_seed=42
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
        "confidence", "reference_score", "gps_conflict", "parser_disagreement",
        "parse_confidence"
    ]
    fi_df = pd.DataFrame({'feature': feature_names, 'importance': importance}).sort_values('importance', ascending=False)
    print("\nFeature Importance:")
    print(fi_df)

if __name__ == "__main__":
    train_decision_model()
