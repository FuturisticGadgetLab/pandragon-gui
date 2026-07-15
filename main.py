"""
Pandragon Operator Console: Main Window Assembly

Integrates an embedded connection panel (no separate dialogs), theme manager,
notification overlay, and all widget panels into the main application window.
"""

import sys

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QLineEdit, QCheckBox, QPushButton,
    QStackedWidget, QMessageBox, QFrame, QComboBox,
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup,
)
from PyQt6.QtGui import QPalette, QColor, QFont

from gui.api_client import PandragonAPI
from gui.theme import ThemeManager
from gui.translations.manager import tr, TranslationManager
from gui.widgets.beacon_table import BeaconTableWidget
from gui.widgets.beacon_detail import BeaconDetailWidget
from gui.widgets.task_queue_widget import TaskQueueWidget
from gui.widgets.beacon_graph_widget import BeaconGraphWidget
from gui.widgets.config_builder_widget import ConfigBuilderWidget
from gui.widgets.bof_repository_widget import BOFRepositoryWidget
from gui.widgets.options_widget import OptionsWidget
from gui.widgets.splash_screen import SplashScreen
from gui.widgets.startup_splash import StartSplash
from gui.widgets.notification_overlay import NotificationOverlay
from gui.state import load as load_state, save as save_state

_MONO = QFont("Consolas", 10)
_MONO.setStyleHint(QFont.StyleHint.Monospace)
_MONO_BOLD = QFont("Consolas", 10, QFont.Weight.Bold)
_MONO_BOLD.setStyleHint(QFont.StyleHint.Monospace)
_MONO_TITLE = QFont("Consolas", 18, QFont.Weight.Bold)
_MONO_TITLE.setStyleHint(QFont.StyleHint.Monospace)

_MONO_DRAGON = QFont("Consolas", 6)
_MONO_DRAGON.setStyleHint(QFont.StyleHint.Monospace)

_DRAGON_ART = r'''                                        ,   ,
  P                                     $,  $,     ,
                                        "ss.$ss. .s'
    A                           ,     .ss$$$$$$$$$$s,
                                $. s$$$$$$$$$$$$$$`$$Ss
      N                         "$$$$$$$$$$$$$$$$$$o$$$       ,
                               s$$$$$$$$$$$$$$$$$$$$$$$$s,  ,s
         D                    s$$$$$$$$$"$$$$$$""""$$$$$$"$$$$$,
                              s$$$$$$$$$$s""$$$$ssssss"$$$$$$$$"
           R                 s$$$$$$$$$$'         `"""ss"$"$s""
                             s$$$$$$$$$$,              `"""""$  .s$$s
             A               s$$$$$$$$$$$$s,...               `s$$'  `
                         `ssss$$$$$$$$$$$$$$$$$$$$####s.     .$$"$.   , s
               G           `""""$$$$$$$$$$$$$$$$$$$$#####$$$$$$"     $.$'
                                 "$$$$$$$$$$$$$$$$$$$$$####s""     .$$$|
                 O                "$$$$$$$$$$$$$$$$$$$$$$$$##s    .$$" $
                                   $$""$$$$$$$$$$$$$$$$$$$$$$$$$$$$$"
                    N             $$"  "$"$$$$$$$$$$$$$$$$$$$$S""""'
                             ,   ,"     '  $$$$$$$$$$$$$$$$####s
                             $.          .s$$$$$$$$$$$$$$$$$####"
                 ,           "$s.   ..ssS$$$$$$$$$$$$$$$$$$$####"
                 $           .$$$S$$$$$$$$$$$$$$$$$$$$$$$$#####"
                 Ss     ..sS$$$$$$$$$$$$$$$$$$$$$$$$$$$######""
                  "$$sS$$$$$$$$$$$$$$$$$$$$$$$$$$$########"
           ,      s$$$$$$$$$$$$$$$$$$$$$$$$#########""'
           $    s$$$$$$$$$$$$$$$$$$$$$#######""'      s'         ,
           $$..$$$$$$$$$$$$$$$$$$######"'       ....,$$....    ,$
            "$$$$$$$$$$$$$######"' ,     .sS$$$$$$$$$$$$$$$$s$$
              $$$$$$$$$$$$#####"     $, .s$$$$$$$$$$$$$$$$$$$$$$$$s.
   )          $$$$$$$$$$$#####'      `$$$$$$$$$###########$$$$$$$$$$$
  ((          $$$$$$$$$$$#####       $$$$$$$$###"       "####$$$$$$$$$$
  ) \         $$$$$$$$$$$$####.     $$$$$$###"             "###$$$$$$$$$
 (   )        $$$$$$$$$$$$$####.   $$$$$###"                ####$$$$$$$$$
 )  ( (       $$"$$$$$$$$$$$#####.$$$$$###' PANDRAGON       .###$$$$$$$$$$
 (  )  )   _,$"   $$$$$$$$$$$$######.$$##'                .###$$$$$$$$$$
 ) (  ( \.         "$$$$$$$$$$$$$#######,,,.          ..####$$$$$$$$$$$"
(   )$ )  )        ,$$$$$$$$$$$$$$$$$$####################$$$$$$$$$$$"
(   ($$  ( \     _sS"  `"$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$S$$,
 )  )$$$s ) )  .      .   `$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$"'  `$$
  (   $$$Ss/  .$,    .$,,s$$$$$$##S$$$$$$$$$$$$$$$$$$$$$$$$S""        '
    \)_$$$$$$$$$$$$$$$$$$$$$$$##"  $$        `$$.        `$$.
        `"S$$$$$$$$$$$$$$$$$#"      $          `$          `$
            `"""""""""""""'         '
'''


