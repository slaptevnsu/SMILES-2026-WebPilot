from __future__ import annotations

import os
from dataclasses import dataclass

from openai import OpenAI


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.0

class LLMClient:
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or self._load_config_from_env()
        self.client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
        )

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.config.model,
            temperature=self.config.temperature,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        )

        message = response.choices[0].message.content

        if message is None:
            raise RuntimeError("LLM returned an empty response.")
        
        return message

    def _load_config_from_env(self) -> LLMConfig:
        base_url = os.environ.get("WEBPILOT_LLM_BASE_URL")
        api_key = os.environ.get("WEBPILOT_LLM_API_KEY")
        model = os.environ.get("WEBPILOT_LLM_MODEL")

        missing = []
        if not base_url:
            missing.append("WEBPILOT_LLM_BASE_URL")
        if not api_key:
            missing.append("WEBPILOT_LLM_API_KEY")
        if not model:
            missing.append("WEBPILOT_LLM_MODEL")

        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(
                f"Missing LLM environment variables: {joined}. "
                "Set them before running LLM-based WebPilot variants."
            )
        
        return LLMConfig(
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
    