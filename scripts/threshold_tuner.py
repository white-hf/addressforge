import json
import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd
from typing import Dict, Any

# Add src to path
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from addressforge.core.common import fetch_all, db_cursor
from addressforge.core.features import AddressFeatureExtractor
from catboost import CatBoostClassifier

def tune_thresholds():
    workspace = "default"
    model_path = "runtime/models/decision_catboost_v1.cbm"
    
    if not os.path.exists(model_path):
        print(f"Error: Model not found at {model_path}")
        return

    print(f"--- Threshold Tuner ---")
    print(f"Loading model: {model_path}")
    model = CatBoostClassifier()
    model.load_model(model_path)
    
    # 1. Fetch Gold Set features and labels
    print("Fetching evaluation data from gold set...")
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
    rows = fetch_all(query, (workspace,))
    
    if not rows:
        print("No gold set data found for tuning.")
        return

    extractor = AddressFeatureExtractor()
    vectors = []
    labels = []
    
    for r in rows:
        gold_status = r["gold_status"]
        system_dec = r["system_decision"]
        
        # Class mapping: 0=reject, 1=accept, 2=review
        if gold_status == "rejected":
            target = 0
        elif system_dec == "review":
            target = 2
        else:
            target = 1
            
        raw_text = r["raw_address_text"]
        parser_json = json.loads(r["parser_json"]) if r.get("parser_json") else {}
        parsed = parser_json.get("best_candidate", {}).get("parsed", {})
        
        validation_ctx = json.loads(r["validation_json"]) if r.get("validation_json") else {}
        reference_ctx = json.loads(r["reference_json"]) if r.get("reference_json") else {}
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
        vectors.append(vector)
        labels.append(target)

    X = pd.DataFrame(vectors)
    
    # 2. Get probabilities
    probs = model.predict_proba(X)
    
    best_f1 = 0
    best_threshold = 0.5
    
    # Scan potential thresholds for Accept class (index 1)
    thresholds = np.linspace(0.01, 0.95, 95)
    
    for t in thresholds:
        preds = []
        for p in probs:
            # If prob(Accept) > t, predict Accept
            if p[1] >= t:
                preds.append(1)
            else:
                # Decide between Reject (0) and Review (2)
                if p[0] >= p[2]:
                    preds.append(0)
                else:
                    preds.append(2)
        
        # Calculate F1 for Accept decisions (Binary F1)
        y_true = np.array(labels) == 1
        y_pred = np.array(preds) == 1
        
        tp = np.sum(y_true & y_pred)
        fp = np.sum((~y_true) & y_pred)
        fn = np.sum(y_true & (~y_pred))
        
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = t

    print(f"Optimization complete.")
    print(f"Best Decision Threshold: {best_threshold:.4f}")
    print(f"Predicted Max F1: {best_f1:.4f}")
    
    # 3. Persist the policy
    policy_path = "runtime/models/decision_policy.json"
    policy = {
        "version": "v1.2",
        "accept_threshold": float(best_threshold),
        "review_threshold": 0.05,
        "model_path": model_path,
        "tuned_at": pd.Timestamp.now().isoformat()
    }
    
    with open(policy_path, "w") as f:
        json.dump(policy, f, indent=2)
    
    print(f"Policy saved to {policy_path}")

if __name__ == "__main__":
    tune_thresholds()


if __name__ == "__main__":
    tune_thresholds()
