"""
Beacon Table Widget

Displays the beacon inventory with sort/filter, batch selection,
a categorized right-click context menu with keyboard shortcuts,
status badges, row flash on check-in, and tooltips.
"""

import base64
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView,
    QPushButton, QMessageBox, QMenu, QLineEdit, QAbstractItemView,
)
from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QSortFilterProxyModel, QModelIndex,
    QAbstractTableModel,
)
from PyQt6.QtGui import QColor, QAction, QKeySequence

from gui.api_client import PandragonAPI
from gui.translations.manager import tr
from gui.dialogs.action_dialogs import (
    BOFExecDialog, ExecutePEDialog, InjectProcessDialog,
    ListFilesDialog, SleepDialog,
)
from gui.widgets.notification_overlay import NotificationOverlay


COLUMNS = [
    ("Name",      0),
    ("Beacon ID", 150),
    ("Status",    0),
    ("Last Seen", 0),
    ("Auth",      0),
    ("Queued",    0),
    ("Scheduled", 0),
    ("Pending",   0),
    ("Output",    0),
    ("Key Rotation", 0),
]

_COLUMN_KEYS = [
    "beacon_table.column_name",
    "beacon_table.column_beacon_id",
    "beacon_table.column_status",
    "beacon_table.column_last_seen",
    "beacon_table.column_auth",
    "beacon_table.column_queued",
    "beacon_table.column_scheduled",
    "beacon_table.column_pending",
    "beacon_table.column_output",
    "beacon_table.column_key_rotation",
]

# Status badge symbols and colors
_STATUS_BADGES = {
    "active":  (tr("beacon_table.status_active", "\u25CF Active"),   QColor("#00ff00")),
    "idle":    (tr("beacon_table.status_idle", "\u25CF Idle"),       QColor("#ffaa00")),
    "dead":    (tr("beacon_table.status_dead", "\u25CF Dead"),       QColor("#ff4444")),
    "removed": (tr("beacon_table.status_removed", "\u25CF Removed"), QColor("#ff4444")),
}


