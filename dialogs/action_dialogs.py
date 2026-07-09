"""
Action Dialogs

Specialized input dialogs for beacon actions triggered from the
right-click context menu. Each dialog collects the parameters
needed to construct and submit a task via the REST API.
"""

import os
import base64
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QComboBox, QSpinBox, QHBoxLayout,
    QDialogButtonBox, QMessageBox, QLabel, QPushButton,
    QFileDialog,
)
from PyQt6.QtGui import QFont
from gui.translations.manager import tr

# Maximum allowed file sizes for validation (bytes)
MAX_BOF_SIZE = 1 * 1024 * 1024       # 1 MB
MAX_SHELLCODE_SIZE = 1 * 1024 * 1024  # 1 MB


class _BaseActionDialog(QDialog):
    """Base class for action dialogs with common helpers."""

    def __init__(self, title_key: str, title_default: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr(title_key, title_default))
        self.setMinimumWidth(400)
        self._layout = QFormLayout(self)
        self._build_buttons()

    def _build_buttons(self):
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._layout.addRow("", buttons)


#  BOF Exec 

class BOFExecDialog(_BaseActionDialog):
    """Collects BOF file path and arguments."""

    def __init__(self, parent=None):
        super().__init__("action.bof_exec_title", "BOF Exec", parent)

        # BOF file row with browse button
        bof_row = QHBoxLayout()
        self.bof_path_input = QLineEdit()
        self.bof_path_input.setPlaceholderText(tr("action.bof_path_placeholder", "/path/to/beacon.o"))
        self.bof_browse_btn = QPushButton(tr("action.browse", "Browse..."))
        self.bof_browse_btn.clicked.connect(self._browse_bof)
        bof_row.addWidget(self.bof_path_input)
        bof_row.addWidget(self.bof_browse_btn)
        self._layout.addRow(tr("action.local_bof_file", "Local BOF File:"), bof_row)

        # Server BOFs combo (populated by set_server_bofs)
        self._server_bofs_combo = QComboBox()
        self._server_bofs_combo.addItem(tr("action.select_from_server", "(select from server)"))
        self._server_bofs_combo.currentIndexChanged.connect(self._on_server_bof_selected)
        self._layout.addRow(tr("action.server_bof", "Server BOF:"), self._server_bofs_combo)

        self.args_input = QLineEdit()
        self.args_input.setPlaceholderText(tr("action.args_placeholder", "arg1 arg2 ..."))
        self._layout.addRow(tr("action.arguments", "Arguments:"), self.args_input)

        # Conversion toolbar
        conv_row = QHBoxLayout()
        conv_row.setSpacing(4)
        b64_btn = QPushButton(tr("action.text_to_b64", "Text \u2192 B64"))
        b64_btn.clicked.connect(self._text_to_b64)
        conv_row.addWidget(b64_btn)
        hex_btn = QPushButton(tr("action.text_to_hex", "Text \u2192 Hex"))
        hex_btn.clicked.connect(self._text_to_hex)
        conv_row.addWidget(hex_btn)
        file_b64_btn = QPushButton(tr("action.file_to_b64", "File \u2192 B64"))
        file_b64_btn.clicked.connect(self._file_to_b64)
        conv_row.addWidget(file_b64_btn)
        conv_row.addStretch()
        self._layout.addRow("", conv_row)

    def set_server_bofs(self, filenames: list[str]):
        self._server_bofs_combo.blockSignals(True)
        self._server_bofs_combo.clear()
        self._server_bofs_combo.addItem(tr("action.select_from_server", "(select from server)"))
        for fn in filenames:
            self._server_bofs_combo.addItem(fn)
        self._server_bofs_combo.blockSignals(False)

    def _on_server_bof_selected(self, index: int):
        if index <= 0:
            return
        self.bof_path_input.setText(self._server_bofs_combo.currentText())

    def _text_to_b64(self):
        text = self.args_input.text()
        if not text:
            return
        self.args_input.setText(base64.b64encode(text.encode()).decode())

    def _text_to_hex(self):
        text = self.args_input.text()
        if not text:
            return
        self.args_input.setText(text.encode().hex())

    def _file_to_b64(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("action.select_file", "Select File"), "", tr("action.all_files_filter", "All Files (*)")
        )
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.args_input.setText(base64.b64encode(data).decode())
        except Exception as e:
            QMessageBox.critical(self, tr("action.error_title", "Error"), tr("action.failed_read_file", "Failed to read file: {error}", error=e))

    def _browse_bof(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("action.select_bof_file", "Select BOF File"), "", tr("action.bof_files_filter", "BOF Files (*.o *.obj);;All Files (*)")
        )
        if path:
            self.bof_path_input.setText(path)

    def get_bof_path(self) -> str:
        return self.bof_path_input.text()

    def get_arguments(self) -> str:
        return self.args_input.text()

    def accept(self):
        """Validate BOF file exists and is within size limits before accepting."""
        bof_path = self.get_bof_path()
        if not bof_path:
            QMessageBox.warning(self, tr("action.validation_error", "Validation Error"), tr("action.bof_path_required", "BOF file path is required."))
            return
        if not os.path.isfile(bof_path):
            QMessageBox.warning(self, tr("action.validation_error", "Validation Error"), tr("action.bof_file_not_found", "BOF file not found:\n{path}", path=bof_path))
            return
        file_size = os.path.getsize(bof_path)
        if file_size == 0:
            QMessageBox.warning(self, tr("action.validation_error", "Validation Error"), tr("action.bof_file_empty", "BOF file is empty."))
            return
        if file_size > MAX_BOF_SIZE:
            QMessageBox.warning(
                self, tr("action.validation_error", "Validation Error"),
                tr("action.bof_file_too_large", "BOF file too large ({size} bytes). Max allowed: {max_size} bytes", size=file_size, max_size=MAX_BOF_SIZE)
            )
            return
        super().accept()


