"""
Abaqus Toolkit — Main Application Entry Point.
PySide6-based desktop application for Abaqus INP file batch processing.

Usage:
    python main.py
"""

import sys
sys.path.insert(0, r"C:\tmp\pyside6")

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QSplitter,
    QListWidget, QListWidgetItem, QStackedWidget,
    QLabel, QStatusBar, QSizePolicy,
)

from pages.dashboard_page import DashboardPage
from pages.merge_page import MergePage


def setup_logging():
    """Initialize logging to console and file."""
    log_dir = Path.home() / "AppData" / "Local" / "AbaqusToolkit" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                log_dir / "abaqus-toolkit.log",
                encoding="utf-8",
            ),
        ],
    )

    logger = logging.getLogger(__name__)
    logger.info("Abaqus Toolkit logging initialized")


def load_stylesheet(app: QApplication) -> None:
    """Load and apply QSS stylesheet from resources."""
    # Try multiple paths (development vs packaged)
    style_paths = [
        Path(__file__).parent / "resources" / "style.qss",
        Path(sys._MEIPASS) / "resources" / "style.qss" if hasattr(sys, "_MEIPASS") else None,
    ]
    for sp in style_paths:
        if sp and sp.exists():
            try:
                app.setStyleSheet(sp.read_text(encoding="utf-8"))
                logging.getLogger(__name__).info("Stylesheet loaded: %s", sp)
                return
            except Exception as e:
                logging.getLogger(__name__).warning("Failed to load stylesheet %s: %s", sp, e)

    logging.getLogger(__name__).warning("No stylesheet loaded — using system defaults")


class MainWindow(QMainWindow):
    """Main application window with sidebar navigation and stacked pages."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Abaqus 工具包")
        self.resize(1200, 800)
        self.setMinimumSize(900, 600)

        # Center on screen
        screen = QApplication.primaryScreen()
        if screen:
            center = screen.availableGeometry().center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)

        self._nav_list: QListWidget = None
        self._pages: QStackedWidget = None
        self._status: QStatusBar = None

        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- Left Navigation Sidebar ----
        self._nav_list = QListWidget()
        self._nav_list.setFocusPolicy(Qt.NoFocus)

        nav_items = [
            ("📊  首页", 0),
            ("🔗  INP 合并", 1),
        ]

        for label, data in nav_items:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, data)
            self._nav_list.addItem(item)

        # Header above nav
        nav_wrapper = QWidget()
        nav_wrapper.setFixedWidth(220)
        nav_wrapper.setStyleSheet("background-color: #FFFFFF; border-right: 1px solid #E0E0E0;")
        nav_layout = QVBoxLayout(nav_wrapper)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)

        app_title = QLabel("Abaqus 工具包")
        app_title.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #0078D4; "
            "padding: 20px 16px 12px 16px; background: transparent;"
        )
        app_title.setFixedHeight(52)
        nav_layout.addWidget(app_title)
        nav_layout.addWidget(self._nav_list)

        # ---- Right Content Area ----
        self._pages = QStackedWidget()

        self._dashboard_page = DashboardPage()
        self._merge_page = MergePage()

        self._pages.addWidget(self._dashboard_page)  # index 0
        self._pages.addWidget(self._merge_page)       # index 1

        # Connect navigation
        self._nav_list.currentRowChanged.connect(self._pages.setCurrentIndex)
        self._dashboard_page.page_change_requested.connect(self._nav_list.setCurrentRow)

        # Select first item by default
        self._nav_list.setCurrentRow(0)

        # ---- Layout ----
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(nav_wrapper)
        splitter.addWidget(self._pages)
        splitter.setStretchFactor(0, 0)  # nav fixed
        splitter.setStretchFactor(1, 1)  # content expands
        splitter.setHandleWidth(0)

        root.addWidget(splitter)

        # ---- Status Bar ----
        self._status = QStatusBar()
        self._status.showMessage("就绪")
        self.setStatusBar(self._status)


def main():
    setup_logging()
    logger = logging.getLogger(__name__)

    app = QApplication(sys.argv)
    app.setApplicationName("AbaqusToolkit")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("AbaqusToolkit")

    load_stylesheet(app)

    logger.info("Starting Abaqus Toolkit...")
    window = MainWindow()
    window.show()
    logger.info("Main window displayed")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
