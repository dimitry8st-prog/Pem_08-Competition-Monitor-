"""Интеграция с OpenAI API для анализа веб-дизайна и анимаций."""

import base64
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Literal

from openai import APIConnectionError, APIError, OpenAI, RateLimitError
from pydantic import BaseModel, Field, field_validator

from config import (
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MAX_RETRIES,
    OPENAI_TEMPERATURE,
    OPENAI_TEXT_MODEL,
    OPENAI_VISION_MODEL,
    PROXY_API_KEY,
)

logger = logging.getLogger(__name__)

AnimationPotential = Literal["low", "medium", "high"]

ANALYSIS_SYSTEM_PROMPT: str = """Ты — эксперт по веб-дизайну, UI/UX и веб-анимациям.
Анализируй контент конкурентов в нише веб-дизайна и анимации.

Оценивай:
- Визуальную согласованность и современные тренды
- Использование анимаций (микро-взаимодействия, переходы, скролл-эффекты)
- UX/UI паттерны и удобство использования
- Цветовые схемы и типографику
- Дизайн компонентов и принципы вёрстки
- Качество адаптивного дизайна

Верни ТОЛЬКО валидный JSON без markdown:
{
    "design_score": <число 0-10>,
    "animation_potential": "low" | "medium" | "high",
    "color_scheme": "<описание цветовой схемы>",
    "ui_elements": ["<элемент UI>", ...],
    "strengths": ["<сильная сторона>", ...],
    "weaknesses": ["<слабая сторона>", ...],
    "recommendations": ["<рекомендация>", ...]
}

Каждый массив — 3–5 пунктов. Пиши на русском языке."""


class DesignAnalysis(BaseModel):
    """Результат AI-анализа веб-дизайна и анимаций."""

    design_score: int = Field(..., ge=0, le=10)
    animation_potential: AnimationPotential
    color_scheme: str
    ui_elements: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    @field_validator("animation_potential", mode="before")
    @classmethod
    def normalize_animation_potential(cls, value: Any) -> str:
        """Нормализация значения animation_potential."""
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in ("low", "medium", "high"):
                return normalized
        return "medium"


def _get_client() -> OpenAI:
    """Создание клиента OpenAI с поддержкой ProxyAPI."""
    api_key = PROXY_API_KEY or OPENAI_API_KEY
    if not api_key:
        raise ValueError("Задайте PROXY_API_KEY или OPENAI_API_KEY в .env")

    base_url = OPENAI_BASE_URL
    if PROXY_API_KEY:
        logger.info("Используется ProxyAPI: %s", base_url)
    else:
        logger.info("Используется OpenAI API: %s", base_url)

    return OpenAI(api_key=api_key, base_url=base_url)


def _parse_json_response(content: str) -> dict[str, Any]:
    """Извлечение JSON из ответа модели."""
    if not content:
        return {}

    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    if json_match:
        content = json_match.group(1)

    json_match = re.search(r"\{[\s\S]*\}", content)
    if json_match:
        content = json_match.group(0)

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error("Ошибка разбора JSON от OpenAI: %s", exc)
        return {}


def _build_analysis(data: dict[str, Any]) -> DesignAnalysis:
    """Построение модели анализа из сырого словаря."""
    return DesignAnalysis(
        design_score=int(data.get("design_score", 5)),
        animation_potential=data.get("animation_potential", "medium"),
        color_scheme=str(data.get("color_scheme", "Не определено")),
        ui_elements=data.get("ui_elements", []) or [],
        strengths=data.get("strengths", []) or [],
        weaknesses=data.get("weaknesses", []) or [],
        recommendations=data.get("recommendations", []) or [],
    )


def _call_with_retry(func: Any) -> Any:
    """Вызов API с повторными попытками при временных ошибках."""
    last_error: Exception | None = None

    for attempt in range(1, OPENAI_MAX_RETRIES + 1):
        try:
            return func()
        except RateLimitError as exc:
            last_error = exc
            wait_time = 2 ** attempt
            logger.warning(
                "Rate limit OpenAI, попытка %d/%d, ожидание %d с",
                attempt,
                OPENAI_MAX_RETRIES,
                wait_time,
            )
            time.sleep(wait_time)
        except APIConnectionError as exc:
            last_error = exc
            wait_time = 2 ** attempt
            logger.warning(
                "Ошибка соединения OpenAI, попытка %d/%d: %s",
                attempt,
                OPENAI_MAX_RETRIES,
                exc,
            )
            time.sleep(wait_time)
        except APIError as exc:
            logger.error("Ошибка OpenAI API: %s", exc)
            raise

    raise last_error or APIError("Превышено число попыток запроса к OpenAI")


def analyze_landing_image(image_path: str | Path) -> DesignAnalysis:
    """
    Анализ скриншота лендинга через GPT-4 Vision.

    Args:
        image_path: Путь к файлу изображения.

    Returns:
        Структурированный результат анализа.
    """
    path = Path(image_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Файл изображения не найден: {path}")

    suffix = path.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime_type = mime_map.get(suffix, "image/jpeg")

    image_data = base64.b64encode(path.read_bytes()).decode("utf-8")
    client = _get_client()

    logger.info("Анализ изображения: %s", path.name)

    def _request() -> DesignAnalysis:
        response = client.chat.completions.create(
            model=OPENAI_VISION_MODEL,
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Проанализируй скриншот веб-сайта конкурента. "
                                "Оцени визуальный дизайн, анимационный потенциал, "
                                "UI-элементы и UX-паттерны."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_data}",
                            },
                        },
                    ],
                },
            ],
            temperature=OPENAI_TEMPERATURE,
            max_tokens=2000,
        )
        content = response.choices[0].message.content or ""
        return _build_analysis(_parse_json_response(content))

    return _call_with_retry(_request)


def analyze_competitor_text(text_description: str) -> DesignAnalysis:
    """
    Анализ текстового описания конкурента через GPT-4.

    Args:
        text_description: Текстовое описание сайта или продукта конкурента.

    Returns:
        Структурированный результат анализа.
    """
    if not text_description or len(text_description.strip()) < 10:
        raise ValueError("Текст описания слишком короткий (минимум 10 символов)")

    client = _get_client()
    logger.info("Анализ текста конкурента (%d символов)", len(text_description))

    def _request() -> DesignAnalysis:
        response = client.chat.completions.create(
            model=OPENAI_TEXT_MODEL,
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Проанализируй текстовое описание веб-сайта/продукта конкурента "
                        "в нише веб-дизайна и анимации:\n\n"
                        f"{text_description}"
                    ),
                },
            ],
            temperature=OPENAI_TEMPERATURE,
            max_tokens=2000,
        )
        content = response.choices[0].message.content or ""
        return _build_analysis(_parse_json_response(content))

    return _call_with_retry(_request)
