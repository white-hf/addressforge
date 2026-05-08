from __future__ import annotations

import json
from typing import Any, Dict
from addressforge.core.utils import logger

class LLMAddressRefiner:
    """
    Plugin for deep address reasoning using Large Language Models.
    使用大语言模型进行深度地址推理的插件。
    """

    def __init__(self, api_key: str | None = None, model_name: str = "gpt-4o"):
        self.api_key = api_key
        self.model_name = model_name

    def refine_parsing(self, raw_text: str, current_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Uses local Ollama (Qwen) via the verified /api/generate endpoint.
        Forces proxy bypass to resolve local 404 issues.
        通过已验证的 /api/generate 端点使用本地 Ollama (Qwen)。强制绕过代理以解决本地 404 问题。
        """
        import os
        import requests
        
        # Use explicit 127.0.0.1 and disable proxies
        # 使用显式的 127.0.0.1 并禁用代理
        api_url = os.getenv("ADDRESSFORGE_LLM_API_URL", "http://127.0.0.1:11434/api/generate")
        model = os.getenv("ADDRESSFORGE_LLM_MODEL", "qwen3:8b")

        logger.info("Connecting to local Ollama at %s (Model: %s)", api_url, model)
        
        prompt = (
            "You are parsing Canadian address text for a review workflow. "
            "Return only valid JSON with keys: "
            "'street_number', 'street_name', 'unit_number', 'building_type', 'decision_hint'. "
            "Use null for missing fields. "
            "building_type_hint must be one of: single_unit, multi_unit, commercial, unknown. "
            "decision_hint must be one of: accept, review, enrich. "
            "Special Rules for Ambiguity: "
            "1) GEOGRAPHIC MODIFIERS: In some rural Canadian areas, numbers like '1676 PICTOU' or '664 PICTOU' following a street address are often area codes or community identifiers, NOT unit numbers. If a number is followed by a known city/town name, prefer single_unit. "
            "2) REDUNDANT NUMBERS: If an address repeats the same number (e.g., '307 ... 307 GRAND PRE'), treat it as a House (single_unit) with the second number being redundant. "
            "3) Street types like Road, Street, Avenue, Lane are not by themselves commercial evidence. "
            f"Address: {raw_text}"
        )

        try:
            # Explicitly disable proxies to avoid local requests being routed to external servers
            # 显式禁用代理，避免本地请求被路由到外部服务器
            response = requests.post(
                api_url,
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0},
                    "format": "json"
                },
                proxies={"http": None, "https": None},
                headers={"Content-Type": "application/json", "User-Agent": "AddressForge-Refiner/1.0"},
                timeout=30
            )
            response.raise_for_status()
            res_json = response.json()
            
            content = res_json["response"]
            parsed_llm = json.loads(content)
            
            # Extract reasoning if available from Qwen
            # 如果 Qwen 提供了思考过程，则提取它
            reasoning = res_json.get("thinking", "LLM logical inference.")
            parsed_llm["reasoning"] = f"AI Insight: {reasoning[:200]}..."
            
            return parsed_llm




        except Exception as exc:
            logger.error("Ollama API call failed: %s. Falling back to simulation.", exc)
            return self._simulate_refinement(raw_text, current_result)


    def _simulate_refinement(self, raw_text: str, current_result: Dict[str, Any]) -> Dict[str, Any]:
        """Internal simulator for testing parsing flows."""
        llm_suggestion = {
            "street_number": current_result.get("street_number"),
            "street_name": current_result.get("street_name"),
            "unit_number": current_result.get("unit_number"),
            "building_type": current_result.get("building_type"),
            "decision_hint": "review",
            "reasoning": "Contextual analysis of text segments.",
            "confidence_boost": 0.15
        }
        if "BSMT" in raw_text.upper():
            llm_suggestion["unit_number"] = "BSMT"
            llm_suggestion["building_type"] = "multi_unit"
            llm_suggestion["decision_hint"] = "accept"
            llm_suggestion["reasoning"] = "Heuristic segment matching confirmed Basement."
        return llm_suggestion


def should_trigger_llm(parsing_result: Dict[str, Any], threshold: float = 0.6) -> bool:
    """
    Logic to decide if an expensive LLM call is required.
    决定是否需要进行昂贵的 LLM 调用的逻辑。
    """
    conf = parsing_result.get("parse_confidence", 1.0)
    # Trigger LLM if confidence is low or if conflict features are flagged
    # 如果置信度低或标记了冲突特征，则触发 LLM
    return conf < threshold or parsing_result.get("feature_vector", {}).get("is_rural") == 1
