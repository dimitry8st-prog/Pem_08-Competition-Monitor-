"""PyQt6 GUI для приложения Competition Monitor."""

import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import API_BASE_URL, API_BIND_HOST, API_PORT, COMPETITORS, DATA_DIR

logger = logging.getLogger(__name__)

BACKEND_STARTUP_TIMEOUT: int = 40

# Цветовая палитра
COLORS = {
    "bg": "#0f1117",
    "surface": "#1a1d27",
    "surface2": "#232736",
    "border": "#2e3348",
    "text": "#e8eaf0",
    "muted": "#8b92a8",
    "accent": "#6366f1",
    "accent_hover": "#818cf8",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "danger": "#ef4444",
    "parse": "#0ea5e9",
    "history": "#a855f7",
}

GLOBAL_STYLE = f"""
QMainWindow {{
    background-color: {COLORS['bg']};
}}
QWidget {{
    color: {COLORS['text']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: {COLORS['surface']};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {COLORS['border']};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLORS['accent']};
}}
QStatusBar {{
    background: {COLORS['surface']};
    color: {COLORS['muted']};
    border-top: 1px solid {COLORS['border']};
    padding: 4px 12px;
}}
QLineEdit {{
    background: {COLORS['surface2']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    padding: 12px 16px;
    color: {COLORS['text']};
    font-size: 14px;
}}
QLineEdit:focus {{
    border: 1px solid {COLORS['accent']};
}}
QTextEdit {{
    background: {COLORS['surface2']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    padding: 10px;
    color: {COLORS['muted']};
    font-family: 'Consolas', monospace;
    font-size: 11px;
}}
"""


def _score_color(score: int) -> str:
    """Цвет бейджа оценки в зависимости от балла."""
    if score >= 8:
        return COLORS["success"]
    if score >= 5:
        return COLORS["warning"]
    return COLORS["danger"]


def _animation_label(value: str) -> str:
    """Человекочитаемая метка анимационного потенциала."""
    labels = {"low": "Низкий", "medium": "Средний", "high": "Высокий"}
    return labels.get(value, value)


