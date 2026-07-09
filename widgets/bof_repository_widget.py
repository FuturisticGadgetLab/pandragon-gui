import base64
from typing import Optional
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QFileDialog,
    QMessageBox, QComboBox, QLineEdit, QGroupBox, QFormLayout,
    QHeaderView, QDialog, QDialogButtonBox, QTextEdit, QPlainTextEdit,
)
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QFont, QColor, QBrush

from gui.api_client import PandragonAPI
from gui.translations.manager import tr
from gui.widgets.notification_overlay import NotificationOverlay


_COLUMN_KEYS = [
    "bof_repo.name",
    "bof_repo.size",
    "bof_repo.modified",
    "bof_repo.sha256",
    "bof_repo.description",
    "bof_repo.author",
    "bof_repo.category",
]
_COLUMNS_DEFAULTS = ["Name", "Size", "Modified", "SHA256", "Description", "Author", "Category"]


class BOFRepositoryWidget(QWidget):

    def __init__(self, api: PandragonAPI, parent=None):
        super().__init__(parent)
        self.api = api
        self._notifications: Optional[NotificationOverlay] = None
        self._bofs: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        #  Toolbar 
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._refresh_btn = QPushButton(tr("bof_repo.refresh", "Refresh"))
        self._refresh_btn.clicked.connect(self.refresh)
        toolbar.addWidget(self._refresh_btn)

        self._upload_btn = QPushButton(tr("bof_repo.upload_bof", "Upload BOF"))
        self._upload_btn.clicked.connect(self._upload_bof)
        toolbar.addWidget(self._upload_btn)

        self._source_bof_btn = QPushButton(tr("bof_repo.source_bof", "Source BOF"))
        self._source_bof_btn.clicked.connect(self._source_bof_dialog)
        toolbar.addWidget(self._source_bof_btn)

        self._delete_btn = QPushButton(tr("bof_repo.delete", "Delete"))
        self._delete_btn.clicked.connect(self._delete_bof)
        toolbar.addWidget(self._delete_btn)

        self._verify_btn = QPushButton(tr("bof_repo.verify", "Verify"))
        self._verify_btn.clicked.connect(self._verify_selected)
        toolbar.addWidget(self._verify_btn)

        self._edit_meta_btn = QPushButton(tr("bof_repo.edit_metadata", "Edit Metadata"))
        self._edit_meta_btn.clicked.connect(self._edit_metadata)
        toolbar.addWidget(self._edit_meta_btn)

        self._verify_btn.setVisible(False)
        self._edit_meta_btn.setVisible(False)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        #  BOF table 
        self._table = QTableWidget()
        self._table.setColumnCount(len(_COLUMNS_DEFAULTS))
        self._table.setHorizontalHeaderLabels([tr(k, d) for k, d in zip(_COLUMN_KEYS, _COLUMNS_DEFAULTS)])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setFont(QFont("Consolas", 9))
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table, 1)

        #  Deploy section 
        deploy_group = QGroupBox(tr("bof_repo.execute_on_beacon", "Execute on Beacon"))
        deploy_layout = QFormLayout(deploy_group)
        deploy_layout.setSpacing(6)

        beacon_row = QHBoxLayout()
        self._beacon_combo = QComboBox()
        self._beacon_combo.setMinimumWidth(300)
        self._beacon_combo.setPlaceholderText(tr("bof_repo.select_beacon_placeholder", "Select a beacon\u2026"))
        beacon_row.addWidget(self._beacon_combo)
        self._refresh_beacons_btn = QPushButton(tr("bof_repo.refresh", "Refresh"))
        self._refresh_beacons_btn.clicked.connect(self._populate_beacons)
        beacon_row.addWidget(self._refresh_beacons_btn)
        beacon_row.addStretch()
        deploy_layout.addRow(tr("bof_repo.target_beacon", "Target Beacon:"), beacon_row)

        self._args_input = QLineEdit()
        self._args_input.setPlaceholderText(tr("bof_repo.args_placeholder", "arg1 arg2 ..."))
        deploy_layout.addRow(tr("bof_repo.arguments", "Arguments:"), self._args_input)

        self._execute_btn = QPushButton(tr("bof_repo.execute_selected", "Execute Selected BOF"))
        self._execute_btn.clicked.connect(self._execute_bof)
        deploy_layout.addRow("", self._execute_btn)

        layout.addWidget(deploy_group)

        # Wire command_error -> notification
        self.api.command_error.connect(self._on_command_error)

        # Initial load
        QTimer.singleShot(500, self.refresh)

    def set_notification_overlay(self, overlay: NotificationOverlay):
        self._notifications = overlay

    def _on_command_error(self, beacon_id: str, data: dict):
        error = data.get('error', tr("bof_repo.unknown_error", "Unknown error"))
        task_id = data.get('task_id', '?')
        if self._notifications:
            self._notifications.error(f"[{task_id}] {error}", 6000)

    #  BOF list 

    def refresh(self):
        try:
            self._bofs = self.api.list_bofs()
            self._populate_table()
        except Exception as e:
            if self._notifications:
                self._notifications.warning(tr("bof_repo.failed_list", "Failed to list BOFs: {error}", error=e), 5000)

    def _populate_table(self):
        self._table.setRowCount(len(self._bofs))
        for i, bof in enumerate(self._bofs):
            self._table.setItem(i, 0, QTableWidgetItem(bof.get("filename", "")))

            size = bof.get("size", 0)
            size_str = tr("bof_repo.size_bytes", "{size} B", size=size) if size < 1024 else tr("bof_repo.size_kb", "{size:.1f} KB", size=size / 1024)
            self._table.setItem(i, 1, QTableWidgetItem(size_str))

            mod = bof.get("modified", 0)
            mod_str = datetime.fromtimestamp(mod).strftime("%Y-%m-%d %H:%M") if mod else "-"
            self._table.setItem(i, 2, QTableWidgetItem(mod_str))

            sha = bof.get("sha256", "")
            sha_item = QTableWidgetItem(sha[:16] + "..." if sha else "")
            if sha:
                sha_item.setToolTip(sha)
            self._table.setItem(i, 3, sha_item)

            self._table.setItem(i, 4, QTableWidgetItem(bof.get("description", "")))
            self._table.setItem(i, 5, QTableWidgetItem(bof.get("author", "")))
            self._table.setItem(i, 6, QTableWidgetItem(bof.get("category", "")))

        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setStretchLastSection(True)
        self._on_selection_changed()

    def _on_selection_changed(self):
        has_selection = self._table.currentRow() >= 0
        self._verify_btn.setVisible(has_selection)
        self._edit_meta_btn.setVisible(has_selection)

    #  Beacon list for deploy 

    def _populate_beacons(self):
        try:
            beacons = self.api.list_beacons()
            self._beacon_combo.clear()
            for b in beacons:
                label = b.get("name") or b.get("computer_name") or b["beacon_id"][:16]
                self._beacon_combo.addItem(f"{b['beacon_id'][:12]}  {label}", b["beacon_id"])
        except Exception as e:
            if self._notifications:
                self._notifications.warning(tr("bof_repo.failed_list_beacons", "Failed to list beacons: {error}", error=e), 3000)

    #  Upload 

    def _upload_bof(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("bof_repo.select_bof_file", "Select BOF File"), "", tr("bof_repo.bof_files_filter", "BOF Files (*.o *.obj);;All Files (*)")
        )
        if not path:
            return
        import os
        filename = os.path.basename(path)
        try:
            with open(path, "rb") as f:
                file_bytes = f.read()
            if not file_bytes:
                QMessageBox.warning(self, tr("bof_repo.error_title", "Error"), tr("bof_repo.file_empty", "File is empty"))
                return
            MAX_UPLOAD = 4 * 1024 * 1024
            if len(file_bytes) > MAX_UPLOAD:
                QMessageBox.warning(self, tr("bof_repo.error_title", "Error"), tr("bof_repo.file_too_large", "File too large ({size} bytes, max {max_size})", size=len(file_bytes), max_size=MAX_UPLOAD))
                return
            data_b64 = base64.b64encode(file_bytes).decode()
            self.api.upload_bof(filename, data_b64)
            if self._notifications:
                self._notifications.success(tr("bof_repo.uploaded", "Uploaded {filename}", filename=filename), 3000)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, tr("bof_repo.upload_failed_title", "Upload Failed"), str(e))

    #  Source BOF (editor + file load + build) 

    def _source_bof_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("bof_repo.source_bof_title", "Source BOF \u2014 Editor"))
        dialog.setMinimumWidth(700)
        dialog.setMinimumHeight(600)
        dialog.resize(800, 700)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(8)

        # Filename row
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(tr("bof_repo.filename", "Filename:")))
        filename_input = QLineEdit(tr("bof_repo.default_filename", "mybof.c"))
        name_row.addWidget(filename_input, 1)

        load_btn = QPushButton(tr("bof_repo.load_file", "Load File"))
        name_row.addWidget(load_btn)
        layout.addLayout(name_row)

        # Code editor
        code_editor = QPlainTextEdit()
        code_editor.setFont(QFont("Consolas", 10))
        code_editor.setPlaceholderText(
            tr("bof_repo.code_placeholder",
               '// Write your BOF code here, or load a .c file\n'
               '#include <windows.h>\n\n'
               'void go(char *args, int len) {\n'
               '    // ...\n'
               '}\n')
        )
        layout.addWidget(code_editor, 1)

        # Load file handler
        def load_file():
            path, _ = QFileDialog.getOpenFileName(
                dialog, tr("bof_repo.select_c_source", "Select C Source"), "", tr("bof_repo.c_source_filter", "C Source (*.c);;All Files (*)")
            )
            if not path:
                return
            import os
            try:
                with open(path, "rb") as f:
                    data = f.read()
                if not data:
                    QMessageBox.warning(dialog, tr("bof_repo.error_title", "Error"), tr("bof_repo.file_empty", "File is empty"))
                    return
                code_editor.setPlainText(data.decode('utf-8', errors='replace'))
                filename_input.setText(os.path.basename(path))
            except Exception as e:
                QMessageBox.critical(dialog, tr("bof_repo.read_failed_title", "Read Failed"), str(e))

        load_btn.clicked.connect(load_file)

        # Build command
        cmd_row = QHBoxLayout()
        cmd_row.addWidget(QLabel(tr("bof_repo.build_command", "Build Command:")))
        build_cmd = QLineEdit(
            tr("bof_repo.default_build_cmd",
               'x86_64-w64-mingw32-gcc -c {source} -o {output} -masm=intel -Wall')
        )
        cmd_row.addWidget(build_cmd, 1)
        layout.addLayout(cmd_row)

        # Build output
        build_output = QTextEdit()
        build_output.setReadOnly(True)
        build_output.setPlaceholderText(tr("bof_repo.build_output_placeholder", "Build output will appear here..."))
        build_output.setMaximumHeight(150)
        layout.addWidget(build_output)

        # Buttons
        btn_row = QHBoxLayout()
        build_btn = QPushButton(tr("bof_repo.build", "Build"))
        btn_row.addWidget(build_btn)
        close_btn = QPushButton(tr("bof_repo.close", "Close"))
        close_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(close_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Build handler
        def do_build():
            fname = filename_input.text().strip()
            if not fname:
                QMessageBox.warning(dialog, tr("bof_repo.warning_title", "Warning"), tr("bof_repo.enter_filename", "Enter a filename"))
                return
            if not fname.endswith('.c'):
                fname += '.c'
                filename_input.setText(fname)

            code = code_editor.toPlainText().strip()
            if not code:
                QMessageBox.warning(dialog, tr("bof_repo.warning_title", "Warning"), tr("bof_repo.write_code_first", "Write or load some code first"))
                return

            build_btn.setEnabled(False)
            build_btn.setText(tr("bof_repo.building", "Building..."))
            build_output.clear()
            build_output.append(tr("bof_repo.uploading_and_compiling", "Uploading and compiling..."))

            file_bytes = code.encode('utf-8')
            data_b64 = base64.b64encode(file_bytes).decode()
            command = build_cmd.text().strip()

            try:
                result = self.api.upload_source_bof(fname, data_b64, command)
            except Exception as e:
                build_output.append(tr("bof_repo.build_error", "\nError: {error}", error=e))
                build_btn.setEnabled(True)
                build_btn.setText(tr("bof_repo.build", "Build"))
                return

            out = result.get('output', '')
            if out:
                build_output.append(out)

            if result.get('success'):
                built = result.get('built_filename', '')
                build_output.append(tr("bof_repo.build_success", "\nBuild SUCCESS \u2014 {built} registered as BOF", built=built))
                if self._notifications:
                    self._notifications.success(tr("bof_repo.built_notification", "Built {built}", built=built), 4000)
                self.refresh()
                QTimer.singleShot(800, dialog.accept)
            else:
                build_output.append(tr("bof_repo.build_failed", "\nBuild FAILED: {error}", error=result.get('error', 'unknown error')))
                build_btn.setEnabled(True)
                build_btn.setText(tr("bof_repo.build", "Build"))

        build_btn.clicked.connect(do_build)
        dialog.exec()

    #  Delete 

    def _delete_bof(self):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._bofs):
            QMessageBox.warning(self, tr("bof_repo.warning_title", "Warning"), tr("bof_repo.no_bof_selected", "No BOF selected"))
            return
        filename = self._bofs[row].get("filename", "")
        reply = QMessageBox.question(
            self, tr("bof_repo.confirm_delete_title", "Confirm Delete"),
            tr("bof_repo.confirm_delete", "Delete {filename} from server?", filename=filename),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.api.delete_bof(filename)
            if self._notifications:
                self._notifications.success(tr("bof_repo.deleted", "Deleted {filename}", filename=filename), 3000)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, tr("bof_repo.delete_failed_title", "Delete Failed"), str(e))

    #  Verify 

    def _verify_selected(self):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._bofs):
            QMessageBox.warning(self, tr("bof_repo.warning_title", "Warning"), tr("bof_repo.no_bof_selected", "No BOF selected"))
            return
        bof = self._bofs[row]
        filename = bof.get("filename", "")
        if not bof.get("sha256"):
            QMessageBox.information(self, tr("bof_repo.verify_title", "Verify"), tr("bof_repo.no_stored_hash", "No stored hash for {filename}", filename=filename))
            return
        try:
            result = self.api.verify_bof(filename)
            if result.get("valid"):
                if self._notifications:
                    self._notifications.success(tr("bof_repo.hash_matches", "{filename}: hash matches", filename=filename), 4000)
            else:
                QMessageBox.warning(
                    self, tr("bof_repo.integrity_mismatch_title", "Integrity Mismatch"),
                    tr("bof_repo.integrity_mismatch", "{filename}\n\nStored: {stored_hash}\nActual: {actual_hash}\nError: {error}",
                       filename=filename,
                       stored_hash=result.get('stored_hash', '?')[:16] + '...',
                       actual_hash=result.get('actual_hash', '?')[:16] + '...',
                       error=result.get('error', 'hash mismatch')),
                )
        except Exception as e:
            QMessageBox.critical(self, tr("bof_repo.verify_failed_title", "Verify Failed"), str(e))

    #  Edit Metadata 

    def _edit_metadata(self):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._bofs):
            QMessageBox.warning(self, tr("bof_repo.warning_title", "Warning"), tr("bof_repo.no_bof_selected", "No BOF selected"))
            return
        bof = self._bofs[row]
        filename = bof.get("filename", "")

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("bof_repo.edit_metadata_title", "Edit BOF Metadata: {filename}", filename=filename))
        dialog.setMinimumWidth(400)

        form = QFormLayout(dialog)

        desc_edit = QLineEdit(bof.get("description", ""))
        author_edit = QLineEdit(bof.get("author", ""))
        category_edit = QLineEdit(bof.get("category", ""))

        form.addRow(tr("bof_repo.description_label", "Description:"), desc_edit)
        form.addRow(tr("bof_repo.author_label", "Author:"), author_edit)
        form.addRow(tr("bof_repo.category_label", "Category:"), category_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self.api.update_bof_metadata(
                filename,
                description=desc_edit.text(),
                author=author_edit.text(),
                category=category_edit.text(),
            )
            if self._notifications:
                self._notifications.success(tr("bof_repo.metadata_updated", "Updated metadata for {filename}", filename=filename), 3000)
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, tr("bof_repo.update_failed_title", "Update Failed"), str(e))

    #  Execute 

    def _execute_bof(self):
        row = self._table.currentRow()
        if row < 0 or row >= len(self._bofs):
            QMessageBox.warning(self, tr("bof_repo.warning_title", "Warning"), tr("bof_repo.no_bof_selected_table", "No BOF selected in the table"))
            return
        if self._beacon_combo.currentIndex() < 0:
            QMessageBox.warning(self, tr("bof_repo.warning_title", "Warning"), tr("bof_repo.no_beacon_selected", "No beacon selected"))
            return
        beacon_id = self._beacon_combo.currentData()
        bof_filename = self._bofs[row].get("filename", "")
        args = self._args_input.text().strip()
        text = f"{bof_filename} {args}".strip()
        payload = base64.b64encode(text.encode()).decode()
        desc = tr("bof_repo.execute_desc", "bof: {filename}", filename=bof_filename)
        try:
            result = self.api.create_task(
                beacon_id=beacon_id, opcode=0x10, payload=payload,
                description=desc,
            )
            task_id = result.get("task_id", "?")
            if self._notifications:
                self._notifications.success(tr("bof_repo.bof_queued", "BOF queued (task {task_id})", task_id=task_id), 4000)
        except Exception as e:
            QMessageBox.critical(self, tr("bof_repo.execute_failed_title", "Execute Failed"), str(e))
