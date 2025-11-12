"""
LLM 모델 가격표
Model Pricing Configuration
"""

from typing import Dict


# 모델별 가격 (USD per 1M tokens)
MODEL_PRICING = {
    # Gemini 2.5 Models (현재 사용 중)
    "gemini-2.5-pro": {
        "input": 1.25,  # $1.25 per 1M input tokens
        "output": 5.00,  # $5.00 per 1M output tokens
    },
    "gemini-2.5-flash": {
        "input": 0.075,  # $0.075 per 1M input tokens
        "output": 0.30,  # $0.30 per 1M output tokens
    },
    "gemini-2.5-flash-lite": {
        "input": 0.0375,  # $0.0375 per 1M input tokens (절반 가격)
        "output": 0.15,   # $0.15 per 1M output tokens
    },

    # Default fallback
    "default": {
        "input": 0.075,
        "output": 0.30,
    }
}


def calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """
    모델 사용 비용 계산

    Args:
        model_name: 모델 이름
        input_tokens: 입력 토큰 수
        output_tokens: 출력 토큰 수

    Returns:
        총 비용 (USD)
    """
    pricing = MODEL_PRICING.get(model_name, MODEL_PRICING["default"])

    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]

    return input_cost + output_cost


def get_model_pricing(model_name: str) -> Dict[str, float]:
    """모델 가격 정보 조회"""
    return MODEL_PRICING.get(model_name, MODEL_PRICING["default"])