class _BeaconTableModel(QAbstractTableModel):
    """Internal model holding beacon data with flash tracking."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._beacons: list[dict] = []
        self._prev_seen: dict[str, float] = {}  # beacon_id -> last_seen_ago
        self._flash_rows: set[int] = set()  # rows that should flash

    def rowCount(self, parent=QModelIndex()):
        return len(self._beacons)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._beacons):
            return None
        b = self._beacons[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_data(b, col)
        if role == Qt.ItemDataRole.UserRole:
            return b['beacon_id']
        if role == Qt.ItemDataRole.ForegroundRole and col == 1:
            return self._status_color(b['status'])
        if role == Qt.ItemDataRole.ToolTipRole and col == 0:
            return b['beacon_id']  # full ID on hover
        if role == Qt.ItemDataRole.BackgroundRole and index.row() in self._flash_rows:
            return QColor(0, 212, 255, 40)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            key = _COLUMN_KEYS[section] if section < len(_COLUMN_KEYS) else None
            if key:
                return tr(key, COLUMNS[section][0])
            return COLUMNS[section][0]
        return None

    def set_beacons(self, beacons: list[dict]):
        """Update beacon list - full reset only on add/remove, else incremental."""
        # Build lookup of existing beacons by beacon_id
        old_beacons = {b['beacon_id']: (i, b) for i, b in enumerate(self._beacons)}
        new_beacons = {b['beacon_id']: (i, b) for i, b in enumerate(beacons)}

        # Detect added/removed beacons
        old_ids = set(old_beacons.keys())
        new_ids = set(new_beacons.keys())
        added = new_ids - old_ids
        removed = old_ids - new_ids

        if added or removed:
            # Structural change → full reset
            self.beginResetModel()
            self._beacons = beacons
            self._prev_seen = {b['beacon_id']: b.get('last_seen_ago', 0) for b in beacons}
            self._flash_rows = set()
            self.endResetModel()
        else:
            # Same set of beacons → incremental update per row
            for bid, (old_row, old_data) in old_beacons.items():
                new_row, new_data = new_beacons[bid]
                # Update last_seen_ago (column 3) and status (column 2) if changed
                if new_data.get('last_seen_ago') != old_data.get('last_seen_ago'):
                    idx = self.index(old_row, 3)
                    self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DisplayRole])
                if new_data.get('status') != old_data.get('status'):
                    idx = self.index(old_row, 2)
                    self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ForegroundRole])
                # Update task counts (columns 5-8)
                for col in (5, 6, 7, 8):
                    if new_data.get(self._col_key(col)) != old_data.get(self._col_key(col)):
                        idx = self.index(old_row, col)
                        self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.DisplayRole])
                # Flash on check-in (last_seen decreased)
                prev = self._prev_seen.get(bid)
                seen = new_data.get('last_seen_ago', 0)
                if prev is not None and seen < prev:
                    self._flash_rows.add(old_row)
            self._prev_seen = {b['beacon_id']: b.get('last_seen_ago', 0) for b in beacons}
            self._beacons = beacons

            if self._flash_rows:
                QTimer.singleShot(1000, self._clear_flashes)

    def _col_key(self, col: int) -> str:
        """Map column index to beacon dict key."""
        return {
            5: 'queued_tasks_internal',
            6: 'scheduled_tasks',
            7: 'pending_tasks',
            8: 'output_count',
            9: 'key_rotation_pending',
        }.get(col, '')

    def _clear_flashes(self):
        if self._flash_rows:
            rows = list(self._flash_rows)
            self._flash_rows.clear()
            # Emit dataChanged for background role on flashed rows
            for r in rows:
                for c in range(self.columnCount()):
                    idx = self.index(r, c)
                    self.dataChanged.emit(idx, idx, [Qt.ItemDataRole.BackgroundRole])

    def beacon_at(self, row: int) -> Optional[str]:
        if 0 <= row < len(self._beacons):
            return self._beacons[row]['beacon_id']
        return None

    def beacon_data_at(self, row: int) -> Optional[dict]:
        if 0 <= row < len(self._beacons):
            return self._beacons[row]
        return None

    def all_beacons(self) -> list[dict]:
        return self._beacons

    @staticmethod
    def _display_data(b: dict, col: int) -> str:
        if col == 0:
            return b.get("name") or b.get("computer_name") or b['beacon_id'][:16]
        if col == 1:
            return b['beacon_id'][:16]
        if col == 2:
            badge = _STATUS_BADGES.get(b['status'])
            return badge[0] if badge else b['status']
        if col == 3:
            return tr("beacon_table.last_seen_fmt", "{seconds}s ago", seconds=b.get('last_seen_ago', 0))
        if col == 4:
            return tr("beacon_table.yes", "Yes") if b['authenticated'] else tr("beacon_table.no", "No")
        if col == 5:
            return str(b['queued_tasks_internal'])
        if col == 6:
            return str(b.get('scheduled_tasks', 0))
        if col == 7:
            return str(b.get('pending_tasks', 0))
        if col == 8:
            return str(b['output_count'])
        if col == 9:
            return tr("beacon_table.pending", "Pending") if b['key_rotation_pending'] else tr("beacon_table.no", "No")
        return ""

    @staticmethod
    def _status_color(status: str) -> Optional[QColor]:
        badge = _STATUS_BADGES.get(status)
        return badge[1] if badge else None


class _BeaconFilterProxy(QSortFilterProxyModel):
    """Filter proxy for beacon search."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter_text = ""

    def set_filter_text(self, text: str):
        self._filter_text = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, row: int, parent: QModelIndex()) -> bool:
        if not self._filter_text:
            return True
        model = self.sourceModel()
        if not isinstance(model, _BeaconTableModel):
            return True
        for col in range(model.columnCount()):
            idx = model.index(row, col, parent)
            data = model.data(idx, Qt.ItemDataRole.DisplayRole)
            if data and self._filter_text in str(data).lower():
                return True
        return False


# Opcode map for dispatched actions (dialogs handle payload construction)
    ACTION_OPCODES = {
        "bof":   0x10,
        "execute_pe": 0x10,
        "inject":  0x30,
        "list_files": 0x13,
        "sleep":   0x02,
        "etw_enable":  0x25,
        "etw_disable": 0x26,
        "exit":    0xFF,
    }