class ApiWorker(QThread):
    """Фоновый поток для HTTP-запросов к API."""

    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
        file_path: str | None = None,
    ) -> None:
        super().__init__()
        self.method = method
        self.endpoint = endpoint
        self.json_data = json_data
        self.file_path = file_path

    def run(self) -> None:
        """Выполнение HTTP-запроса."""
        try:
            with httpx.Client(timeout=120.0) as client:
                url = f"{API_BASE_URL}{self.endpoint}"

                if self.method == "GET":
                    response = client.get(url)
                elif self.method == "POST" and self.file_path:
                    path = Path(self.file_path)
                    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
                    with path.open("rb") as file_handle:
                        response = client.post(
                            url,
                            files={"file": (path.name, file_handle, mime)},
                        )
                elif self.method == "POST":
                    response = client.post(url, json=self.json_data)
                else:
                    self.error.emit(f"Неизвестный метод: {self.method}")
                    return

                response.raise_for_status()
                self.finished.emit(response.json())

        except httpx.ConnectError:
            self.error.emit(
                f"Не удалось подключиться к API ({API_BASE_URL}). "
                "Перезапустите приложение или выполните: uvicorn main:app --reload"
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            self.error.emit(f"HTTP {exc.response.status_code}: {detail}")
        except Exception as exc:
            self.error.emit(str(exc))


class ScoreBadge(QLabel):
    """Круглый бейдж с оценкой дизайна."""

    def __init__(self, score: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        color = _score_color(score)
        self.setFixedSize(64, 64)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(f"{score}")
        self.setStyleSheet(
            f"background: {color}; color: white; border-radius: 32px; "
            f"font-size: 22px; font-weight: bold;"
        )


class AnalysisCard(QFrame):
    """Карточка отображения результата анализа."""

    def __init__(self, data: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("analysisCard")
        self.setStyleSheet(
            f"#analysisCard {{ background: {COLORS['surface']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 14px; }}"
        )

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(Qt.GlobalColor.black)
        self.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(14)

        analysis = data.get("analysis", data)
        if isinstance(analysis, dict) and "analysis" in analysis:
            analysis = analysis["analysis"]

        # Верхняя строка: оценка + метаданные
        top = QHBoxLayout()
        score = int(analysis.get("design_score", 0))
        top.addWidget(ScoreBadge(score))

        meta = QVBoxLayout()
        source = (
            data.get("source")
            or data.get("page_title")
            or Path(str(data.get("screenshot_path", ""))).name
            or "Анализ"
        )
        title_lbl = QLabel(str(source))
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: bold; color: {COLORS['text']};"
        )
        meta.addWidget(title_lbl)

        animation = analysis.get("animation_potential", "medium")
        anim_color = COLORS["success"] if animation == "high" else (
            COLORS["warning"] if animation == "medium" else COLORS["muted"]
        )
        anim_lbl = QLabel(
            f"Анимации: <span style='color:{anim_color}; font-weight:bold;'>"
            f"{_animation_label(animation)}</span>"
        )
        anim_lbl.setStyleSheet(f"color: {COLORS['muted']};")
        meta.addWidget(anim_lbl)
        top.addLayout(meta, stretch=1)
        outer.addLayout(top)

        # Цветовая схема
        colors = analysis.get("color_scheme", "")
        if colors:
            color_block = QLabel(f"🎨  {colors}")
            color_block.setWordWrap(True)
            color_block.setStyleSheet(
                f"background: {COLORS['surface2']}; border-radius: 8px; "
                f"padding: 10px; color: {COLORS['text']};"
            )
            outer.addWidget(color_block)

        # Списки
        for icon, label, key in [
            ("🧩", "UI-элементы", "ui_elements"),
            ("✅", "Сильные стороны", "strengths"),
            ("⚠️", "Слабые стороны", "weaknesses"),
            ("💡", "Рекомендации", "recommendations"),
        ]:
            items = analysis.get(key, [])
            if items:
                section = QLabel(
                    f"<b style='color:{COLORS['accent']};'>{icon} {label}</b><br>"
                    + "<br>".join(
                        f"<span style='color:{COLORS['text']};'>• {item}</span>"
                        for item in items
                    )
                )
                section.setWordWrap(True)
                section.setStyleSheet(
                    f"background: {COLORS['surface2']}; border-radius: 8px; padding: 10px;"
                )
                outer.addWidget(section)


class StyledButton(QPushButton):
    """Стилизованная кнопка с цветом акцента."""

    def __init__(self, text: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._color = color
        self._hover = COLORS["accent_hover"] if color == COLORS["accent"] else color
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(46)
        self._apply_style(enabled=True)

    def _apply_style(self, enabled: bool) -> None:
        if enabled:
            self.setStyleSheet(
                f"QPushButton {{ background: {self._color}; color: white; border: none; "
                f"border-radius: 10px; font-weight: bold; font-size: 13px; padding: 0 20px; }}"
                f"QPushButton:hover {{ background: {self._hover}; }}"
            )
        else:
            self.setStyleSheet(
                f"QPushButton {{ background: {COLORS['border']}; color: {COLORS['muted']}; "
                f"border: none; border-radius: 10px; font-weight: bold; font-size: 13px; }}"
            )

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)
        self._apply_style(enabled)


class CompetitionMonitorWindow(QMainWindow):
    """Главное окно приложения."""

    def __init__(self) -> None:
        super().__init__()
        self.backend_process: subprocess.Popen | None = None
        self.worker: ApiWorker | None = None
        self._backend_started_by_us = False
        self._init_ui()
        self._start_backend()

    def _init_ui(self) -> None:
        """Инициализация интерфейса."""
        self.setWindowTitle("Competition Monitor")
        self.setMinimumSize(1000, 720)
        self.setStyleSheet(GLOBAL_STYLE)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Шапка ──
        header = QWidget()
        header.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {COLORS['accent']}, stop:1 #8b5cf6);"
        )
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(28, 24, 28, 24)

        title = QLabel("Competition Monitor")
        title_font = QFont("Segoe UI", 22)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: white; background: transparent;")
        header_layout.addWidget(title)

        subtitle = QLabel("AI-анализ конкурентов в нише веб-дизайна и анимаций")
        subtitle.setStyleSheet("color: rgba(255,255,255,0.8); background: transparent; font-size: 13px;")
        header_layout.addWidget(subtitle)

        # Индикатор подключения
        conn_row = QHBoxLayout()
        self.conn_dot = QLabel("●")
        self.conn_dot.setStyleSheet("color: #fbbf24; font-size: 14px; background: transparent;")
        self.conn_label = QLabel("Подключение к API...")
        self.conn_label.setStyleSheet("color: rgba(255,255,255,0.7); background: transparent; font-size: 12px;")
        conn_row.addWidget(self.conn_dot)
        conn_row.addWidget(self.conn_label)
        conn_row.addStretch()
        header_layout.addLayout(conn_row)
        root.addWidget(header)

        # ── Основной контент ──
        body = QWidget()
        body.setStyleSheet(f"background: {COLORS['bg']};")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(28, 24, 28, 24)
        body_layout.setSpacing(16)

        # URL
        url_label = QLabel("URL конкурента")
        url_label.setStyleSheet(f"color: {COLORS['muted']}; font-weight: bold; font-size: 12px;")
        body_layout.addWidget(url_label)

        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.awwwards.com/")
        self.url_input.returnPressed.connect(self._on_parse_website)
        url_row.addWidget(self.url_input)
        body_layout.addLayout(url_row)

        # Быстрый выбор конкурентов
        chips_label = QLabel("Быстрый выбор")
        chips_label.setStyleSheet(f"color: {COLORS['muted']}; font-size: 11px;")
        body_layout.addWidget(chips_label)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)
        for comp in COMPETITORS[:5]:
            chip = QPushButton(comp["name"])
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(
                f"QPushButton {{ background: {COLORS['surface2']}; color: {COLORS['text']}; "
                f"border: 1px solid {COLORS['border']}; border-radius: 16px; "
                f"padding: 4px 14px; font-size: 12px; }}"
                f"QPushButton:hover {{ border-color: {COLORS['accent']}; color: {COLORS['accent']}; }}"
            )
            chip.clicked.connect(lambda _, u=comp["url"]: self.url_input.setText(u))
            chips_row.addWidget(chip)
        chips_row.addStretch()
        body_layout.addLayout(chips_row)

        # Кнопки
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.btn_screenshot = StyledButton("📷  Загрузить скриншот", COLORS["accent"])
        self.btn_screenshot.clicked.connect(self._on_load_screenshot)
        self.btn_parse = StyledButton("🌐  Парсить сайт", COLORS["parse"])
        self.btn_parse.clicked.connect(self._on_parse_website)
        self.btn_history = StyledButton("📋  История", COLORS["history"])
        self.btn_history.clicked.connect(self._on_show_history)
        btn_row.addWidget(self.btn_screenshot)
        btn_row.addWidget(self.btn_parse)
        btn_row.addWidget(self.btn_history)
        body_layout.addLayout(btn_row)

        # Результаты
        results_label = QLabel("Результаты анализа")
        results_label.setStyleSheet(f"color: {COLORS['muted']}; font-weight: bold; font-size: 12px;")
        body_layout.addWidget(results_label)

        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setStyleSheet("background: transparent;")
        self.results_container = QWidget()
        self.results_container.setStyleSheet("background: transparent;")
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setSpacing(12)

        self._show_empty_state()
        self.results_layout.addStretch()
        self.results_scroll.setWidget(self.results_container)
        body_layout.addWidget(self.results_scroll, stretch=1)

        self.raw_output = QTextEdit()
        self.raw_output.setReadOnly(True)
        self.raw_output.setMaximumHeight(120)
        self.raw_output.setPlaceholderText("JSON-ответ API появится здесь...")
        body_layout.addWidget(self.raw_output)

        root.addWidget(body, stretch=1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Запуск бэкенда...")
        self._set_buttons_enabled(False)

    def _show_empty_state(self) -> None:
        """Плейсхолдер при отсутствии результатов."""
        empty = QLabel(
            "Загрузите скриншот или введите URL конкурента,\n"
            "чтобы получить AI-анализ дизайна и анимаций"
        )
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setObjectName("emptyState")
        empty.setStyleSheet(
            f"#emptyState {{ color: {COLORS['muted']}; font-size: 14px; "
            f"padding: 40px; border: 2px dashed {COLORS['border']}; "
            f"border-radius: 14px; background: {COLORS['surface']}; }}"
        )
        self.results_layout.insertWidget(0, empty)

    def _set_connection_status(self, connected: bool, message: str) -> None:
        """Обновление индикатора подключения."""
        color = COLORS["success"] if connected else COLORS["danger"]
        self.conn_dot.setStyleSheet(f"color: {color}; font-size: 14px; background: transparent;")
        self.conn_label.setText(message)
        self.conn_label.setStyleSheet(
            f"color: rgba(255,255,255,0.85); background: transparent; font-size: 12px;"
        )

    def _is_backend_alive(self) -> bool:
        """Проверка доступности API."""
        try:
            response = httpx.get(f"{API_BASE_URL}/health", timeout=2.0)
            return response.status_code == 200
        except httpx.RequestError:
            return False

    def _start_backend(self) -> None:
        """Запуск или подключение к FastAPI-бэкенду."""
        if self._is_backend_alive():
            logger.info("Бэкенд уже запущен на %s", API_BASE_URL)
            self._set_connection_status(True, f"API: {API_BASE_URL}")
            self.status_bar.showMessage(f"Подключено к {API_BASE_URL}")
            self._set_buttons_enabled(True)
            return

        try:
            creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self.backend_process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "main:app",
                    "--host",
                    API_BIND_HOST,
                    "--port",
                    str(API_PORT),
                ],
                cwd=str(Path(__file__).resolve().parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
            )
            self._backend_started_by_us = True
            logger.info("Бэкенд запущен (PID %s)", self.backend_process.pid)
            self._wait_for_backend()
        except Exception as exc:
            logger.error("Ошибка запуска бэкенда: %s", exc)
            self._set_connection_status(False, "Ошибка запуска API")
            self.status_bar.showMessage(f"Ошибка: {exc}")

    def _wait_for_backend(self) -> None:
        """Ожидание готовности API."""
        for i in range(BACKEND_STARTUP_TIMEOUT):
            if self._is_backend_alive():
                self._set_connection_status(True, f"API: {API_BASE_URL}")
                self.status_bar.showMessage(f"Подключено к {API_BASE_URL}")
                self._set_buttons_enabled(True)
                return
            self.status_bar.showMessage(f"Ожидание бэкенда... ({i + 1}/{BACKEND_STARTUP_TIMEOUT})")
            time.sleep(1)

        self._set_connection_status(False, "API недоступен")
        self.status_bar.showMessage("Бэкенд не отвечает — запустите: uvicorn main:app --reload")
        self._set_buttons_enabled(False)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        """Включение/отключение кнопок."""
        self.btn_screenshot.setEnabled(enabled)
        self.btn_parse.setEnabled(enabled)
        self.btn_history.setEnabled(enabled)

    def _clear_results(self) -> None:
        """Очистка области результатов."""
        while self.results_layout.count() > 1:
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _display_analysis(self, data: dict[str, Any]) -> None:
        """Отображение результата анализа."""
        self._clear_results()
        self.raw_output.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))

        if data.get("success") and data.get("analysis"):
            source = data.get("page_title") or data.get("screenshot_path") or ""
            card_data = {**data, "source": source}
            self.results_layout.insertWidget(0, AnalysisCard(card_data))
        elif not data.get("success"):
            error = data.get("error", "Неизвестная ошибка")
            err_lbl = QLabel(f"⚠️  {error}")
            err_lbl.setWordWrap(True)
            err_lbl.setStyleSheet(
                f"color: {COLORS['danger']}; background: {COLORS['surface']}; "
                f"border: 1px solid {COLORS['danger']}; border-radius: 10px; padding: 16px;"
            )
            self.results_layout.insertWidget(0, err_lbl)
        else:
            self._show_empty_state()

    def _set_busy(self, message: str) -> None:
        """Установка состояния загрузки."""
        self._set_buttons_enabled(False)
        self.status_bar.showMessage(message)

    def _set_ready(self, message: str = "Готово") -> None:
        """Снятие состояния загрузки."""
        if self._is_backend_alive():
            self._set_buttons_enabled(True)
        self.status_bar.showMessage(message)

    def _on_load_screenshot(self) -> None:
        """Обработчик кнопки загрузки скриншота."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите скриншот",
            str(DATA_DIR),
            "Изображения (*.png *.jpg *.jpeg *.gif *.webp)",
        )
        if not file_path:
            return

        self._set_busy(f"Анализ изображения: {Path(file_path).name}...")
        self.worker = ApiWorker("POST", "/analyzeimage", file_path=file_path)
        self.worker.finished.connect(self._on_analysis_done)
        self.worker.error.connect(self._on_worker_error)
        self.worker.start()

    def _on_parse_website(self) -> None:
        """Обработчик кнопки парсинга сайта."""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Внимание", "Введите URL конкурента.")
            return

        self._set_busy(f"Парсинг и анализ: {url}...")
        self.worker = ApiWorker("POST", "/parsedemo", json_data={"url": url})
        self.worker.finished.connect(self._on_analysis_done)
        self.worker.error.connect(self._on_worker_error)
        self.worker.start()

    def _on_show_history(self) -> None:
        """Обработчик кнопки показа истории."""
        self._set_busy("Загрузка истории...")
        self.worker = ApiWorker("GET", "/history")
        self.worker.finished.connect(self._on_history_done)
        self.worker.error.connect(self._on_worker_error)
        self.worker.start()

    def _on_analysis_done(self, data: dict[str, Any]) -> None:
        """Обработка завершения анализа."""
        self._display_analysis(data)
        self._set_ready("Анализ завершён")

    def _on_history_done(self, data: dict[str, Any]) -> None:
        """Отображение истории анализов."""
        self._clear_results()
        self.raw_output.setPlainText(json.dumps(data, ensure_ascii=False, indent=2))

        items = data.get("items", [])
        if not items:
            self._show_empty_state()
        else:
            for item in items:
                wrapper = QFrame()
                wrapper.setStyleSheet(
                    f"background: transparent; border: none;"
                )
                wl = QVBoxLayout(wrapper)
                wl.setSpacing(6)
                ts = item.get("timestamp", "")[:19].replace("T", " ")
                type_badge = QLabel(
                    f"<span style='background:{COLORS['accent']}; color:white; "
                    f"padding:2px 8px; border-radius:4px; font-size:11px;'>"
                    f"{item.get('analysis_type', '').upper()}</span>"
                    f"&nbsp;&nbsp;<span style='color:{COLORS['muted']};'>{ts}</span>"
                )
                wl.addWidget(type_badge)
                wl.addWidget(AnalysisCard(item))
                self.results_layout.insertWidget(0, wrapper)

        self._set_ready(f"Загружено записей: {data.get('total', 0)}")

    def _on_worker_error(self, error: str) -> None:
        """Обработка ошибки воркера."""
        self._clear_results()
        err_lbl = QLabel(f"⚠️  {error}")
        err_lbl.setWordWrap(True)
        err_lbl.setStyleSheet(
            f"color: {COLORS['danger']}; background: {COLORS['surface']}; "
            f"border: 1px solid {COLORS['danger']}; border-radius: 10px; padding: 16px;"
        )
        self.results_layout.insertWidget(0, err_lbl)
        self.raw_output.setPlainText(f"Ошибка: {error}")
        self._set_ready("Ошибка операции")

    def closeEvent(self, event) -> None:
        """Завершение бэкенда при закрытии окна."""
        if self._backend_started_by_us and self.backend_process:
            if self.backend_process.poll() is None:
                self.backend_process.terminate()
                try:
                    self.backend_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.backend_process.kill()
        event.accept()


def main() -> None:
    """Точка входа GUI-приложения."""
    logging.basicConfig(level=logging.INFO)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = CompetitionMonitorWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
