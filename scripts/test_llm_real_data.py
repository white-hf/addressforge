from __future__ import annotations

import os
import sys
import json
from pathlib import Path

# Setup sys.path for internal modules
# 为内部模块设置系统路径
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from addressforge.core.common import fetch_all
from addressforge.core.llm_refiner import LLMAddressRefiner
from addressforge.core.utils import logger

def run_real_data_test(limit: int = 5):
    """
    Fetches real 'low confidence' records and attempts LLM refinement.
    获取真实的“低置信度”记录并尝试 LLM 修复。
    """
    logger.info("--- Starting Real Data LLM Refinement Test (JSON-based) ---")
    
    # 1. Fetch real problematic samples from database (Extracting from parser_json)
    # 1. 从数据库中获取真实的存疑样本 (从 parser_json 中提取)
    query = """
        SELECT raw_id, raw_address_text, suggested_unit_number, confidence, parser_json
        FROM address_cleaning_result
        WHERE confidence < 0.7 AND workspace_name = 'default'
        ORDER BY confidence ASC
        LIMIT %s
    """
    samples = fetch_all(query, (limit,))
    
    if not samples:
        logger.warning("No low-confidence samples found in DB. Test aborted.")
        return

    refiner = LLMAddressRefiner()
    
    # 2. Process each sample with LLM
    # 2. 使用 LLM 处理每个样本
    for i, s in enumerate(samples):
        addr = s["raw_address_text"]
        p_data = json.loads(s["parser_json"] or "{}")
        
        s_num = p_data.get("street_number")
        s_name = p_data.get("street_name")
        u_num = s["suggested_unit_number"]
        
        print(f"\n[Sample {i+1}] Original ID: {s['raw_id']} | Conf: {s['confidence']}")
        print(f"Raw Address: {addr}")
        print(f"Rule Result: {s_num} {s_name} (Unit: {u_num})")
        
        try:
            # Reconstruct current result for LLM comparison
            curr_mock = {
                "street_number": s_num,
                "street_name": s_name,
                "unit_number": u_num
            }
            
            # Request LLM Insight
            # 请求 LLM 见解
            refined = refiner.refine_parsing(addr, curr_mock)
            
            print(f"LLM Result: {refined.get('street_number')} {refined.get('street_name')} (Unit: {refined.get('unit_number')})")
            print(f"LLM Reason: {refined.get('reasoning')}")
            
        except Exception as e:
            print(f"LLM Refinement Failed: {e}")

if __name__ == "__main__":
    run_real_data_test()
