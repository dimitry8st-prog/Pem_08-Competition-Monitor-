"""Конфигурация приложения Competition Monitor."""

import os
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv

load_dotenv()

# Корневая директория проекта
BASE_DIR: Path = Path(__file__).resolve().parent
DATA_DIR: Path = BASE_DIR / "data"
HISTORY_FILE: Path = DATA_DIR / "history.json"

# Создание папки data при импорте
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Competitor(TypedDict):
    """Структура записи конкурента."""

    name: str
    url: str
    niche: str


COMPETITORS: list[Competitor] = [
    {
        "name": "Awwwards",
        "url": "https://www.awwwards.com/",
        "niche": "design",
    },
    {
        "name": "LottieFiles",
        "url": "https://lottiefiles.com/",
        "niche": "animation",
    },
    {
        "name": "Dribbble",
        "url": "https://dribbble.com/",
        "niche": "design",
    },
    {
        "name": "Codrops",
        "url": "https://tympanus.net/codrops/",
        "niche": "animation",
    },
    {
        "name": "Behance",
        "url": "https://www.behance.net/",
        "niche": "design",
    },
]

# OpenAI / ProxyAPI
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
PROXY_API_KEY: str = os.getenv("PROXY_API_KEY", "") or os.getenv("PROXY_API", "")
PROXY_API_BASE_URL: str = os.getenv(
    "OPENAI_BASE_URL",
    "https://api.proxyapi.ru/openai/v1" if PROXY_API_KEY else "https://api.openai.com/v1",
)
OPENAI_BASE_URL: str = PROXY_API_BASE_URL
OPENAI_TEXT_MODEL: str = os.getenv(
    "OPENAI_TEXT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini")
)
OPENAI_VISION_MODEL: str = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")
OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
OPENAI_MAX_RETRIES: int = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
TEST_MODE: bool = os.getenv("TEST_MODE", "False").lower() in ("true", "1", "yes")
USE_PROXY_API: bool = bool(PROXY_API_KEY)

# API-сервер
API_PORT: int = int(os.getenv("API_PORT", "8000"))
API_BIND_HOST: str = os.getenv("API_HOST", "127.0.0.1")
# Клиент всегда подключается через localhost (0.0.0.0 нельзя использовать в URL)
API_CLIENT_HOST: str = (
    "127.0.0.1" if API_BIND_HOST in ("0.0.0.0", "::", "") else API_BIND_HOST
)
API_BASE_URL: str = f"http://{API_CLIENT_HOST}:{API_PORT}"

# Selenium
SELENIUM_TIMEOUT: int = int(os.getenv("SELENIUM_TIMEOUT", "30"))
HEADLESS_MODE: bool = os.getenv("HEADLESS_MODE", "True").lower() in ("true", "1", "yes")
SELENIUM_IMPLICIT_WAIT: int = int(os.getenv("SELENIUM_IMPLICIT_WAIT", "10"))
SELENIUM_USER_AGENT: str = os.getenv(
    "SELENIUM_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)
SELENIUM_WINDOW_WIDTH: int = int(os.getenv("SELENIUM_WINDOW_WIDTH", "1920"))
SELENIUM_WINDOW_HEIGHT: int = int(os.getenv("SELENIUM_WINDOW_HEIGHT", "1080"))

# История
MAX_HISTORY_ITEMS: int = int(os.getenv("MAX_HISTORY_ITEMS", "100"))

# Разрешённые расширения изображений
ALLOWED_IMAGE_EXTENSIONS: set[str] = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
