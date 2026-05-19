"""
INP Merge page for Abaqus Toolkit.
Provides file selection, merge execution, and real-time log output.
"""

import asyncio
import logging
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QObject, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QPlainTextEdit,
    QGroupBox, QFileDialog, QMessageBox, QSizePolicy,
)

from core.merge_engine import MergeEngine
from core.models import MergeResult

logger = logging.getLogger(__name__)


class _MergeWorker(QObject):
    """Worker object for running merge in QThreadPool."""
    finished = Signal(object)   # MergeResult
    log_signal = Signal(str)    # log line

    def __init__(self, file1: str, file2: str, output: str):
        super().__init__()
        self._file1 = file1
        self._file2 = file2
        self._output = output

    def run(self):
        engine = MergeEngine(log_callback=lambda msg: self.log_signal.emit(msg))
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            engine.merge(self._file1, self._file2, self._output)
        )
        loop.close()
        self.finished.emit(result)


class MergePage(QWidget):
    """INP file merge page with file selection, execute button, and log output."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MergePage")

        self._file1_edit: QLineEdit = None
        self._file2_edit: QLineEdit = None
        self._output_edit: QLineEdit = None
        self._merge_btn: QPushButton = None
        self._log_area: QPlainTextEdit = None
        self._status_label: QLabel = None
        self._worker: _MergeWorker | None = None

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 16)
        layout.setSpacing(12)

        # --- Header ---
        title = QLabel("INP 文件合并")
        title.setProperty("heading", True)
        layout.addWidget(title)

        desc = QLabel("将两个 INP 文件合并为一个，自动处理节点和单元编号冲突。")
        desc.setProperty("subtitle", True)
        desc.setWordWrap(True)
        desc.setContentsMargins(0, 0, 0, 16)
        layout.addWidget(desc)

        # --- File Selection Card ---
        file_card = QGroupBox("文件选择")
        card_layout = QGridLayout(file_card)
        card_layout.setVerticalSpacing(10)
        card_layout.setHorizontalSpacing(12)

        # Job-1
        card_layout.addWidget(QLabel("Job-1（主文件）："), 0, 0)
        self._file1_edit = QLineEdit()
        self._file1_edit.setPlaceholderText("选择主 INP 文件...")
        card_layout.addWidget(self._file1_edit, 0, 1)
        btn1 = QPushButton("浏览")
        btn1.clicked.connect(self._browse_file1)
        card_layout.addWidget(btn1, 0, 2)

        # Job-2
        card_layout.addWidget(QLabel("Job-2（次文件）："), 1, 0)
        self._file2_edit = QLineEdit()
        self._file2_edit.setPlaceholderText("选择次要 INP 文件...")
        card_layout.addWidget(self._file2_edit, 1, 1)
        btn2 = QPushButton("浏览")
        btn2.clicked.connect(self._browse_file2)
        card_layout.addWidget(btn2, 1, 2)

        # Output
        card_layout.addWidget(QLabel("输出文件："), 2, 0)
        self._output_edit = QLineEdit()
        self._output_edit.setText("Job-Merged.inp")
        card_layout.addWidget(self._output_edit, 2, 1)
        btn_out = QPushButton("浏览")
        btn_out.clicked.connect(self._browse_output)
        card_layout.addWidget(btn_out, 2, 2)

        layout.addWidget(file_card)

        # --- Merge Button ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._merge_btn = QPushButton("开始合并")
        self._merge_btn.setMinimumWidth(140)
        self._merge_btn.setMinimumHeight(36)
        self._merge_btn.clicked.connect(self._on_merge)
        btn_row.addWidget(self._merge_btn)
        layout.addLayout(btn_row)

        # --- Log Area ---
        self._log_area = QPlainTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setMaximumBlockCount(5000)
        self._log_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._log_area)

        # --- Status Label ---
        self._status_label = QLabel("就绪")
        self._status_label.setStyleSheet("color: #666; font-size: 12px; padding: 4px 0;")
        layout.addWidget(self._status_label)

    # ---- File Choosers ----

    def _browse_file1(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Job-1 INP 文件", "",
            "INP 文件 (*.inp);;所有文件 (*.*)"
        )
        if path:
            self._file1_edit.setText(path)

    def _browse_file2(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Job-2 INP 文件", "",
            "INP 文件 (*.inp);;所有文件 (*.*)"
        )
        if path:
            self._file2_edit.setText(path)

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "选择输出文件", "Job-Merged.inp",
            "INP 文件 (*.inp);;所有文件 (*.*)"
        )
        if path:
            self._output_edit.setText(path)

    # ---- Merge Logic ----

    def _on_merge(self):
        f1 = self._file1_edit.text().strip()
        f2 = self._file2_edit.text().strip()
        out = self._output_edit.text().strip()

        if not f1 or not f2:
            QMessageBox.warning(self, "提示", "请选择两个输入文件。")
            return

        if not out:
            QMessageBox.warning(self, "提示", "请指定输出文件路径。")
            return

        # Validate input files exist
        if not Path(f1).exists():
            QMessageBox.critical(self, "错误", f"文件不存在:\n{f1}")
            return
        if not Path(f2).exists():
            QMessageBox.critical(self, "错误", f"文件不存在:\n{f2}")
            return

        self._merge_btn.setEnabled(False)
        self._merge_btn.setText("合并中...")
        self._status_label.setText("正在合并...")
        self._log_area.clear()

        self._worker = _MergeWorker(f1, f2, out)
        self._worker.log_signal.connect(self._on_log)
        self._worker.finished.connect(self._on_finished)
        QThreadPool.globalInstance().start(self._worker.run)

    def _on_log(self, msg: str):
        self._log_area.appendPlainText(msg)
        # Auto-scroll to bottom
        scrollbar = self._log_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_finished(self, result: MergeResult):
        self._merge_btn.setEnabled(True)
        self._merge_btn.setText("开始合并")
        if result.success:
            self._status_label.setText(f"✅ 合并完成 → {result.output_path}")
            logger.info("Merge successful: %s", result.output_path)
        else:
            self._status_label.setText(f"❌ 合并失败: {result.message}")
            logger.error("Merge failed: %s", result.message)