#  Inject Process 

class InjectProcessDialog(_BaseActionDialog):
    """Collects target PID and BOF file path for injection."""

    def __init__(self, parent=None):
        super().__init__("action.inject_process_title", "Inject Process", parent)
        self.pid_spin = QSpinBox()
        self.pid_spin.setRange(0, 999999)
        self.pid_spin.setValue(0)
        self._layout.addRow(tr("action.target_pid", "Target PID:"), self.pid_spin)

        # Payload file row with browse button
        bof_row = QHBoxLayout()
        self.bof_path_input = QLineEdit()
        self.bof_path_input.setPlaceholderText(tr("action.payload_placeholder", "/path/to/shellcode.bin"))
        self.bof_browse_btn = QPushButton(tr("action.browse", "Browse..."))
        self.bof_browse_btn.clicked.connect(self._browse_payload)
        bof_row.addWidget(self.bof_path_input)
        bof_row.addWidget(self.bof_browse_btn)
        self._layout.addRow(tr("action.payload_label", "BOF / Payload:"), bof_row)

    def _browse_payload(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("action.select_payload", "Select Payload File"), "",
            tr("action.payload_filter", "Payload Files (*.o *.obj *.bin *.raw);;All Files (*)")
        )
        if path:
            self.bof_path_input.setText(path)

    def get_pid(self) -> int:
        return self.pid_spin.value()

    def get_bof_path(self) -> str:
        return self.bof_path_input.text()

    def accept(self):
        """Validate payload file exists and is within size limits before accepting."""
        bof_path = self.get_bof_path()
        if not bof_path:
            QMessageBox.warning(self, tr("action.validation_error", "Validation Error"), tr("action.payload_required", "Payload file path is required."))
            return
        if not os.path.isfile(bof_path):
            QMessageBox.warning(self, tr("action.validation_error", "Validation Error"), tr("action.payload_not_found", "Payload file not found:\n{path}", path=bof_path))
            return
        file_size = os.path.getsize(bof_path)
        if file_size == 0:
            QMessageBox.warning(self, tr("action.validation_error", "Validation Error"), tr("action.payload_empty", "Payload file is empty."))
            return
        if file_size > MAX_SHELLCODE_SIZE:
            QMessageBox.warning(
                self, tr("action.validation_error", "Validation Error"),
                tr("action.payload_too_large", "Payload file too large ({size} bytes). Max allowed: {max_size} bytes", size=file_size, max_size=MAX_SHELLCODE_SIZE)
            )
            return
        super().accept()


#  File Download 

class FileDownloadDialog(_BaseActionDialog):
    """Collects remote path and optional local save path."""

    def __init__(self, parent=None):
        super().__init__("action.download_file_title", "Download File", parent)
        self.remote_path_input = QLineEdit()
        self.remote_path_input.setPlaceholderText(tr("action.remote_path_placeholder", "C:\\Users\\target\\secret.txt"))
        self._layout.addRow(tr("action.remote_path", "Remote Path:"), self.remote_path_input)

        self.local_path_input = QLineEdit()
        self.local_path_input.setPlaceholderText(tr("action.local_save_placeholder", "C:\\Users\\target\\secret.txt (optional)"))
        self._layout.addRow(tr("action.local_save_path", "Local Save Path (optional):"), self.local_path_input)

    def get_remote_path(self) -> str:
        return self.remote_path_input.text()

    def get_local_path(self) -> str:
        return self.local_path_input.text()


