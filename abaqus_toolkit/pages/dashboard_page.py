"""
Dashboard welcome page for Abaqus Toolkit.
Displays app branding and quick-action cards.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGroupBox, QSpacerItem, QSizePolicy,
)


class DashboardPage(QWidget):
    """Welcome dashboard with quick-action navigation cards."""

    page_change_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("DashboardPage")
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignCenter)

        # --- Icon ---
        icon_label = QLabel("🏠")
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("font-size: 48px; margin-bottom: 8px;")
        outer.addWidget(icon_label)

        # --- Title ---
        title = QLabel("欢迎使用 Abaqus 工具包")
        title.setProperty("heading", True)
        title.setAlignment(Qt.AlignCenter)
        outer.addWidget(title)

        # --- Subtitle ---
        subtitle = QLabel("Abaqus INP 文件管理专业工具集")
        subtitle.setProperty("subtitle", True)
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setContentsMargins(0, 8, 0, 24)
        outer.addWidget(subtitle)

        # --- Quick Actions Card ---
        card = QGroupBox("快捷操作")
        card.setFixedWidth(420)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(6)

        actions = [
            ("🔗  INP 合并", "将两个 INP 文件合并为一个，自动处理节点/单元编号冲突", 1),
        ]

        for label, desc, target in actions:
            btn = QPushButton(f"{label}\n{desc}")
            btn.setObjectName("cardBtn")
            btn.setMinimumHeight(52)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton#cardBtn {
                    background-color: #FFFFFF;
                    border: 1px solid #E8E8E8;
                    border-radius: 8px;
                    padding: 10px 16px;
                    text-align: left;
                    font-size: 13px;
                    color: #333333;
                }
                QPushButton#cardBtn:hover {
                    border-color: #0078D4;
                    background-color: #EFF6FC;
                }
            """)
            if target > 0:
                btn.clicked.connect(lambda checked, t=target: self.page_change_requested.emit(t))
            card_layout.addWidget(btn)

        outer.addWidget(card, alignment=Qt.AlignCenter)

        # --- Bottom spacer ---
        outer.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))
