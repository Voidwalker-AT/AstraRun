"""Memory and Skill Management UI for AstraRun Learning Foundation.

Provides interactive inspection, verification, conflict resolution, and skill approval
surfaces built with PySide6 dark-theme widgets.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from astrarun.learning.memory import MemoryStore
from astrarun.learning.models import (
    MemoryNamespace,
    MemoryStatus,
    SemanticMemory,
    SkillCandidate,
    SkillStatus,
)
from astrarun.learning.skills import SkillManager


class MemoryDetailWidget(QFrame):
    """Panel displaying complete provenance and evidence references for a selected memory."""

    confirmed = Signal(str)  # memory_id
    rejected = Signal(str)   # memory_id
    deleted = Signal(str)    # memory_id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.current_memory: Optional[SemanticMemory] = None

        self.setStyleSheet("""
            MemoryDetailWidget {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        self.title_label = QLabel("Memory Details", self)
        self.title_label.setStyleSheet("color: #89b4fa; font-size: 14px; font-weight: bold;")
        header.addWidget(self.title_label)
        header.addStretch(1)

        self.btn_confirm = QPushButton("Confirm (Active)", self)
        self.btn_confirm.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold; padding: 4px 10px; border-radius: 4px;")
        self.btn_confirm.clicked.connect(self._on_confirm)
        header.addWidget(self.btn_confirm)

        self.btn_reject = QPushButton("Reject", self)
        self.btn_reject.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold; padding: 4px 10px; border-radius: 4px;")
        self.btn_reject.clicked.connect(self._on_reject)
        header.addWidget(self.btn_reject)

        self.btn_delete = QPushButton("Delete", self)
        self.btn_delete.setStyleSheet("background-color: #45475a; color: #cdd6f4; padding: 4px 10px; border-radius: 4px;")
        self.btn_delete.clicked.connect(self._on_delete)
        header.addWidget(self.btn_delete)

        layout.addLayout(header)

        # Meta properties
        self.meta_label = QLabel("", self)
        self.meta_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        layout.addWidget(self.meta_label)

        # Evidence scroll area
        ev_title = QLabel("Verifiable Provenance & Evidence Records:", self)
        ev_title.setStyleSheet("color: #cdd6f4; font-weight: bold; margin-top: 6px;")
        layout.addWidget(ev_title)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        self.evidence_container = QWidget()
        self.evidence_layout = QVBoxLayout(self.evidence_container)
        self.evidence_layout.setContentsMargins(0, 0, 0, 0)
        self.evidence_layout.setSpacing(6)
        scroll.setWidget(self.evidence_container)

        layout.addWidget(scroll, 1)

    def set_memory(self, memory: Optional[SemanticMemory]) -> None:
        self.current_memory = memory
        if not memory:
            self.title_label.setText("No Memory Selected")
            self.meta_label.setText("")
            self.btn_confirm.setEnabled(False)
            self.btn_reject.setEnabled(False)
            self.btn_delete.setEnabled(False)
            self._clear_evidence()
            return

        self.btn_confirm.setEnabled(True)
        self.btn_reject.setEnabled(True)
        self.btn_delete.setEnabled(True)

        self.title_label.setText(f"{memory.namespace.value}: '{memory.key}' ➔ '{memory.value}'")
        self.meta_label.setText(
            f"Status: {memory.status.value}  |  Confidence: {memory.confidence:.2f}  |  "
            f"Support: {memory.support_count}  |  Contradictions: {memory.contradiction_count}  |  "
            f"Pinned: {memory.pinned}  |  Confirmed: {memory.user_confirmed}"
        )

        self._clear_evidence()
        for idx, ref in enumerate(memory.evidence_refs, 1):
            row = QFrame()
            row.setStyleSheet("background-color: #262738; border-radius: 4px; padding: 6px;")
            r_lay = QVBoxLayout(row)
            r_lay.setContentsMargins(6, 6, 6, 6)

            t_lbl = QLabel(f"#{idx} [{ref.evidence_type.value}] - Weight: {ref.weight:.1f}")
            t_lbl.setStyleSheet("color: #cba6f7; font-weight: bold;")
            r_lay.addWidget(t_lbl)

            d_lbl = QLabel(f"Task ID: {ref.task_id[:12]}...  |  Event: {ref.event_id or 'N/A'}")
            d_lbl.setStyleSheet("color: #bac2de; font-size: 10px;")
            r_lay.addWidget(d_lbl)

            if ref.details:
                det_lbl = QLabel(f"Details: {ref.details}")
                det_lbl.setStyleSheet("color: #a6adc8; font-size: 10px;")
                det_lbl.setWordWrap(True)
                r_lay.addWidget(det_lbl)

            self.evidence_layout.addWidget(row)

        self.evidence_layout.addStretch(1)

    def _clear_evidence(self) -> None:
        while self.evidence_layout.count():
            item = self.evidence_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _on_confirm(self) -> None:
        if self.current_memory:
            self.confirmed.emit(self.current_memory.id)

    def _on_reject(self) -> None:
        if self.current_memory:
            self.rejected.emit(self.current_memory.id)

    def _on_delete(self) -> None:
        if self.current_memory:
            self.deleted.emit(self.current_memory.id)


class MemoryView(QWidget):
    """Main management widget displaying learned knowledge, aliases, preferences, and provenance."""

    def __init__(
        self,
        memory_store: Optional[MemoryStore] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.store = memory_store or MemoryStore()

        self.setWindowTitle("AstraRun Memory & Learning Inspector")
        self.resize(900, 550)
        self.setStyleSheet("background-color: #11111b; color: #cdd6f4;")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        # Top Bar: Search and Filters
        top_bar = QHBoxLayout()
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Search learned memories by key or value...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #313244;
                border-radius: 6px;
                padding: 6px 12px;
                font-size: 12px;
            }
        """)
        self.search_input.textChanged.connect(self.reload_memories)
        top_bar.addWidget(self.search_input, 1)

        self.btn_clear_all = QPushButton("Clear All Learning", self)
        self.btn_clear_all.setStyleSheet("background-color: #45475a; color: #f38ba8; padding: 6px 12px; border-radius: 6px;")
        self.btn_clear_all.clicked.connect(self._on_clear_all)
        top_bar.addWidget(self.btn_clear_all)

        root_layout.addLayout(top_bar)

        # Splitter: List on left, Details on right
        splitter = QSplitter(Qt.Horizontal, self)

        # Left list
        self.list_widget = QListWidget(self)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background-color: #313244;
            }
        """)
        self.list_widget.currentItemChanged.connect(self._on_item_selected)
        splitter.addWidget(self.list_widget)

        # Right details
        self.detail_widget = MemoryDetailWidget(self)
        self.detail_widget.confirmed.connect(self._handle_confirm)
        self.detail_widget.rejected.connect(self._handle_reject)
        self.detail_widget.deleted.connect(self._handle_delete)
        splitter.addWidget(self.detail_widget)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        root_layout.addWidget(splitter, 1)

        self.reload_memories()

    def reload_memories(self) -> None:
        """Fetch and populate list with memories matching search query."""
        self.list_widget.clear()
        query = self.search_input.text().strip().lower()

        memories = self.store.list_memories()
        for m in memories:
            if query and query not in m.key.lower() and query not in str(m.value).lower():
                continue

            item = QListWidgetItem()
            status_symbol = "[OK]" if m.status == MemoryStatus.ACTIVE else f"[{m.status.value[:4]}]"
            item.setText(f"{status_symbol} {m.namespace.value}: '{m.key}' ➔ '{m.value}' (Conf: {m.confidence:.2f})")
            item.setData(Qt.UserRole, m)

            # Color coding
            if m.status == MemoryStatus.ACTIVE:
                item.setForeground(QColor("#a6e3a1"))
            elif m.status == MemoryStatus.CONFLICTED:
                item.setForeground(QColor("#fab387"))
            elif m.status in {MemoryStatus.REJECTED, MemoryStatus.DEPRECATED}:
                item.setForeground(QColor("#6c7086"))
            else:
                item.setForeground(QColor("#cdd6f4"))

            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        else:
            self.detail_widget.set_memory(None)

    def _on_item_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if current:
            mem = current.data(Qt.UserRole)
            self.detail_widget.set_memory(mem)
        else:
            self.detail_widget.set_memory(None)

    def _handle_confirm(self, memory_id: str) -> None:
        self.store.confirm_memory(memory_id)
        self.reload_memories()

    def _handle_reject(self, memory_id: str) -> None:
        self.store.reject_memory(memory_id)
        self.reload_memories()

    def _handle_delete(self, memory_id: str) -> None:
        self.store.delete_memory(memory_id)
        self.reload_memories()

    def _on_clear_all(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Clear All Learning",
            "Are you sure you want to wipe all learned memories, aliases, and skills?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm == QMessageBox.Yes:
            self.store.persistence.clear_all_learning()
            self.reload_memories()


class SkillReviewWidget(QDialog):
    """
    Interactive modal dialog proposing recurring workflow patterns for user confirmation.
    """

    def __init__(
        self,
        skill: SkillCandidate,
        skill_manager: SkillManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.skill = skill
        self.skill_manager = skill_manager

        self.setWindowTitle(f"New Skill Proposed: {skill.name}")
        self.resize(600, 450)
        self.setStyleSheet("background-color: #181825; color: #cdd6f4;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Title
        t_lbl = QLabel(f"Skill Candidate: {skill.name}", self)
        t_lbl.setStyleSheet("color: #89b4fa; font-size: 16px; font-weight: bold;")
        layout.addWidget(t_lbl)

        d_lbl = QLabel(skill.description, self)
        d_lbl.setStyleSheet("color: #a6adc8; font-size: 12px;")
        layout.addWidget(d_lbl)

        # Stats
        stats_lbl = QLabel(
            f"Observed Occurrences: {skill.support_count}  |  "
            f"Confidence: {skill.confidence:.2f}  |  "
            f"Aggregate Risk: {skill.max_risk_level}",
            self
        )
        stats_lbl.setStyleSheet("color: #fab387; font-weight: bold;")
        layout.addWidget(stats_lbl)

        # Steps
        steps_title = QLabel("Workflow Steps:", self)
        steps_title.setStyleSheet("color: #cdd6f4; font-weight: bold; margin-top: 6px;")
        layout.addWidget(steps_title)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: 1px solid #313244; border-radius: 4px;")

        steps_widget = QWidget()
        steps_lay = QVBoxLayout(steps_widget)
        for s in skill.steps:
            row = QFrame()
            row.setStyleSheet("background-color: #1e1e2e; padding: 6px; border-radius: 4px; margin-bottom: 4px;")
            r_l = QHBoxLayout(row)
            r_l.addWidget(QLabel(f"Step {s.step_index}: {s.capability_id}"))
            r_l.addStretch(1)
            risk_badge = QLabel(f"[{s.risk_level}]")
            risk_color = "#f38ba8" if s.risk_level in {"HIGH", "CRITICAL"} else "#a6e3a1"
            risk_badge.setStyleSheet(f"color: {risk_color}; font-weight: bold;")
            r_l.addWidget(risk_badge)
            steps_lay.addWidget(row)

        steps_lay.addStretch(1)
        scroll.setWidget(steps_widget)
        layout.addWidget(scroll, 1)

        # Buttons
        btns = QHBoxLayout()
        btns.addStretch(1)

        btn_reject = QPushButton("Reject", self)
        btn_reject.setStyleSheet("background-color: #45475a; color: #f38ba8; padding: 6px 14px; border-radius: 4px;")
        btn_reject.clicked.connect(self._on_reject)
        btns.addWidget(btn_reject)

        btn_approve = QPushButton("Approve & Activate", self)
        btn_approve.setStyleSheet("background-color: #a6e3a1; color: #11111b; font-weight: bold; padding: 6px 14px; border-radius: 4px;")
        btn_approve.clicked.connect(self._on_approve)
        btns.addWidget(btn_approve)

        layout.addLayout(btns)

    def _on_approve(self) -> None:
        self.skill_manager.approve_skill(self.skill.id)
        self.accept()

    def _on_reject(self) -> None:
        self.skill_manager.reject_skill(self.skill.id)
        self.reject()
