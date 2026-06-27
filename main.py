"""FastAPI-бэкенд приложения Competition Monitor."""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import (
    ALLOWED_IMAGE_EXTENSIONS,
    API_BIND_HOST,
    API_PORT,
    DATA_DIR,
    HISTORY_FILE,
    MAX_HISTORY_ITEMS,
)
from openaiservice import DesignAnalysis, analyze_competitor_text, analyze_landing_image
from parsingservice import parse_competitor_website

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(DATA_DIR / "app.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


# --- Pydantic-модели ---


class TextAnalysisRequest(BaseModel):
    """Запрос на анализ текста конкурента."""

    text: str = Field(..., min_length=10, description="Описание конкурента")


class ParseDemoRequest(BaseModel):
    """Запрос на парсинг и анализ сайта."""

    url: str = Field(..., min_length=5, description="URL сайта конкурента")


class HistoryEntry(BaseModel):
    """Запись в истории анализов."""

    id: str
    timestamp: str
    analysis_type: str
    source: str
    analysis: DesignAnalysis
    screenshot_path: str | None = None
    cache_file: str | None = None


class HistoryResponse(BaseModel):
    """Ответ со списком истории."""

    items: list[HistoryEntry]
    total: int


class AnalysisResponse(BaseModel):
    """Универсальный ответ с результатом анализа."""

    success: bool
    analysis: DesignAnalysis | None = None
    history_id: str | None = None
    screenshot_path: str | None = None
    page_title: str | None = None
    error: str | None = None


# --- Утилиты ---


def _save_analysis_cache(
    analysis_type: str,
    source: str,
    analysis: DesignAnalysis,
    screenshot_path: str | None = None,
) -> tuple[str, str]:
    """Сохранение анализа в кэш-файл и history.json."""
    entry_id = str(uuid.uuid4())
    timestamp = datetime.now().isoformat()
    cache_filename = f"analysis_{analysis_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{entry_id[:8]}.json"
    cache_path = DATA_DIR / cache_filename

    cache_data: dict[str, Any] = {
        "id": entry_id,
        "timestamp": timestamp,
        "analysis_type": analysis_type,
        "source": source,
        "analysis": analysis.model_dump(),
        "screenshot_path": screenshot_path,
    }
    cache_path.write_text(
        json.dumps(cache_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    history_entry = HistoryEntry(
        id=entry_id,
        timestamp=timestamp,
        analysis_type=analysis_type,
        source=source,
        analysis=analysis,
        screenshot_path=screenshot_path,
        cache_file=str(cache_path),
    )
    _append_to_history(history_entry)

    logger.info("Анализ сохранён: %s (%s)", entry_id, analysis_type)
    return entry_id, str(cache_path)


def _load_history() -> list[dict[str, Any]]:
    """Загрузка истории из JSON-файла."""
    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text("[]", encoding="utf-8")
        return []

    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("Повреждённый history.json: %s", exc)
        return []


def _append_to_history(entry: HistoryEntry) -> None:
    """Добавление записи в history.json."""
    history = _load_history()
    history.insert(0, entry.model_dump())
    HISTORY_FILE.write_text(
        json.dumps(history[:MAX_HISTORY_ITEMS], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# --- Приложение FastAPI ---

app = FastAPI(
    title="Competition Monitor API",
    description="API для конкурентного анализа веб-дизайна и анимаций",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
    """Инициализация при запуске."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not HISTORY_FILE.exists():
        HISTORY_FILE.write_text("[]", encoding="utf-8")
    logger.info("Competition Monitor API запущен")


@app.get("/")
async def root() -> dict[str, Any]:
    """Корневой эндпоинт с информацией об API."""
    return {
        "service": "Competition Monitor",
        "version": "1.0.0",
        "endpoints": [
            "POST /analyzeimage",
            "POST /analyzetext",
            "POST /parsedemo",
            "GET /history",
        ],
    }


@app.get("/health")
async def health() -> dict[str, str]:
    """Проверка доступности сервиса."""
    return {"status": "ok"}


@app.post("/analyzeimage", response_model=AnalysisResponse)
async def analyze_image_endpoint(file: UploadFile = File(...)) -> AnalysisResponse:
    """Анализ загруженного изображения (скриншота лендинга)."""
    logger.info("POST /analyzeimage — файл: %s", file.filename)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Имя файла не указано")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемый формат. Разрешены: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}",
        )

    temp_name = f"upload_{uuid.uuid4().hex}{suffix}"
    temp_path = DATA_DIR / temp_name

    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Пустой файл изображения")

        temp_path.write_bytes(content)
        analysis = analyze_landing_image(temp_path)

        history_id, _ = _save_analysis_cache(
            analysis_type="image",
            source=file.filename,
            analysis=analysis,
            screenshot_path=str(temp_path),
        )

        return AnalysisResponse(
            success=True,
            analysis=analysis,
            history_id=history_id,
            screenshot_path=str(temp_path),
        )

    except HTTPException:
        raise
    except FileNotFoundError as exc:
        logger.error("Файл не найден: %s", exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        logger.error("Ошибка валидации: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Ошибка анализа изображения: %s", exc)
        return AnalysisResponse(success=False, error=str(exc))


@app.post("/analyzetext", response_model=AnalysisResponse)
async def analyze_text_endpoint(request: TextAnalysisRequest) -> AnalysisResponse:
    """Анализ текстового описания конкурента."""
    logger.info("POST /analyzetext — %d символов", len(request.text))

    try:
        analysis = analyze_competitor_text(request.text)
        preview = request.text[:100] + ("..." if len(request.text) > 100 else "")
        history_id, _ = _save_analysis_cache(
            analysis_type="text",
            source=preview,
            analysis=analysis,
        )

        return AnalysisResponse(
            success=True,
            analysis=analysis,
            history_id=history_id,
        )

    except ValueError as exc:
        logger.error("Ошибка валидации текста: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Ошибка анализа текста: %s", exc)
        return AnalysisResponse(success=False, error=str(exc))


@app.post("/parsedemo", response_model=AnalysisResponse)
async def parse_demo_endpoint(request: ParseDemoRequest) -> AnalysisResponse:
    """Парсинг URL через Selenium и AI-анализ результата."""
    logger.info("POST /parsedemo — URL: %s", request.url)

    try:
        parse_result = parse_competitor_website(request.url)

        text_for_analysis = (
            f"URL: {parse_result['url']}\n"
            f"Заголовок: {parse_result['title']}\n\n"
            f"Текст страницы:\n{parse_result['page_text'][:4000]}"
        )
        analysis = analyze_competitor_text(text_for_analysis)

        history_id, _ = _save_analysis_cache(
            analysis_type="parse",
            source=parse_result["url"],
            analysis=analysis,
            screenshot_path=parse_result["screenshot_path"],
        )

        return AnalysisResponse(
            success=True,
            analysis=analysis,
            history_id=history_id,
            screenshot_path=parse_result["screenshot_path"],
            page_title=parse_result["title"],
        )

    except ValueError as exc:
        logger.error("Некорректный URL: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TimeoutError as exc:
        logger.error("Таймаут парсинга: %s", exc)
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("Ошибка парсинга: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Неожиданная ошибка parsedemo: %s", exc)
        return AnalysisResponse(success=False, error=str(exc))


@app.get("/history", response_model=HistoryResponse)
async def get_history() -> HistoryResponse:
    """Получение всех предыдущих анализов из data/history.json."""
    logger.info("GET /history")

    try:
        raw_history = _load_history()
        items = [HistoryEntry(**item) for item in raw_history]
        return HistoryResponse(items=items, total=len(items))
    except Exception as exc:
        logger.exception("Ошибка чтения истории: %s", exc)
        raise HTTPException(status_code=500, detail="Ошибка чтения истории") from exc


if __name__ == "__main__":
    uvicorn.run("main:app", host=API_BIND_HOST, port=API_PORT, reload=True)
