"""Dialog that walks the user through authorising their own Claude account.

Opens the Claude OAuth consent page in the browser, then accepts the
authorization code the user pastes back and exchanges it for tokens.  On success
it emits :pyattr:`logged_in` with the resolved credentials (already persisted to
the app's own cache).
"""
from __future__ import annotations

from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ..api import oauth
from ..api.oauth_login import LoginSession


class LoginDialog(QDialog):
    logged_in = pyqtSignal(object)  # OAuthCredentials

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Zaloguj się przez Claude")
        self.setModal(True)
        self.setMinimumWidth(480)
        self._session = LoginSession()
        self._build_ui()
        # Kick the browser open as soon as the dialog appears.
        self._open_browser()

    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(10)

        info = QLabel(
            "Otwarto stronę logowania Claude w przeglądarce.\n\n"
            "1.  Zaloguj się na swoje konto Claude (Pro / Max) i zatwierdź dostęp.\n"
            "2.  Skopiuj wyświetlony kod autoryzacyjny.\n"
            "3.  Wklej go poniżej i kliknij „Zaloguj”."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        reopen = QPushButton("Otwórz ponownie stronę logowania")
        reopen.clicked.connect(self._open_browser)
        root.addWidget(reopen)

        self.code = QLineEdit()
        self.code.setPlaceholderText("Wklej tutaj kod autoryzacyjny…")
        self.code.returnPressed.connect(self._on_confirm)
        root.addWidget(self.code)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Anuluj")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self.confirm = QPushButton("Zaloguj")
        self.confirm.setObjectName("Primary")
        self.confirm.clicked.connect(self._on_confirm)
        buttons.addWidget(self.confirm)
        root.addLayout(buttons)

    # ------------------------------------------------------------------ #
    def _open_browser(self) -> None:
        QDesktopServices.openUrl(QUrl(self._session.authorize_url()))
        self._set_status("Otwarto przeglądarkę — zaloguj się i wklej kod.", "#94a3b8")

    def _on_confirm(self) -> None:
        code = self.code.text().strip()
        if not code:
            self._set_status("Najpierw wklej kod autoryzacyjny.", "#ef4444")
            return
        self._set_status("Łączenie z Claude…", "#94a3b8")
        self.confirm.setEnabled(False)
        try:
            creds = self._session.exchange(code)
        except Exception as exc:
            self._set_status(f"Logowanie nie powiodło się. {exc}", "#ef4444")
            self.confirm.setEnabled(True)
            return

        oauth.save_login_credentials(creds)
        self._set_status("Zalogowano pomyślnie.", "#22c55e")
        self.logged_in.emit(creds)
        self.accept()

    def _set_status(self, text: str, color: str) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color};")
