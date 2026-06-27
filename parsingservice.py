"""Сервис парсинга сайтов конкурентов через Selenium WebDriver."""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import TypedDict
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config import (
    COMPETITORS,
    DATA_DIR,
    HEADLESS_MODE,
    SELENIUM_IMPLICIT_WAIT,
    SELENIUM_TIMEOUT,
    SELENIUM_USER_AGENT,
    SELENIUM_WINDOW_HEIGHT,
    SELENIUM_WINDOW_WIDTH,
)

logger = logging.getLogger(__name__)


class ParseResult(TypedDict):
    """Результат парсинга сайта."""

    url: str
    screenshot_path: str
    text_path: str
    page_text: str
    title: str


def _validate_url(url: str) -> str:
    """
    Валидация и нормализация URL.

    Raises:
        ValueError: При некорректном URL.
    """
    url = url.strip()
    if not url:
        raise ValueError("URL не может быть пустым")

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    if not parsed.netloc:
        raise ValueError(f"Некорректный URL: {url}")

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Неподдерживаемая схема URL: {parsed.scheme}")

    return url


def _sanitize_filename(value: str) -> str:
    """Очистка строки для использования в имени файла."""
    sanitized = re.sub(r"[^\w\-.]", "_", value)
    return sanitized[:80] or "page"


def _create_driver() -> webdriver.Chrome:
    """Создание headless Chrome WebDriver."""
    options = ChromeOptions()
    if HEADLESS_MODE:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(f"--window-size={SELENIUM_WINDOW_WIDTH},{SELENIUM_WINDOW_HEIGHT}")
    options.add_argument(f"--user-agent={SELENIUM_USER_AGENT}")
    options.add_argument("--lang=ru-RU")

    try:
        driver = webdriver.Chrome(options=options, service=ChromeService())
        driver.set_page_load_timeout(SELENIUM_TIMEOUT)
        driver.implicitly_wait(SELENIUM_IMPLICIT_WAIT)
        return driver
    except WebDriverException as exc:
        logger.error("Не удалось запустить Chrome WebDriver: %s", exc)
        raise RuntimeError(
            "Ошибка запуска Selenium. Убедитесь, что Google Chrome установлен."
        ) from exc


def save_to_data_folder(url: str, screenshot: bytes, html_text: str) -> tuple[str, str]:
    """
    Сохранение скриншота и текста страницы в папку data/.

    Args:
        url: URL страницы.
        screenshot: Байты PNG-скриншота.
        html_text: Извлечённый текст страницы.

    Returns:
        Кортеж (путь к скриншоту, путь к текстовому файлу).
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    host = _sanitize_filename(urlparse(url).netloc)
    base_name = f"{host}_{timestamp}"

    screenshot_path = DATA_DIR / f"{base_name}.png"
    text_path = DATA_DIR / f"{base_name}.txt"

    screenshot_path.write_bytes(screenshot)
    text_path.write_text(html_text, encoding="utf-8")

    logger.info("Сохранено: %s, %s", screenshot_path.name, text_path.name)
    return str(screenshot_path), str(text_path)


def parse_competitor_website(url: str) -> ParseResult:
    """
    Парсинг сайта конкурента: скриншот и извлечение текста.

    Args:
        url: URL сайта для парсинга.

    Returns:
        ParseResult со скриншотом, текстом и путями к файлам.
    """
    normalized_url = _validate_url(url)
    driver: webdriver.Chrome | None = None

    logger.info("Начало парсинга: %s", normalized_url)

    try:
        driver = _create_driver()
        driver.get(normalized_url)

        WebDriverWait(driver, SELENIUM_TIMEOUT).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        title = driver.title or ""
        body = driver.find_element(By.TAG_NAME, "body")
        page_text = body.text.strip()

        if not page_text:
            page_text = driver.page_source[:5000]

        screenshot_bytes = driver.get_screenshot_as_png()
        screenshot_path, text_path = save_to_data_folder(
            normalized_url, screenshot_bytes, page_text
        )

        return ParseResult(
            url=normalized_url,
            screenshot_path=screenshot_path,
            text_path=text_path,
            page_text=page_text[:8000],
            title=title,
        )

    except TimeoutException as exc:
        logger.error("Таймаут загрузки страницы: %s", normalized_url)
        raise TimeoutError(
            f"Превышено время ожидания загрузки ({SELENIUM_TIMEOUT} с): {normalized_url}"
        ) from exc
    except WebDriverException as exc:
        logger.error("Ошибка Selenium при парсинге %s: %s", normalized_url, exc)
        raise RuntimeError(f"Ошибка парсинга сайта: {exc}") from exc
    finally:
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException as exc:
                logger.warning("Ошибка при закрытии WebDriver: %s", exc)


def get_competitor_urls() -> list[dict[str, str]]:
    """Возвращает список конкурентов из конфигурации."""
    return list(COMPETITORS)
