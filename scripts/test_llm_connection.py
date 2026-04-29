from __future__ import annotations

import os
import sys
from pathlib import Path

# Add src to sys.path
# 将 src 添加到系统路径
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from addressforge.core.llm_refiner import LLMAddressRefiner
from addressforge.core.utils import logger

def test_ollama_integration():
    """
    Diagnostic script to test local Ollama connectivity and reasoning.
    测试本地 Ollama 连接性与推理能力的诊断脚本。
    """
    # Override env for local testing
    # 覆盖环境变量进行本地测试
    os.environ["ADDRESSFORGE_LLM_MODEL"] = "qwen2.5:7b" # User's model
    
    refiner = LLMAddressRefiner()
    
    test_cases = [
        "101-123 MAIN ST BSMT",
        "SUITE 500, 1505 BARRINGTON ST",
        "PENTHOUSE 1, 1234 SPRING GARDEN RD"
    ]
    
    print("\n--- Ollama Integration Test ---")
    for addr in test_cases:
        print(f"\nProcessing Address: {addr}")
        try:
            # Current result mock
            # 当前结果模拟
            mock_result = {"street_number": "123", "street_name": "MAIN ST", "unit_number": "101"}
            
            result = refiner.refine_parsing(addr, mock_result)
            print(f"LLM Response: {result}")
            
        except Exception as e:
            print(f"Test Failed: {e}")

if __name__ == "__main__":
    test_ollama_integration()
