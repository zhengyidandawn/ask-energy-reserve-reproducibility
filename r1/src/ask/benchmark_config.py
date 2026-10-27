from __future__ import annotations

from dataclasses import dataclass
from typing import Any


BENCHMARK_CONFIG_VERSION = "ask-benchmark-v2"
PROMPT_VERSION = "ask-boundary-v2.0"
TEMPERATURE = 0.0
TOP_P = 1.0
MAX_TOKENS = 1400
RESPONSE_FORMAT = {"type": "json_object"}


@dataclass(frozen=True)
class ServiceConfig:
    service: str
    api_provider: str
    model_name: str
    base_url: str
    api_key_env: str


SERVICES = {
    "deepseek": ServiceConfig(
        "deepseek", "DeepSeek", "deepseek-chat", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"
    ),
    "qwen": ServiceConfig(
        "qwen", "Alibaba Model Studio", "qwen-max", "https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"
    ),
    "ernie": ServiceConfig(
        "ernie", "Baidu Qianfan", "ernie-4.5-turbo-32k", "https://qianfan.baidubce.com/v2", "QIANFAN_API_KEY"
    ),
    "hunyuan": ServiceConfig(
        "hunyuan", "Tencent Hunyuan", "hy3-preview", "https://tokenhub.tencentmaas.com/v1", "HUNYUAN_API_KEY"
    ),
    "glm": ServiceConfig(
        "glm", "Zhipu GLM", "glm-5.2", "https://open.bigmodel.cn/api/paas/v4", "ZHIPUAI_API_KEY"
    ),
}


def canonical_settings() -> dict[str, Any]:
    return {
        "benchmark_config_version": BENCHMARK_CONFIG_VERSION,
        "temperature": TEMPERATURE,
        "top_p": TOP_P,
        "max_tokens": MAX_TOKENS,
        "response_format": dict(RESPONSE_FORMAT),
        "prompt_version": PROMPT_VERSION,
    }
