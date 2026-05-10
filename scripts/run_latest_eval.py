import sys
import os
from pathlib import Path
import json

# Add src to path
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from addressforge.learning.evaluator import run_baseline_evaluation

def run_latest_eval():
    print("--- Running Latest Baseline Evaluation ---")
    try:
        result = run_baseline_evaluation(
            workspace_name="default",
            model_name="canada_default",
            model_version="v1"  # Or use a dynamic version if needed
        )
        print("\nEvaluation Results:")
        print(f"Sample Count: {result['sample_count']}")
        print(f"Overall Accuracy: {result['metrics_json'].get('accuracy', 'N/A')}")
        print(f"Decision F1: {result['metrics_json'].get('decision', {}).get('f1', 'N/A')}")
        print(f"Building Type F1: {result['metrics_json'].get('building_type', {}).get('f1', 'N/A')}")
        print(f"Unit Number F1: {result['metrics_json'].get('unit_number', {}).get('f1', 'N/A')}")
        print(f"Report Path: {result['report_path']}")
        
        # Read and display a summary of the report
        if os.path.exists(result['report_path']):
            with open(result['report_path'], 'r') as f:
                print("\n--- Report Summary ---")
                print(f.read()[:2000]) # First 2k chars
    except Exception as e:
        print(f"Evaluation failed: {e}")

if __name__ == "__main__":
    run_latest_eval()