class BeaconTableWidget(QWidget):
    """Main beacon table view with sort/filter, batch selection, and context menu."""

    beacon_selected = pyqtSignal(object)

    def __init__(self, api: PandragonAPI, parent=None):
        super().__init__(parent)
        self.api = api
        self.selected_beacon_id: Optional[str] = None
        self.task_queue = None
        self._notifications: Optional[NotificationOverlay] = None

        layout = QVBoxLayout(self)

        #  Toolbar 
        toolbar = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("beacon_table.filter_placeholder", "Filter beacons\u2026"))
        self.search_input.textChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.search_input)

        self.refresh_btn = QPushButton(tr("beacon_table.refresh_btn", "Refresh"))
        self.refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self.refresh_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        #  Table view 
        self._model = _BeaconTableModel(self)
        self._proxy = _BeaconFilterProxy(self)
        self._proxy.setSourceModel(self._model)

        self.table = QTableView()
        self.table.setModel(self._proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()

        header = self.table.horizontalHeader()
        for i, (_, width) in enumerate(COLUMNS):
            if width:
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
                header.resizeSection(i, width)
            else:
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)

        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        layout.addWidget(self.table)

        #  Keyboard shortcuts 
        from PyQt6.QtGui import QShortcut
        QShortcut(QKeySequence("Ctrl+R"), self, self.rotate_key)
        QShortcut(QKeySequence.StandardKey.Delete, self, self.remove_beacon)
        QShortcut(QKeySequence("Escape"), self, self.search_input.clear)

        #  Auto-refresh 
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(15000)

    #  Public API 

    def set_notification_overlay(self, overlay: NotificationOverlay):
        self._notifications = overlay

    def refresh(self):
        try:
            beacons = self.api.list_beacons()
            self._model.set_beacons(beacons)

            if self.selected_beacon_id:
                alive = any(b['beacon_id'] == self.selected_beacon_id for b in beacons)
                if not alive:
                    self.selected_beacon_id = None
                    self.beacon_selected.emit(None)
        except Exception as e:
            if self._notifications:
                self._notifications.warning(tr("notification.beacon_refresh_failed", "Beacon refresh failed: {error}", error=e), 5000)

    def get_selected_beacon_id(self) -> Optional[str]:
        if self.selected_beacon_id:
            return self.selected_beacon_id
        idx = self._first_selected_source_index()
        if idx is not None:
            self.selected_beacon_id = self._model.beacon_at(idx)
        return self.selected_beacon_id

    def get_selected_beacon_ids(self) -> list[str]:
        ids = []
        for idx in self._proxy_selected_rows():
            bid = self._model.beacon_at(idx)
            if bid:
                ids.append(bid)
        return ids

    def select_beacon_by_id(self, beacon_id: str):
        """Select a beacon row by its full ID."""
        for row in range(self._model.rowCount()):
            if self._model.beacon_at(row) == beacon_id:
                proxy_idx = self._proxy.mapFromSource(self._model.index(row, 0))
                self.table.selectRow(proxy_idx.row())
                return

    #  Selection helpers 

    def _first_selected_source_index(self) -> Optional[int]:
        rows = self._proxy_selected_rows()
        return rows[0] if rows else None

    def _proxy_selected_rows(self) -> list[int]:
        out = []
        for idx in self.table.selectionModel().selectedRows(0):
            src = self._proxy.mapToSource(idx)
            out.append(src.row())
        return out

    def _on_selection_changed(self, selected, deselected):
        row = self._first_selected_source_index()
        if row is not None:
            bid = self._model.beacon_at(row)
            self.selected_beacon_id = bid
            self.beacon_selected.emit(bid)
        else:
            self.selected_beacon_id = None
            self.beacon_selected.emit(None)

    def _on_filter_changed(self, text: str):
        self._proxy.set_filter_text(text)

    #  Actions 

    def remove_beacon(self):
        bids = self.get_selected_beacon_ids()
        if not bids:
            QMessageBox.warning(self, tr("beacon_table.warning_title", "Warning"), tr("beacon_table.no_beacon_selected", "No beacon selected"))
            return
        label = bids[0][:16] if len(bids) == 1 else tr("beacon_table.label_beacons", "{count} beacons", count=len(bids))
        reply = QMessageBox.question(
            self, tr("beacon_table.confirm_remove_title", "Confirm"), tr("beacon_table.confirm_remove", "Remove {label}?", label=label),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for bid in bids:
            try:
                self.api.remove_beacon(bid)
            except Exception as e:
                QMessageBox.critical(self, tr("beacon_table.error_title", "Error"), str(e))
        self.refresh()

    def rotate_key(self):
        bids = self.get_selected_beacon_ids()
        if not bids:
            QMessageBox.warning(self, tr("beacon_table.warning_title", "Warning"), tr("beacon_table.no_beacon_selected", "No beacon selected"))
            return
        for bid in bids:
            try:
                self.api.rotate_key(bid)
            except Exception as e:
                QMessageBox.critical(self, tr("beacon_table.error_title", "Error"), str(e))
        self.refresh()

    def rename_beacon(self):
        bids = self.get_selected_beacon_ids()
        if not bids:
            QMessageBox.warning(self, tr("beacon_table.warning_title", "Warning"), tr("beacon_table.no_beacon_selected", "No beacon selected"))
            return
        bid = bids[0]
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            self, tr("beacon_table.rename_title", "Rename Beacon"),
            tr("beacon_table.rename_prompt", "New name for {id}:", id=bid[:16]),
        )
        if not ok:
            return
        try:
            self.api.rename_beacon(bid, name.strip())
            if self._notifications:
                self._notifications.success(tr("notification.beacon_renamed", "Beacon renamed to {name}", name=name.strip()), 3000)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, tr("beacon_table.error_title", "Error"), str(e))

    def queue_etw(self, enable: bool):
        bids = self.get_selected_beacon_ids()
        if not bids:
            return
        opcode = 0x25 if enable else 0x26
        desc = tr("beacon_table.description_etw_enable", "etw: enable") if enable else tr("beacon_table.description_etw_disable", "etw: disable")
        payload = base64.b64encode(b"").decode()
        for bid in bids:
            if self.task_queue:
                self.task_queue.add_task(
                    beacon_id=bid, opcode=opcode, payload=payload,
                    description=desc,
                )
        self.refresh()

    def queue_exit(self):
        bids = self.get_selected_beacon_ids()
        if not bids:
            return
        label = bids[0][:16] if len(bids) == 1 else tr("beacon_table.label_beacons", "{count} beacons", count=len(bids))
        reply = QMessageBox.question(
            self, tr("beacon_table.confirm_exit_title", "Confirm Exit"), tr("beacon_table.confirm_exit", "Terminate {label}?", label=label),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for bid in bids:
            if self.task_queue:
                self.task_queue.add_task(
                    beacon_id=bid, opcode=0xFF, payload="",
                    description=tr("beacon_table.description_exit", "exit beacon"),
                )
        self.refresh()

    #  Context Menu 

    def _show_context_menu(self, pos):
        beacon_id = self.get_selected_beacon_id()
        if not beacon_id:
            return

        menu = QMenu(self)
        self._build_context_menu(menu, beacon_id)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _build_context_menu(self, menu: QMenu, beacon_id: str):
        #  Execution 
        exec_m = menu.addMenu(tr("beacon_table.context_execution", "Execution"))
        self._add_action(exec_m, tr("beacon_table.context_bof_exec", "BOF Exec"), "bof", beacon_id)
        self._add_action(exec_m, tr("beacon_table.context_execute_pe", "Execute PE..."), "execute_pe", beacon_id)

        menu.addSeparator()

        #  Inject 
        inject = menu.addMenu(tr("beacon_table.context_inject", "Inject"))
        self._add_action(inject, tr("beacon_table.context_inject_process", "Inject Process"), "inject", beacon_id)

        menu.addSeparator()

        #  File Operations 
        file_m = menu.addMenu(tr("beacon_table.context_file_ops", "File Operations"))
        self._add_action(file_m, tr("beacon_table.context_list_files", "List Files"),    "list_files", beacon_id)

        menu.addSeparator()

        #  Beacon Control 
        ctrl = menu.addMenu(tr("beacon_table.context_beacon_ctrl", "Beacon Control"))

        sleep_a = QAction(tr("beacon_table.context_sleep", "Sleep\u2026"), self)
        sleep_a.triggered.connect(lambda: self._open_dialog(SleepDialog, beacon_id, "sleep"))
        ctrl.addAction(sleep_a)

        ctrl.addSeparator()
        etw_on = QAction(tr("beacon_table.context_etw_enable", "ETW Enable"), self)
        etw_on.triggered.connect(lambda: self.queue_etw(True))
        ctrl.addAction(etw_on)
        etw_off = QAction(tr("beacon_table.context_etw_disable", "ETW Disable"), self)
        etw_off.triggered.connect(lambda: self.queue_etw(False))
        ctrl.addAction(etw_off)

        ctrl.addSeparator()
        exit_a = QAction(tr("beacon_table.context_exit", "Exit Beacon"), self)
        exit_a.triggered.connect(lambda: self.queue_exit())
        ctrl.addAction(exit_a)

        ctrl.addSeparator()

        rename_a = QAction(tr("beacon_table.context_rename", "Rename Beacon\u2026"), self)
        rename_a.triggered.connect(lambda: self.rename_beacon())
        ctrl.addAction(rename_a)

        rotate_a = QAction(tr("beacon_table.context_rotate_key", "Rotate Key"), self)
        rotate_a.setShortcut(QKeySequence("Ctrl+R"))
        rotate_a.triggered.connect(lambda: self.rotate_key())
        ctrl.addAction(rotate_a)

        remove_a = QAction(tr("beacon_table.context_remove", "Remove Beacon"), self)
        remove_a.setShortcut(QKeySequence.StandardKey.Delete)
        remove_a.triggered.connect(lambda: self.remove_beacon())
        ctrl.addAction(remove_a)

    def _add_action(self, parent, label: str, action_key: str, beacon_id: str):
        a = QAction(label, parent)
        a.setData(action_key)
        a.triggered.connect(lambda: self._open_dialog_by_key(action_key, beacon_id))
        parent.addAction(a)

    def _open_dialog_by_key(self, action_key: str, beacon_id: str):
        dlg_map = {
            "bof": BOFExecDialog,
            "execute_pe": ExecutePEDialog,
            "inject": InjectProcessDialog,
            "list_files": ListFilesDialog,
            "sleep": SleepDialog,
        }
        dlg_cls = dlg_map.get(action_key)
        if not dlg_cls:
            return
        self._open_dialog(dlg_cls, beacon_id, action_key)

    def _open_dialog(self, dialog_cls, beacon_id: str, action: str):
        dlg = dialog_cls(self)
        if action == "bof" and hasattr(dlg, 'set_server_bofs'):
            try:
                bofs = self.api.list_bofs()
                dlg.set_server_bofs([b['filename'] for b in bofs])
            except Exception:
                pass
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        if action == "execute_pe":
            self._handle_execute_pe(beacon_id, dlg)
            return

        task = self._build_and_queue_task(beacon_id, action, dlg)
        if task:
            QMessageBox.information(
                self, tr("beacon_table.task_queued_title", "Task Queued"),
                tr("beacon_table.task_queued", "Task queued: {action} (ID: {task_id})\nWill be submitted on next beacon check-in.", action=action, task_id=task.id)
            )
            self.refresh()

    def _handle_execute_pe(self, beacon_id: str, dlg):
        """Handle Execute PE - reads PE file, sends directly to server via execute_pe API."""
        try:
            file_path = dlg.get_file_path()
            with open(file_path, "rb") as f:
                pe_bytes = f.read()
            pe_b64 = base64.b64encode(pe_bytes).decode()

            result = self.api.execute_pe(
                beacon_id=beacon_id,
                pe_data_b64=pe_b64,
                pe_filename=dlg.get_filename(),
                arch=dlg.get_arch_value(),
                bypass=dlg.get_bypass_value(),
            )

            if result.get('success'):
                QMessageBox.information(
                    self, tr("beacon_table.execute_pe_title", "Execute PE"),
                    tr("beacon_table.execute_pe_queued", "PE execution queued on server\nFile: {file}\nShellcode size: {size} bytes\nTask ID: {task_id}",
                       file=dlg.get_filename(), size=result.get('shellcode_size', '?'), task_id=result.get('task_id', '?'))
                )
            else:
                QMessageBox.critical(
                    self, tr("beacon_table.execute_pe_failed_title", "Execute PE Failed"),
                    tr("beacon_table.execute_pe_failed", "Server error: {error}", error=result.get('error', 'Unknown error'))
                )
        except Exception as e:
            QMessageBox.critical(self, tr("beacon_table.error_title", "Error"), tr("beacon_table.failed_to_execute_pe", "Failed to execute PE: {error}", error=e))

    #  Task building 

    _PAYLOAD_BUILDERS = {}

    def _build_and_queue_task(self, beacon_id: str, action: str, dlg):
        if not self.task_queue:
            QMessageBox.warning(self, tr("beacon_table.warning_title", "Warning"), tr("beacon_table.task_queue_not_initialized", "Task queue not initialized"))
            return None

        payload, desc = self._build_payload(action, dlg)
        if payload is None:
            return None

        opcode = ACTION_OPCODES.get(action)
        if opcode is None:
            return None

        return self.task_queue.add_task(
            beacon_id=beacon_id, opcode=opcode, payload=payload,
            description=desc,
        )

    def _build_payload(self, action: str, dlg):
        if action == "bof":
            bof_path = dlg.get_bof_path()
            args = dlg.get_arguments()
            text = f"{bof_path} {args}".strip()
            return base64.b64encode(text.encode()).decode(), tr("beacon_table.description_bof", "bof: {path}", path=bof_path)

        if action == "inject":
            pid = dlg.get_pid()
            bof_path = dlg.get_bof_path()
            text = f"{pid} {bof_path}"
            return base64.b64encode(text.encode()).decode(), tr("beacon_table.description_inject", "inject: pid={pid}", pid=pid)

        if action == "list_files":
            d = dlg.get_directory_path()
            return base64.b64encode(d.encode()).decode(), tr("beacon_table.description_list", "list: {dir}", dir=d)

        if action == "sleep":
            sec = dlg.get_sleep_seconds()
            return base64.b64encode(str(sec).encode()).decode(), tr("beacon_table.description_sleep", "sleep: {seconds}s", seconds=sec)

        return None, ""
