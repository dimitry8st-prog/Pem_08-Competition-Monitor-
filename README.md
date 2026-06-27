# Competition Monitor

Desktop-приложение для конкурентного анализа в нише веб-дизайна и анимаций. Использует FastAPI-бэкенд, OpenAI GPT-4 Vision для анализа скриншотов, Selenium для парсинга сайтов и PyQt6 для графического интерфейса.

## Установка

```bash
pip install -r requirements.txt
```

Требуется установленный **Google Chrome** (для Selenium WebDriver).

## Настройка .env

Скопируйте пример конфигурации и укажите ключ API:

```bash
cp .env.example .env
```

Параметры в `.env`:

| Переменная | Описание |
|---|---|
| `OPENAI_API_KEY` | Ключ OpenAI API |
| `OPENAI_BASE_URL` | Базовый URL API (для прокси-сервисов) |
| `PROXY_API_KEY` | Опциональный ключ прокси API |
| `SELENIUM_TIMEOUT` | Таймаут загрузки страницы (сек) |
| `HEADLESS_MODE` | Headless-режим браузера (`True`/`False`) |

## Запуск

### Только бэкенд (API)

```bash
uvicorn main:app --reload
```

Документация API: http://127.0.0.1:8000/docs

### GUI-приложение (бэкенд стартует автоматически)

```bash
python build.py
```

### Сборка exe

```bash
pyinstaller --onefile --windowed build.py
```

## Использование

### Анализ скриншота

1. Запустите `python build.py`
2. Нажмите **«Загрузить скриншот»**
3. Выберите PNG/JPG из папки `data/` или загрузите свой файл
4. AI оценит дизайн, анимационный потенциал, UI-элементы и даст рекомендации

### Парсинг сайта конкурента

1. Введите URL в поле ввода (например, `https://www.awwwards.com/`)
2. Нажмите **«Парсить сайт»**
3. Selenium сделает скриншот, извлечёт текст и отправит на AI-анализ
4. Результаты сохраняются в `data/history.json`

### Просмотр истории

Нажмите **«Показать историю»** — отобразятся все предыдущие анализы с оценками и рекомендациями.

## API-эндпоинты

| Метод | Путь | Описание |
|---|---|---|
| `POST` | `/analyzeimage` | Анализ изображения (multipart file) |
| `POST` | `/analyzetext` | Анализ текстового описания (`{"text": "..."}`) |
| `POST` | `/parsedemo` | Парсинг URL + анализ (`{"url": "..."}`) |
| `GET` | `/history` | История всех анализов |

## Структура проекта

```
├── main.py              # FastAPI-бэкенд
├── openaiservice.py     # Интеграция OpenAI
├── parsingservice.py    # Selenium-парсинг
├── config.py            # Конфигурация и список конкурентов
├── build.py             # PyQt6 GUI
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── data/                # Скриншоты, кэш анализов, history.json
```

## Ниша: веб-дизайн и анимации

Все AI-промпты настроены на оценку:

- Визуальной согласованности и современных трендов
- Анимаций (микро-взаимодействия, переходы, скролл-эффекты)
- UX/UI паттернов и удобства использования
- Цветовых схем и типографики
- Дизайна компонентов и адаптивной вёрстки

## Примеры curl

```bash
# Анализ изображения
curl -X POST http://127.0.0.1:8000/analyzeimage -F "file=@data/screenshot.png"

# Анализ текста
curl -X POST http://127.0.0.1:8000/analyzetext \
  -H "Content-Type: application/json" \
  -d '{"text": "Современный лендинг с плавными анимациями при скролле..."}'

# Парсинг сайта
curl -X POST http://127.0.0.1:8000/parsedemo \
  -H "Content-Type: application/json" \
  -d '{"url": "https://lottiefiles.com/"}'

# История
curl http://127.0.0.1:8000/history
```
