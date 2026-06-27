"""Settings dialog — auth, display, polling, notifications and system options."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

from .. import constants
from ..api import oauth
from ..i18n import tr
from ..utils import autostart, encryption


class SettingsWindow(QDialog):
    applied = pyqtSignal()           # emitted after a successful Save
    restart_requested = pyqtSignal()  # user accepted restart after a language change

    def __init__(self, config, client, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.client = client
        self.setWindowTitle(tr("settings_title"))
        self.setMinimumWidth(420)
        self.setModal(False)
        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)

        root.addWidget(self._auth_group())
        root.addWidget(self._display_group())
        root.addWidget(self._polling_group())
        root.addWidget(self._notifications_group())
        root.addWidget(self._system_group())

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(tr("btn_cancel"))
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        save = QPushButton(tr("btn_save"))
        save.setObjectName("Primary")
        save.clicked.connect(self._on_save)
        buttons.addWidget(save)
        root.addLayout(buttons)

    def _auth_group(self) -> QGroupBox:
        box = QGroupBox(tr("grp_auth"))
        form = QFormLayout(box)

        self.auth_type = QComboBox()
        # OAuth first — the recommended default for Pro/Max subscribers.
        self.auth_type.addItem(tr("auth_oauth"), "oauth")
        self.auth_type.addItem(tr("auth_api_key"), "api_key")
        self.auth_type.addItem(tr("auth_demo"), "mock")
        self.auth_type.currentIndexChanged.connect(self._on_auth_changed)
        form.addRow(tr("auth_type"), self.auth_type)

        # OAuth status: which local credential we discovered (read-only).
        self.oauth_info = QLabel("")
        self.oauth_info.setWordWrap(True)
        self.oauth_info.setStyleSheet("color: #94a3b8; font-size: 11px;")
        form.addRow(tr("lbl_oauth_token"), self.oauth_info)

        # Account authorisation — anyone can log in to their own Claude account.
        login_row = QHBoxLayout()
        self.login_btn = QPushButton(tr("btn_login"))
        self.login_btn.clicked.connect(self._on_login)
        login_row.addWidget(self.login_btn, 1)
        self.logout_btn = QPushButton(tr("btn_logout"))
        self.logout_btn.clicked.connect(self._on_logout)
        login_row.addWidget(self.logout_btn)
        form.addRow(tr("lbl_account"), login_row)

        key_row = QHBoxLayout()
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText("sk-ant-...")
        key_row.addWidget(self.api_key, 1)
        self.show_key = QPushButton("👁")
        self.show_key.setObjectName("IconButton")
        self.show_key.setFixedSize(34, 34)
        self.show_key.setCheckable(True)
        self.show_key.toggled.connect(
            lambda on: self.api_key.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        key_row.addWidget(self.show_key)
        self.api_key_label = QLabel(tr("lbl_api_key"))
        form.addRow(self.api_key_label, key_row)

        self.model = QComboBox()
        for model_id, meta in constants.MODELS.items():
            self.model.addItem(meta["label"], model_id)
        form.addRow(tr("lbl_model_ping"), self.model)

        test_row = QHBoxLayout()
        self.test_btn = QPushButton(tr("btn_test"))
        self.test_btn.clicked.connect(self._on_test)
        test_row.addWidget(self.test_btn)
        self.test_result = QLabel("")
        self.test_result.setWordWrap(True)
        test_row.addWidget(self.test_result, 1)
        form.addRow("", test_row)
        return box

    def _display_group(self) -> QGroupBox:
        box = QGroupBox(tr("grp_display"))
        form = QFormLayout(box)

        op_row = QHBoxLayout()
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(30, 100)
        self.opacity_label = QLabel("95%")
        self.opacity.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"{v}%")
        )
        op_row.addWidget(self.opacity, 1)
        op_row.addWidget(self.opacity_label)
        form.addRow(tr("lbl_opacity"), op_row)

        self.always_on_top = QCheckBox(tr("chk_on_top"))
        form.addRow("", self.always_on_top)

        self.compact = QCheckBox(tr("chk_compact"))
        form.addRow("", self.compact)

        self.language = QComboBox()
        self.language.addItem(tr("lang_pl"), "pl")
        self.language.addItem(tr("lang_en"), "en")
        form.addRow(tr("lbl_language"), self.language)
        return box

    def _polling_group(self) -> QGroupBox:
        box = QGroupBox(tr("grp_polling"))
        form = QFormLayout(box)
        self.interval = QSpinBox()
        self.interval.setRange(constants.MIN_POLL_INTERVAL, constants.MAX_POLL_INTERVAL)
        self.interval.setSuffix(" s")
        form.addRow(tr("lbl_interval"), self.interval)
        self.smart = QCheckBox(tr("chk_smart"))
        form.addRow("", self.smart)
        return box

    def _notifications_group(self) -> QGroupBox:
        box = QGroupBox(tr("grp_notifications"))
        layout = QVBoxLayout(box)
        self.notify_enabled = QCheckBox(tr("chk_notify_enabled"))
        layout.addWidget(self.notify_enabled)
        self.notify_80 = QCheckBox(tr("chk_notify_80"))
        self.notify_90 = QCheckBox(tr("chk_notify_90"))
        self.notify_100 = QCheckBox(tr("chk_notify_100"))
        for cb in (self.notify_80, self.notify_90, self.notify_100):
            layout.addWidget(cb)
        return box

    def _system_group(self) -> QGroupBox:
        box = QGroupBox(tr("grp_system"))
        layout = QVBoxLayout(box)
        self.autostart_cb = QCheckBox(tr("chk_autostart"))
        layout.addWidget(self.autostart_cb)
        self.min_to_tray = QCheckBox(tr("chk_tray"))
        layout.addWidget(self.min_to_tray)
        return box

    # ------------------------------------------------------------------ #
    def _on_auth_changed(self, *_args) -> None:
        """Toggle the API-key field and refresh OAuth status when the mode changes."""
        mode = self.auth_type.currentData()
        is_api = mode == "api_key"
        self.api_key.setEnabled(is_api)
        self.api_key_label.setEnabled(is_api)
        self.show_key.setEnabled(is_api)
        is_oauth = mode == "oauth"
        self.login_btn.setEnabled(is_oauth)
        self.logout_btn.setEnabled(is_oauth and oauth.has_local_login())
        self._refresh_oauth_info()

    # -- account login / logout ----------------------------------------- #
    def _on_login(self) -> None:
        from .login_dialog import LoginDialog

        dlg = LoginDialog(self)
        dlg.logged_in.connect(self._on_logged_in)
        dlg.exec()

    def _on_logged_in(self, _creds) -> None:
        # A fresh login means OAuth — switch to it, persist, and re-poll now.
        self.auth_type.setCurrentIndex(max(0, self.auth_type.findData("oauth")))
        self.config.set("auth.auth_type", "oauth")
        self.config.save()
        self.logout_btn.setEnabled(True)
        self._refresh_oauth_info()
        self.applied.emit()

    def _on_logout(self) -> None:
        oauth.logout()
        self.logout_btn.setEnabled(False)
        self._refresh_oauth_info()
        self.applied.emit()

    def _refresh_oauth_info(self) -> None:
        """Show which local OAuth credential was discovered (best-effort)."""
        try:
            creds = oauth.load_credentials()
        except Exception:
            creds = None
        if creds:
            where = {
                "login": tr("src_login"),
                "monitor-cache": tr("src_login"),
                "refreshed": tr("src_refreshed"),
                "desktop-cache": tr("src_desktop"),
                "env": tr("src_env"),
            }.get(creds.source, creds.source)
            self.oauth_info.setText(
                tr("oauth_detected", plan=creds.plan_label(), where=where)
            )
            self.oauth_info.setStyleSheet("color: #22c55e; font-size: 11px;")
        else:
            self.oauth_info.setText(tr("oauth_not_found"))
            self.oauth_info.setStyleSheet("color: #ef4444; font-size: 11px;")

    def _load_values(self) -> None:
        idx = max(0, self.auth_type.findData(self.config.auth_type))
        self.auth_type.setCurrentIndex(idx)

        stored = encryption.load_api_key() or self.config.get("auth.api_key", "")
        self.api_key.setText(stored or "")
        self._on_auth_changed()

        midx = max(0, self.model.findData(self.config.model))
        self.model.setCurrentIndex(midx)

        self.opacity.setValue(int(self.config.opacity * 100))
        self.always_on_top.setChecked(self.config.always_on_top)
        self.compact.setChecked(self.config.compact)
        self.language.setCurrentIndex(max(0, self.language.findData(self.config.language)))

        self.interval.setValue(self.config.poll_interval)
        self.smart.setChecked(self.config.smart_polling)

        self.notify_enabled.setChecked(self.config.notifications_enabled)
        self.notify_80.setChecked(bool(self.config.get("notifications.threshold_80", True)))
        self.notify_90.setChecked(bool(self.config.get("notifications.threshold_90", True)))
        self.notify_100.setChecked(bool(self.config.get("notifications.threshold_100", True)))

        self.autostart_cb.setChecked(autostart.is_enabled())
        self.min_to_tray.setChecked(bool(self.config.get("system.minimize_to_tray", True)))

    # ------------------------------------------------------------------ #
    def _on_test(self) -> None:
        self.test_result.setText(tr("testing"))
        self.test_result.setStyleSheet("color: #94a3b8;")
        # Stash the typed key so the client can read it during the test.
        auth = self.auth_type.currentData()
        key = self.api_key.text().strip()
        ok, message = self.client.test_connection(api_key=key, auth_type=auth)
        self.test_result.setText(message)
        self.test_result.setStyleSheet(
            "color: #22c55e;" if ok else "color: #ef4444;"
        )

    def _on_save(self) -> None:
        old_language = self.config.language
        self.config.set("auth.auth_type", self.auth_type.currentData())
        self.config.set("auth.model", self.model.currentData())

        # Persist API key securely; clear the plaintext config fallback if stored.
        key = self.api_key.text().strip()
        secured = encryption.save_api_key(key)
        self.config.set("auth.api_key", "" if secured else key)

        self.config.set("display.opacity", self.opacity.value() / 100.0)
        self.config.set("display.always_on_top", self.always_on_top.isChecked())
        self.config.set("display.compact", self.compact.isChecked())
        self.config.set("display.language", self.language.currentData())

        self.config.set("polling.interval", self.interval.value())
        self.config.set("polling.smart_polling", self.smart.isChecked())

        self.config.set("notifications.enabled", self.notify_enabled.isChecked())
        self.config.set("notifications.threshold_80", self.notify_80.isChecked())
        self.config.set("notifications.threshold_90", self.notify_90.isChecked())
        self.config.set("notifications.threshold_100", self.notify_100.isChecked())

        self.config.set("system.minimize_to_tray", self.min_to_tray.isChecked())
        autostart.set_enabled(self.autostart_cb.isChecked())

        self.config.save()
        self.applied.emit()
        self.accept()

        # A language change needs a clean re-render of every widget — offer to
        # restart the app now (applies on next launch either way).
        if self.config.language != old_language:
            choice = QMessageBox.question(
                self.parent() or self,
                tr("lang_restart_title"),
                tr("lang_restart_body"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if choice == QMessageBox.StandardButton.Yes:
                self.restart_requested.emit()