_STATUS_QUIPS = [
    "the eyes chico, they never lie",
    "\u201cthe bird of Hermes is my Name\u201d",
    "nothing ever happens",
    "all quiet on the happening front",
    "there are more things in heaven and earth, Horatio\u2026",
    "in the beginning was the Word, and the Word was with God",
    "from the place of the skull, a garden",
    "skibidi dop dop yes yes",
]

_STATUS_QUIP_KEYS = [
    "quip.eyes_chico",
    "quip.bird_of_hermes",
    "quip.nothing_happens",
    "quip.quiet_front",
    "quip.horatio",
    "quip.word",
    "quip.skull",
    "quip.skibidi",
]


class ConnectPanel(QWidget):
    """Embedded connection panel shown before the main tab interface."""

    def __init__(self, on_connected, parent=None):
        super().__init__(parent)
        self._on_connected = on_connected
        self._connecting_api = None
        saved = load_state()

        outer = QHBoxLayout(self)
        outer.setSpacing(15)
        outer.setContentsMargins(26, 0, 26, 0)

        form = QVBoxLayout()
        form.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        form.setSpacing(6)
        form.setContentsMargins(0, 0, 0, 0)

        form_w = 360

        # -- server history row --
        server_row = QHBoxLayout()
        server_row.setSpacing(4)
        self._server_combo = QComboBox()
        self._server_combo.setFont(_MONO)
        self._server_combo.setFixedWidth(form_w - 30)
        self._server_combo.setPlaceholderText(tr("connect.quick_connect", "\u2014 Quick Connect \u2014"))
        self._server_combo.currentIndexChanged.connect(self._on_server_selected)
        server_row.addWidget(self._server_combo)

        self._remove_server_btn = QPushButton("\u2715")
        self._remove_server_btn.setFont(_MONO)
        self._remove_server_btn.setFixedWidth(26)
        self._remove_server_btn.setFixedHeight(24)
        self._remove_server_btn.setObjectName("removeServerBtn")
        self._remove_server_btn.setStyleSheet(
            "QPushButton#removeServerBtn { padding: 0px; font-size: 10pt; }"
        )
        self._remove_server_btn.clicked.connect(self._remove_server)
        server_row.addWidget(self._remove_server_btn)

        sw = QWidget()
        sw.setLayout(server_row)
        sw.setFixedWidth(form_w)
        form.addWidget(sw, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._refresh_server_combo()
        # -- end server history row --

        form.addSpacing(8)

        self._title = QLabel(tr("connect.title", "PANDRAGON"))
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setFont(_MONO_TITLE)
        self._title.setFixedWidth(form_w)
        form.addWidget(self._title, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._subtitle = QLabel(tr("connect.subtitle", "serexp . FGL"))
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setFont(_MONO)
        self._subtitle.setFixedWidth(form_w)
        form.addWidget(self._subtitle, alignment=Qt.AlignmentFlag.AlignHCenter)

        form.addSpacing(16)

        self._url = QLineEdit(saved.get("last_url", "wss://127.0.0.1:6767/ws"))
        self._url.setPlaceholderText(tr("connect.url_placeholder", "WebSocket URL"))
        self._url.setFont(_MONO)
        self._url.setFixedWidth(form_w)
        self._url.returnPressed.connect(self._do_connect)
        form.addWidget(self._url, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._username = QLineEdit(saved.get("last_username", tr("connect.default_username", "operator")))
        self._username.setPlaceholderText(tr("connect.username_placeholder", "Username"))
        self._username.setFont(_MONO)
        self._username.setFixedWidth(form_w)
        self._username.returnPressed.connect(self._do_connect)
        form.addWidget(self._username, alignment=Qt.AlignmentFlag.AlignHCenter)

        token_row = QHBoxLayout()
        token_row.setSpacing(0)
        self._token = QLineEdit(saved.get("last_token", ""))
        self._token.setPlaceholderText(tr("connect.token_placeholder", "Token (required)"))
        self._token.setFont(_MONO)
        self._token.setFixedWidth(form_w - 56)
        self._token.returnPressed.connect(self._do_connect)
        token_row.addWidget(self._token)

        self._token_toggle = QPushButton(tr("connect.token_show", "SHOW"))
        self._token_toggle.setObjectName("tokenToggle")
        self._token_toggle.setFont(_MONO_BOLD)
        self._token_toggle.setFixedWidth(44)
        self._token_toggle.setFixedHeight(self._token.sizeHint().height() + 4)
        self._token_toggle.setCheckable(True)
        self._token_toggle.clicked.connect(self._toggle_token_visibility)
        token_row.addWidget(self._token_toggle)

        tw = QWidget()
        tw.setLayout(token_row)
        tw.setFixedWidth(form_w)
        form.addWidget(tw, alignment=Qt.AlignmentFlag.AlignHCenter)

        chk_row = QHBoxLayout()
        self._skip_verify = QCheckBox(tr("connect.skip_ssl", "Skip SSL verify"))
        self._skip_verify.setFont(_MONO)
        chk_row.addWidget(self._skip_verify)

        chk_row.addStretch()

        self._remember = QCheckBox(tr("connect.remember", "Remember"))
        self._remember.setFont(_MONO)
        self._remember.setChecked(bool(saved.get("last_token", "")))
        chk_row.addWidget(self._remember)

        cw = QWidget()
        cw.setLayout(chk_row)
        cw.setFixedWidth(form_w)
        form.addWidget(cw, alignment=Qt.AlignmentFlag.AlignHCenter)

        form.addSpacing(4)

        pref_row = QHBoxLayout()
        pref_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pref_row.setSpacing(0)
        self._lang_en = QPushButton(tr("connect.lang_en", "EN"))
        self._lang_en.setFont(_MONO_BOLD)
        self._lang_en.setFixedWidth(50)
        self._lang_en.setFixedHeight(28)
        self._lang_en.setCheckable(True)
        self._lang_en.clicked.connect(lambda: self._set_lang("en"))
        pref_row.addWidget(self._lang_en)
        self._lang_zh = QPushButton(tr("connect.lang_zh", "简体"))
        self._lang_zh.setFont(_MONO_BOLD)
        self._lang_zh.setFixedWidth(50)
        self._lang_zh.setFixedHeight(28)
        self._lang_zh.setCheckable(True)
        self._lang_zh.clicked.connect(lambda: self._set_lang("zh_CN"))
        pref_row.addWidget(self._lang_zh)

        theme_lbl = QLabel(tr("connect.theme", "Theme"))
        theme_lbl.setFont(_MONO)
        theme_lbl.setStyleSheet("color: #888;")
        theme_lbl.setContentsMargins(10, 0, 4, 0)
        pref_row.addWidget(theme_lbl)

        self._theme_combo = QComboBox()
        self._theme_combo.setFont(_MONO)
        self._theme_combo.setFixedWidth(100)
        self._theme_combo.setFixedHeight(26)
        theme_mgr = self.parent().theme_mgr if hasattr(self.parent(), "theme_mgr") else None
        if theme_mgr:
            for name in theme_mgr.names():
                self._theme_combo.addItem(name.capitalize(), name)
            self._theme_combo.setCurrentText(theme_mgr.current.capitalize())
            self._theme_combo.currentIndexChanged.connect(
                lambda idx: theme_mgr.apply(self._theme_combo.itemData(idx))
            )
        pref_row.addWidget(self._theme_combo)

        pw = QWidget()
        pw.setLayout(pref_row)
        pw.setFixedWidth(form_w)
        form.addWidget(pw, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._sync_lang_buttons()

        form.addSpacing(4)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._connect_btn = QPushButton(tr("connect.connect_btn", "CONNECT"))
        self._connect_btn.setObjectName("connectBtn")
        self._connect_btn.setFont(_MONO_BOLD)
        self._connect_btn.setMinimumHeight(36)
        self._connect_btn.clicked.connect(self._do_connect)
        btn_row.addWidget(self._connect_btn)

        self._cancel_btn = QPushButton(tr("connect.cancel_btn", "CANCEL"))
        self._cancel_btn.setObjectName("cancelBtn")
        self._cancel_btn.setFont(_MONO_BOLD)
        self._cancel_btn.setMinimumHeight(36)
        self._cancel_btn.clicked.connect(self._cancel_connect)
        self._cancel_btn.setVisible(False)
        btn_row.addWidget(self._cancel_btn)

        bw = QWidget()
        bw.setLayout(btn_row)
        bw.setFixedWidth(form_w)
        form.addWidget(bw, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._progress = SplashScreen()
        self._progress.setFixedWidth(form_w)
        self._progress.setStyleSheet("background: transparent;")
        form.addWidget(self._progress, alignment=Qt.AlignmentFlag.AlignHCenter)

        form_widget = QWidget()
        form_widget.setLayout(form)
        form_widget.setFixedWidth(form_w)
        outer.addWidget(form_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        self._dragon_sep = QFrame()
        self._dragon_sep.setFrameShape(QFrame.Shape.VLine)
        self._dragon_sep.setFixedWidth(1)
        outer.addWidget(self._dragon_sep)

        self._dragon = QLabel(_DRAGON_ART)
        self._dragon.setFont(_MONO_DRAGON)
        outer.addWidget(self._dragon, alignment=Qt.AlignmentFlag.AlignCenter)

        self._dragon_sep.setFixedHeight(self._dragon.sizeHint().height())

        theme_mgr = self.parent().theme_mgr if hasattr(self.parent(), "theme_mgr") else None
        self._apply_dragon_theme(theme_mgr)
        if theme_mgr:
            theme_mgr.theme_changed.connect(self._on_theme_changed)

    def _apply_dragon_theme(self, theme_mgr):
        accent = theme_mgr.accent_color() if theme_mgr else "#00d4ff"
        self._dragon.setStyleSheet(f"color: {accent}; background: transparent;")
        self._dragon_sep.setStyleSheet(f"color: {accent}; background-color: {accent}; max-width: 1px;")

    def _on_theme_changed(self, theme_name):
        theme_mgr = self.parent().theme_mgr if hasattr(self.parent(), "theme_mgr") else None
        self._apply_dragon_theme(theme_mgr)

    #  Server history

    @staticmethod
    def _server_label(url):
        url = url.replace("wss://", "").replace("ws://", "")
        return url.split("/")[0]

    def _refresh_server_combo(self):
        self._server_combo.blockSignals(True)
        self._server_combo.clear()
        self._server_combo.addItem(tr("connect.quick_connect", "\u2014 Quick Connect \u2014"), "")
        self._server_combo.insertSeparator(1)
        saved = load_state().get("saved_servers", [])
        current_url = self._url.text().strip() if hasattr(self, "_url") else ""
        current_idx = -1
        for i, entry in enumerate(saved):
            url = entry.get("url", "")
            label = entry.get("label") or self._server_label(url)
            self._server_combo.addItem(label, url)
            if url == current_url:
                current_idx = i + 2  # +2 for default item + separator
        if current_idx >= 0:
            self._server_combo.setCurrentIndex(current_idx)
        self._server_combo.blockSignals(False)

    def _on_server_selected(self, idx):
        url = self._server_combo.itemData(idx)
        if not url:
            return
        saved = load_state().get("saved_servers", [])
        for entry in saved:
            if entry.get("url") == url:
                self._url.setText(url)
                self._username.setText(entry.get("username", ""))
                token = entry.get("token", "")
                self._token.setText(token)
                self._remember.setChecked(bool(token))
                break

    def _save_server(self, url, username, token):
        saved = list(load_state().get("saved_servers", []))
        label = self._server_label(url)
        entry = {"url": url, "username": username, "token": token, "label": label}
        # Remove existing entry with same URL, then prepend
        saved = [e for e in saved if e.get("url") != url]
        saved.insert(0, entry)
        # Keep max 10 entries
        saved = saved[:10]
        save_state({"saved_servers": saved})

    def _remove_server(self):
        idx = self._server_combo.currentIndex()
        url = self._server_combo.itemData(idx)
        if not url:
            return
        saved = list(load_state().get("saved_servers", []))
        saved = [e for e in saved if e.get("url") != url]
        save_state({"saved_servers": saved})
        self._refresh_server_combo()
        self._progress.clear_stages()
        self._progress.add_stage(tr("connect.server_removed", "Server removed"), "info")
        QTimer.singleShot(2000, self._progress.clear_stages)

    def animate_in(self):
        pass

    def _toggle_token_visibility(self):
        if self._token.echoMode() == QLineEdit.EchoMode.Password:
            self._token.setEchoMode(QLineEdit.EchoMode.Normal)
            self._token_toggle.setText(tr("connect.token_hide", "HIDE"))
        else:
            self._token.setEchoMode(QLineEdit.EchoMode.Password)
            self._token_toggle.setText(tr("connect.token_show", "SHOW"))

    def _cancel_connect(self):
        if self._connecting_api:
            self._connecting_api.disconnect()
            self._connecting_api = None
        self._cancel_btn.setVisible(False)
        self._connect_btn.setText(tr("connect.connect_btn", "CONNECT"))
        self._connect_btn.setEnabled(True)
        self._progress.clear_stages()
        self._progress.add_stage(tr("connect.cancelled", "\u201cThis is the way the world ends\u201d"), "info")

    def _do_connect(self):
        url = self._url.text().strip()
        token = self._token.text().strip()
        username = self._username.text().strip()
        verify_ssl = not self._skip_verify.isChecked()

        if not token:
            self._progress.clear_stages()
            self._progress.add_stage(tr("connect.token_required", "Token is required"), "fail")
            return

        self._progress.clear_stages()
        self._progress.add_stage('\u201cWhen the Lamb of God spoke, there was Silence in Heaven for about half an hour\u201d', "busy")
        self._progress.add_stage('\u201cAnd the light shineth in darkness; and the darkness comprehended it not\u201d', "busy")

        self._connect_btn.setText(tr("connect.connecting_btn", "CONNECTING..."))
        self._connect_btn.setEnabled(False)
        self._cancel_btn.setVisible(True)

        QApplication.processEvents()

        api = PandragonAPI(url)
        self._connecting_api = api
        auth_error = [None]

        def _on_auth_error(err):
            auth_error[0] = err

        api.connection_error.connect(_on_auth_error)

        if not api.connect(token, username, ssl_verify=verify_ssl):
            msg = auth_error[0] or tr("connect.failed_auth", "Failed to authenticate")
            self._progress.clear_stages()
            self._progress.add_stage(msg, "fail")
            self._progress.add_stage(tr("connect.check_details", "> Check connection details"), "info")
            self._connect_btn.setText(tr("connect.connect_btn", "CONNECT"))
            self._connect_btn.setEnabled(True)
            self._cancel_btn.setVisible(False)
            self._connecting_api = None
            return

        self._progress.update_stage(0, "ok", '\u201cI am become Death, the destroyer of worlds\u201d')
        self._progress.update_stage(1, "ok", '\u201cThe fault, dear Brutus, is not in our stars, but in ourselves\u201d')
        self._progress.add_stage('\u201cZzzzzzzzzzzzz...\u201d', "ok")

        _updates = {"last_url": url, "last_username": username}
        if self._remember.isChecked():
            _updates["last_token"] = token
        else:
            _updates["last_token"] = ""
        save_state(_updates)
        saved_token = token if self._remember.isChecked() else ""
        self._save_server(url, username, saved_token)

        self._connecting_api = None
        QTimer.singleShot(300, lambda: self._on_connected(api))

    #  Language toggle on login screen

    def _sync_lang_buttons(self):
        t = TranslationManager.instance()
        curr = t.current_language
        self._lang_en.setChecked(curr == "en")
        self._lang_zh.setChecked(curr == "zh_CN")

    def _set_lang(self, code):
        TranslationManager.instance().set_language(code)
        self._sync_lang_buttons()
        self._refresh_connect_panel()

    def _refresh_connect_panel(self):
        self._title.setText(tr("connect.title", "PANDRAGON"))
        self._subtitle.setText(tr("connect.subtitle", "serexp . FGL"))
        self._url.setPlaceholderText(tr("connect.url_placeholder", "WebSocket URL"))
        self._username.setPlaceholderText(tr("connect.username_placeholder", "Username"))
        self._token.setPlaceholderText(tr("connect.token_placeholder", "Token (required)"))
        self._token_toggle.setText(
            tr("connect.token_hide", "HIDE")
            if self._token.echoMode() == QLineEdit.EchoMode.Normal
            else tr("connect.token_show", "SHOW")
        )
        self._skip_verify.setText(tr("connect.skip_ssl", "Skip SSL verify"))
        self._remember.setText(tr("connect.remember", "Remember"))
        self._connect_btn.setText(tr("connect.connect_btn", "CONNECT"))
        self._cancel_btn.setText(tr("connect.cancel_btn", "CANCEL"))
        self._refresh_server_combo()


class MainWindow(QMainWindow):
    """Main application window with embedded connect panel and tabbed interface."""

    def __init__(self, theme_mgr: ThemeManager):
        super().__init__()
        self.theme_mgr = theme_mgr
        self.api: PandragonAPI = None
        self._splash_done = False
        self._tabs = None
        self._tab_labels = []
        self._connected_state = (False, None)

        # Post-connect UI elements (created in _on_connected)
        self._status_bar_widgets = []
        self._status_indicator = None
        self._operator_label = None
        self._quip_timer = None
        self._quip_label = None
        self._quip_idx = 0

        self.setWindowTitle(tr("window.title", "Pandragon Operator Console"))

        self._stack = QStackedWidget()

        self._splash = StartSplash(self)
        self._splash.finished.connect(self._on_splash_done)
        self._stack.addWidget(self._splash)

        self._connect_panel = ConnectPanel(self._on_connected, self)
        self._stack.addWidget(self._connect_panel)

        self._tabs_container = QWidget()
        self._stack.addWidget(self._tabs_container)
        self._tab_layout = QVBoxLayout(self._tabs_container)
        self._tab_layout.setContentsMargins(0, 0, 0, 0)

        self._stack.setCurrentIndex(0)
        self.setCentralWidget(self._stack)

        self.resize(640, 420)

    #  Disconnect / Reconnect 

    def _cycle_quip(self):
        self._quip_idx = (self._quip_idx + 1) % len(_STATUS_QUIPS)
        self._quip_label.setText(tr(_STATUS_QUIP_KEYS[self._quip_idx], _STATUS_QUIPS[self._quip_idx]))

    def _disconnect(self):
        if self.api:
            self.api.disconnect()
            self.api = None

        if self._quip_timer:
            self._quip_timer.stop()

        for w in self._status_bar_widgets:
            try:
                self.statusBar().removeWidget(w)
                w.deleteLater()
            except Exception:
                pass
        self._status_bar_widgets.clear()
        self._status_indicator = None
        self._operator_label = None
        self.statusBar().clearMessage()

        while self._tab_layout.count():
            item = self._tab_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._connect_panel = ConnectPanel(self._on_connected, self)
        self._stack.insertWidget(1, self._connect_panel)
        self._stack.setCurrentIndex(1)
        self.resize(680, 420)
        self.setWindowTitle(tr("window.title", "Pandragon Operator Console"))

    #  Splash / transitions 

    def _on_splash_done(self):
        if self._splash_done:
            return
        self._splash_done = True
        self.resize(680, 420)
        self._crossfade(0, 1, callback=self._after_connect_fade)

    def _after_connect_fade(self):
        self._stack.removeWidget(self._splash)
        self._splash.deleteLater()
        self._connect_panel.animate_in()

    def _crossfade(self, old_idx, new_idx, duration=300, callback=None):
        old_widget = self._stack.widget(old_idx)
        new_widget = self._stack.widget(new_idx)

        if not old_widget or not new_widget:
            return

        new_widget.show()
        new_widget.setWindowOpacity(0.0)
        self._stack.setCurrentIndex(new_idx)

        self._fade_old = QPropertyAnimation(old_widget, b"windowOpacity")
        self._fade_old.setDuration(duration)
        self._fade_old.setStartValue(1.0)
        self._fade_old.setEndValue(0.0)
        self._fade_old.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._fade_new = QPropertyAnimation(new_widget, b"windowOpacity")
        self._fade_new.setDuration(duration)
        self._fade_new.setStartValue(0.0)
        self._fade_new.setEndValue(1.0)
        self._fade_new.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._crossfade_group = QParallelAnimationGroup(self)
        self._crossfade_group.addAnimation(self._fade_old)
        self._crossfade_group.addAnimation(self._fade_new)

        if callback:
            self._crossfade_group.finished.connect(callback)

        self._crossfade_group.start()

    def _on_connected(self, api):
        self.api = api

        self._stack.removeWidget(self._connect_panel)
        self._connect_panel.deleteLater()

        tabs = QTabWidget()
        self._tabs = tabs

        from PyQt6.QtWidgets import QSplitter
        beacon_split = QSplitter(Qt.Orientation.Horizontal)

        self.beacon_table = BeaconTableWidget(api, self)
        self.beacon_detail = BeaconDetailWidget(api, self)

        beacon_split.addWidget(self.beacon_table)
        beacon_split.addWidget(self.beacon_detail)
        beacon_split.setStretchFactor(0, 2)
        beacon_split.setStretchFactor(1, 1)

        self.task_queue = TaskQueueWidget(api, self.beacon_table, self)
        self.beacon_table.task_queue = self.task_queue

        self.graph_widget = BeaconGraphWidget(api, self)

        self.config_builder = ConfigBuilderWidget(self)
        self.config_builder.set_api(api)

        self.bof_repo = BOFRepositoryWidget(api, self)

        self.options_widget = OptionsWidget(self._disconnect, self.theme_mgr, self)

        self._tab_labels = []  # (tr_key, default, index)
        _tab_defs = [
            (beacon_split,    "tab.beacons",        "Beacons"),
            (self.task_queue, "tab.task_queue",     "Task Queue"),
            (self.graph_widget, "tab.pivot_graph",  "Pivot Graph"),
            (self.config_builder, "tab.config_builder", "Config Builder"),
            (self.bof_repo, "tab.bof_repository",   "BOF Repository"),
            (self.options_widget, "tab.options",    "Options"),
        ]
        for widget, key, default in _tab_defs:
            idx = tabs.addTab(widget, tr(key, default))
            self._tab_labels.append((key, default, idx))

        self._tab_layout.addWidget(tabs)

        self.notifications = NotificationOverlay(self)
        self.beacon_table.set_notification_overlay(self.notifications)
        self.beacon_detail.set_notification_overlay(self.notifications)
        self.task_queue.set_notification_overlay(self.notifications)
        self.graph_widget.set_notification_overlay(self.notifications)
        self.bof_repo.set_notification_overlay(self.notifications)

        self._build_post_connect_ui()
        self._wire_events()
        self._set_connection_status(True)

        self._crossfade(1, 2, duration=400, callback=self._after_tabs_fade)
        self.beacon_table.refresh()

    def _after_tabs_fade(self):
        QTimer.singleShot(0, lambda: self.resize(1280, 800))

    def _build_post_connect_ui(self):
        """Build status bar - only after connection. No menu bar."""
        sb = self.statusBar()

        # Left side: status + operator (addWidget = left-aligned)
        self._status_indicator = QLabel(tr("window.status_disconnected", "[DISCONNECTED]"))
        self._status_indicator.setFont(_MONO_BOLD)
        self._status_indicator.setStyleSheet("color: #ffaa00;")
        sb.addWidget(self._status_indicator)
        self._status_bar_widgets.append(self._status_indicator)

        self._operator_label = QLabel("")
        self._operator_label.setFont(_MONO)
        self._operator_label.setStyleSheet("color: #888;")
        sb.addWidget(self._operator_label)
        self._status_bar_widgets.append(self._operator_label)

        # Right side: cycling quip + branding (permanent = right-aligned)
        sep1 = QLabel("  |  ")
        sep1.setStyleSheet("color: #444;")
        sb.addPermanentWidget(sep1)
        self._status_bar_widgets.append(sep1)

        self._quip_label = QLabel(tr(_STATUS_QUIP_KEYS[0], _STATUS_QUIPS[0]))
        self._quip_label.setFont(_MONO)
        self._quip_label.setStyleSheet("color: #555;")
        sb.addPermanentWidget(self._quip_label)
        self._status_bar_widgets.append(self._quip_label)

        sep2 = QLabel("  |  ")
        sep2.setStyleSheet("color: #444;")
        sb.addPermanentWidget(sep2)
        self._status_bar_widgets.append(sep2)

        brand = QLabel(tr("window.branding", "PANDRAGON . serexp / FGL"))
        brand.setFont(_MONO_BOLD)
        brand.setStyleSheet("color: #666;")
        sb.addPermanentWidget(brand)
        self._status_bar_widgets.append(brand)

        # Rotating status quips
        self._quip_timer = QTimer(self)
        self._quip_timer.timeout.connect(self._cycle_quip)
        self._quip_timer.start(8000)
        self._quip_idx = 0

    def _on_graph_node_selected(self, beacon_id):
        tabs = self._tabs
        if tabs:
            tabs.setCurrentIndex(0)
        self.beacon_table.select_beacon_by_id(beacon_id)
        self.beacon_detail.update_beacon(beacon_id)

    def _wire_events(self):
        self.beacon_table.beacon_selected.connect(self.beacon_detail.update_beacon)
        self.graph_widget.node_selected.connect(self._on_graph_node_selected)

        self.api.beacon_output.connect(self.beacon_detail.handle_beacon_output)
        self.api.beacon_activity.connect(self._on_beacon_activity)
        self.api.beacon_removed.connect(self._on_beacon_removed)

        self.api.connected.connect(
            lambda: (
                self._set_connection_status(True),
                self.notifications.success(tr("notification.connected", "Connected to teamserver"), 3000),
            )
        )
        self.api.disconnected.connect(
            lambda: (
                self._set_connection_status(False),
                self.notifications.warning(tr("notification.disconnected", "Disconnected from teamserver - reconnecting..."), 0),
            )
        )
        self.api.connection_error.connect(
            lambda err: (
                self._set_connection_status(False, err),
                self.notifications.error(tr("notification.connection_error", "Connection error: {error}", error=err), 0),
            )
        )

        self.api.operator_joined.connect(self._on_operator_joined)
        self.api.operator_left.connect(self._on_operator_left)

        TranslationManager.instance().language_changed.connect(self._on_language_changed)

    def _on_language_changed(self):
        t = TranslationManager.instance()
        save_state({"last_language": t.current_language})

        # Update tab labels
        tabs = self._tabs
        if tabs:
            for key, default, idx in self._tab_labels:
                tabs.setTabText(idx, tr(key, default))

        # Refresh window title and status indicator
        self._set_connection_status(*self._connected_state if hasattr(self, '_connected_state') else (False, None))

    def _set_connection_status(self, connected, error=None):
        self._connected_state = (connected, error)
        if connected:
            self._status_indicator.setText(tr("window.status_connected", "[CONNECTED]"))
            self._status_indicator.setStyleSheet("color: #8f8;")
            self.setWindowTitle(tr("window.title_connected", "Pandragon Operator Console [CONNECTED]"))
        elif error:
            self._status_indicator.setText(tr("window.status_error", "[ERROR]"))
            self._status_indicator.setStyleSheet("color: #f44;")
            self.setWindowTitle(tr("window.title_error", "Pandragon Operator Console [ERROR]"))
        else:
            self._status_indicator.setText(tr("window.status_disconnected", "[DISCONNECTED]"))
            self._status_indicator.setStyleSheet("color: #fa0;")
            self.setWindowTitle(tr("window.title_disconnected", "Pandragon Operator Console [DISCONNECTED]"))

    def _on_operator_joined(self, username):
        self._operator_label.setText(tr("status.operator_joined", "  {username} joined", username=username))
        self.notifications.info(tr("notification.operator_joined", "Operator joined: {username}", username=username), 5000)
        QTimer.singleShot(5000, lambda: self._operator_label.setText(""))

    def _on_operator_left(self, username):
        self._operator_label.setText(tr("status.operator_left", "  {username} left", username=username))
        self.notifications.info(tr("notification.operator_left", "Operator left: {username}", username=username), 5000)
        QTimer.singleShot(5000, lambda: self._operator_label.setText(""))

    def _on_beacon_activity(self, bid, data):
        self.beacon_table.refresh()
        self.beacon_detail.update_beacon(
            self.beacon_table.get_selected_beacon_id()
        )
        self.task_queue.handle_beacon_activity(bid)

    def _on_beacon_removed(self, bid):
        self.beacon_table.refresh()
        if self.beacon_detail.current_beacon_id == bid:
            self.beacon_detail.update_beacon(None)


#  Application Entry 

def main(accept_responsibility=False):
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # Initialize translations
    saved_state = load_state()
    tmanager = TranslationManager.instance()
    lang = saved_state.get("last_language", "en")
    tmanager.load(lang)

    if not accept_responsibility:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(tr("eula.title", "Authorized Use Only"))
        msg.setText(tr("eula.message",
            "Pandragon Framework, Authorized Use Only\n\n"
            "This framework is intended exclusively for:\n"
            "  \u2022  Authorized penetration testing with written permission\n"
            "     from the target system owner(s)\n"
            "  \u2022  Personal security research on systems you own or have\n"
            "     explicit permission to test\n"
            "  \u2022  Academic research and cybersecurity education strictly\n"
            "     within dedicated, isolated laboratory networks\n\n"
            "Use in production environments, public networks, or live\n"
            "targets without written authorization is strictly forbidden.\n"
            "The authors disclaim all liability for misuse.\n\n"
            "Do no evil."
        ))
        msg.setStandardButtons(QMessageBox.StandardButton.Yes |
                               QMessageBox.StandardButton.No)
        msg.button(QMessageBox.StandardButton.Yes).setText(tr("eula.agree", "I Agree"))
        msg.button(QMessageBox.StandardButton.No).setText(tr("eula.decline", "I Decline"))
        if msg.exec() != QMessageBox.StandardButton.Yes:
            sys.exit(0)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(224, 224, 224))
    palette.setColor(QPalette.ColorRole.Base, QColor(37, 37, 37))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(40, 40, 40))
    palette.setColor(QPalette.ColorRole.Text, QColor(224, 224, 224))
    palette.setColor(QPalette.ColorRole.Button, QColor(42, 42, 42))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(224, 224, 224))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 68, 68))
    palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
    app.setPalette(palette)

    theme = ThemeManager(app)

    window = MainWindow(theme)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
