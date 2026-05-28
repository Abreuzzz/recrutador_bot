from __future__ import annotations

import json
import logging
import re
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.llm.prompts import build_json_retry_prompt

logger = logging.getLogger(__name__)
ModelT = TypeVar("ModelT", bound=BaseModel)


class OllamaError(RuntimeError):
    """Base error for local model failures."""


class OllamaConnectionError(OllamaError):
    """Raised when Ollama is unavailable or the model cannot respond."""


class OllamaResponseError(OllamaError):
    """Raised when the model repeatedly returns invalid content."""


def extract_json_object(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"```$", "", text).strip()

    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        json.loads(candidate)
        return candidate
    raise json.JSONDecodeError("Nenhum objeto JSON valido encontrado.", text, 0)


class OllamaClient:
    def __init__(self, settings: Settings, timeout_seconds: float = 180.0) -> None:
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model
        self.timeout_seconds = timeout_seconds

    def generate(self, prompt: str, retries: int = 1) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1},
        }
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(f"{self.base_url}/api/generate", json=payload)
                    response.raise_for_status()
                    data = response.json()
                    model_response = data.get("response")
                    if not isinstance(model_response, str):
                        raise OllamaConnectionError("Ollama retornou payload sem campo 'response'.")
                    return model_response.strip()
            except (httpx.HTTPError, json.JSONDecodeError, OllamaConnectionError) as exc:
                last_error = exc
                logger.warning("Falha ao chamar Ollama (tentativa %s): %s", attempt + 1, exc)
        raise OllamaConnectionError(
            f"Não consegui conectar ao Ollama ou ao modelo configurado ({self.model})."
        ) from last_error

    def generate_validated_json(
        self,
        prompt: str,
        schema: type[ModelT],
        schema_description: str,
        max_attempts: int = 3,
    ) -> ModelT:
        current_prompt = prompt
        invalid_response = ""
        validation_error = ""

        for attempt in range(max_attempts):
            raw_response = self.generate(current_prompt, retries=1)
            try:
                json_text = extract_json_object(raw_response)
                return schema.model_validate_json(json_text)
            except (json.JSONDecodeError, ValidationError) as exc:
                invalid_response = raw_response
                validation_error = str(exc)
                logger.warning(
                    "Resposta inválida do LLM para %s na tentativa %s: %s",
                    schema.__name__,
                    attempt + 1,
                    exc,
                )
                current_prompt = build_json_retry_prompt(
                    original_prompt=prompt,
                    invalid_response=invalid_response,
                    validation_error=validation_error,
                    schema_description=schema_description,
                )

        logger.error(
            "Resposta inválida do LLM após retries. Schema=%s Erro=%s Resposta=%s",
            schema.__name__,
            validation_error,
            invalid_response,
        )
        raise OllamaResponseError(
            "O modelo retornou uma resposta inválida mesmo após tentativas de correção."
        )