#  File Upload 

class FileUploadDialog(_BaseActionDialog):
    """Collects local file path and remote destination."""

    def __init__(self, parent=None):
        super().__init__("action.upload_file_title", "Upload File", parent)

        # Local file row with browse button
        local_row = QHBoxLayout()
        self.local_path_input = QLineEdit()
        self.local_path_input.setPlaceholderText(tr("action.local_file_placeholder", "C:\\Users\\target\\tool.exe"))
        self.local_browse_btn = QPushButton(tr("action.browse", "Browse..."))
        self.local_browse_btn.clicked.connect(self._browse_local)
        local_row.addWidget(self.local_path_input)
        local_row.addWidget(self.local_browse_btn)
        self._layout.addRow(tr("action.local_file", "Local File:"), local_row)

        self.remote_path_input = QLineEdit()
        self.remote_path_input.setPlaceholderText(tr("action.remote_dest_placeholder", "C:\\Users\\Public\\tool.exe"))
        self._layout.addRow(tr("action.remote_destination", "Remote Destination:"), self.remote_path_input)

    def _browse_local(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("action.select_file_upload", "Select File to Upload"), "", tr("action.all_files_filter", "All Files (*)")
        )
        if path:
            self.local_path_input.setText(path)

    def get_local_path(self) -> str:
        return self.local_path_input.text()

    def get_remote_path(self) -> str:
        return self.remote_path_input.text()

    def accept(self):
        """Validate local file exists before accepting."""
        local_path = self.get_local_path()
        if not local_path:
            QMessageBox.warning(self, tr("action.validation_error", "Validation Error"), tr("action.local_file_required", "Local file path is required."))
            return
        if not os.path.isfile(local_path):
            QMessageBox.warning(self, tr("action.validation_error", "Validation Error"), tr("action.local_file_not_found", "Local file not found:\n{path}", path=local_path))
            return
        file_size = os.path.getsize(local_path)
        if file_size == 0:
            QMessageBox.warning(self, tr("action.validation_error", "Validation Error"), tr("action.local_file_empty", "Local file is empty."))
            return
        super().accept()


#  List Files 

class ListFilesDialog(_BaseActionDialog):
    """Collects remote directory path to list."""

    def __init__(self, parent=None):
        super().__init__("action.list_files_title", "List Files", parent)
        self.dir_path_input = QLineEdit()
        self.dir_path_input.setPlaceholderText(tr("action_dialog.placeholder_root_dir", "C:\\"))
        self._layout.addRow(tr("action.remote_directory", "Remote Directory:"), self.dir_path_input)

    def get_directory_path(self) -> str:
        return self.dir_path_input.text()


#  Sleep 

class SleepDialog(_BaseActionDialog):
    """Collects sleep interval in seconds."""

    def __init__(self, parent=None):
        super().__init__("action.sleep_title", "Set Sleep Interval", parent)
        self.sleep_spin = QSpinBox()
        self.sleep_spin.setRange(1, 86400)
        self.sleep_spin.setValue(60)
        self.sleep_spin.setSuffix(tr("action.sleep_seconds_suffix", " seconds"))
        self._layout.addRow(tr("action.sleep_interval", "Sleep Interval:"), self.sleep_spin)

    def get_sleep_seconds(self) -> int:
        return self.sleep_spin.value()


#  ETW Toggle 

class ETWDialog(_BaseActionDialog):
    """Toggle ETW enable/disable selector."""

    def __init__(self, parent=None):
        super().__init__("action.etw_title", "ETW Toggle", parent)
        self.action_combo = QComboBox()
        self.action_combo.addItems([
            tr("action.etw_enable", "Enable"),
            tr("action.etw_disable", "Disable"),
        ])
        self._layout.addRow(tr("action.etw_action", "Action:"), self.action_combo)

    def get_action(self) -> str:
        """Return 'enable' or 'disable'."""
        return self.action_combo.currentText().lower()


#  Exit Beacon 

class ExitDialog(_BaseActionDialog):
    """Confirmation dialog for exiting a beacon."""

    def __init__(self, parent=None):
        super().__init__("action.exit_title", "Exit Beacon", parent)
        label = QLabel(
            tr("action.exit_confirm", "Are you sure you want to terminate this beacon?\nThe beacon will stop checking in and all pending tasks will be lost.")
        )
        label.setWordWrap(True)
        font = QFont()
        font.setBold(True)
        label.setFont(font)
        self._layout.addRow(label)

#  Execute PE via Donut 

