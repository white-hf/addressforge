import requests
import json
import time

def verify_shadow_ml():
    url = "http://127.0.0.1:8010/api/v1/validate"
    
    test_cases = [
        {"text": "111 - 1350 Oxford Street Halifax NS", "desc": "Double number house"},
        {"text": "******", "desc": "Garbage text"},
        {"text": "Halifax NS", "desc": "Incomplete address"}
    ]
    
    print("--- Verifying Shadow ML via API ---")
    for tc in test_cases:
        payload = {"raw_address_text": tc["text"]}
        try:
            res = requests.post(url, json=payload)
            if res.status_code == 200:
                data = res.json()
                ml = data.get("ml_decision", {})
                best = data.get("parser_result", {}).get("best_candidate", {})
                print(f"Input: {tc['text']} ({tc['desc']})")
                print(f"  Heuristic Decision: {data.get('decision')}")
                print(f"  ML Decision: {ml.get('ml_decision')} (Score: {ml.get('ml_score')})")
                print(f"  Best Candidate Rerank Score: {best.get('rerank_score', 'N/A')}")
                print(f"  Best Candidate Final Score: {best.get('final_score', 'N/A')}")
            else:
                print(f"Error for {tc['text']}: HTTP {res.status_code}")
        except Exception as e:
            print(f"Connection failed: {e}")

if __name__ == "__main__":
    verify_shadow_ml()