class ExecutePEDialog(_BaseActionDialog):
    """Upload a PE to the server; server converts to shellcode via Donut
    and queues a shellcode_loader BOF execution."""

    def __init__(self, parent=None):
        super().__init__("action.execute_pe_title", "Execute PE / Assembly", parent)

        file_row = QHBoxLayout()
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText(tr("action.pe_file_placeholder", "C:\\Tools\\mimikatz.exe"))
        browse = QPushButton(tr("action.browse", "Browse..."))
        browse.clicked.connect(self._browse)
        file_row.addWidget(self.file_input)
        file_row.addWidget(browse)
        self._layout.addRow(tr("action.pe_file", "PE File:"), file_row)

        self.filename_input = QLineEdit()
        self.filename_input.setPlaceholderText(tr("action_dialog.placeholder_pe_filename", "mimikatz.exe"))
        self._layout.addRow(tr("action.pe_filename", "PE Filename:"), self.filename_input)

        self.arch_combo = QComboBox()
        self.arch_combo.addItems([tr("action.arch_x64", "x64"), tr("action.arch_x86", "x86"), tr("action.arch_both", "Both")])
        self._layout.addRow(tr("action.architecture", "Architecture:"), self.arch_combo)

        self.bypass_combo = QComboBox()
        self.bypass_combo.addItems([
            tr("action.bypass_amsi_wldp", "AMSI+WLDP"),
            tr("action.bypass_amsi_only", "AMSI only"),
            tr("action.bypass_wldp_only", "WLDP only"),
            tr("action.bypass_none", "None"),
        ])
        self._layout.addRow(tr("action.bypass", "Bypass:"), self.bypass_combo)

        self.args_input = QLineEdit()
        self.args_input.setPlaceholderText(tr("action.pe_args_placeholder", "sekurlsa::logonpasswords"))
        self._layout.addRow(tr("action.arguments", "Arguments:"), self.args_input)

        self.cls_input = QLineEdit()
        self.cls_input.setPlaceholderText(tr("action.dotnet_class_placeholder", "SharpHound.Program (optional for .NET)"))
        self._layout.addRow(tr("action.dotnet_class", ".NET Class:"), self.cls_input)

        self.method_input = QLineEdit()
        self.method_input.setPlaceholderText(tr("action.dotnet_method_placeholder", "Main (optional for .NET)"))
        self._layout.addRow(tr("action.dotnet_method", ".NET Method:"), self.method_input)

        self.runtime_input = QLineEdit()
        self.runtime_input.setPlaceholderText(tr("action.dotnet_runtime_placeholder", "v4.0.30319 (optional for .NET)"))
        self._layout.addRow(tr("action.dotnet_runtime", ".NET Runtime:"), self.runtime_input)

        conv_row = QHBoxLayout()
        conv_row.setSpacing(4)
        file_b64_btn = QPushButton(tr("action.pe_to_b64", "PE \u2192 B64"))
        file_b64_btn.clicked.connect(self._file_to_b64)
        conv_row.addWidget(file_b64_btn)
        conv_row.addStretch()
        self._layout.addRow("", conv_row)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("action.select_pe_file", "Select PE File"), "",
            tr("action.pe_files_filter", "PE Files (*.exe *.dll);;All Files (*)")
        )
        if path:
            self.file_input.setText(path)
            if not self.filename_input.text():
                self.filename_input.setText(Path(path).name)

    def _file_to_b64(self):
        path = self.file_input.text()
        if not path:
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.args_input.setText(base64.b64encode(data).decode())
        except Exception as e:
            QMessageBox.critical(self, tr("action.error_title", "Error"), tr("action.failed_read_file", "Failed to read file: {error}", error=e))

    def get_file_path(self) -> str:
        return self.file_input.text()

    def get_filename(self) -> str:
        return self.filename_input.text() or "unknown.exe"

    def get_arch_value(self) -> int:
        idx = self.arch_combo.currentIndex()
        return 3 if idx == 2 else idx + 1

    def get_bypass_value(self) -> int:
        idx = self.bypass_combo.currentIndex()
        return 3 if idx == 0 else (1 if idx == 1 else (2 if idx == 2 else 0))

    def get_args(self) -> str:
        return self.args_input.text()

    def get_cls(self) -> str:
        return self.cls_input.text()

    def get_method(self) -> str:
        return self.method_input.text()

    def get_runtime(self) -> str:
        return self.runtime_input.text()

    def accept(self):
        if not self.get_file_path():
            QMessageBox.warning(self, tr("action.validation_error", "Validation Error"), tr("action.pe_path_required", "PE file path is required."))
            return
        if not os.path.isfile(self.get_file_path()):
            QMessageBox.warning(self, tr("action.validation_error", "Validation Error"), tr("action.pe_file_not_found", "File not found:\n{path}", path=self.get_file_path()))
            return
        super().accept()
