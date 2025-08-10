import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox, QSplitter,
    QPlainTextEdit, QWidget, QHBoxLayout, QLineEdit, QPushButton, QLabel
)
from PyQt6.QtGui import QAction, QKeySequence, QTextCursor, QIcon
from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSignal, QEvent
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage

# --- Okno dialogowe wyszukiwania ---
class FindDialog(QWidget):
    """
    Niemodalne okno dialogowe do wyszukiwania tekstu w edytorze kodu.
    Emituje sygnały, gdy użytkownik chce znaleźć następne/poprzednie wystąpienie.
    """
    # Sygnał: (tekst_do_znalezienia, kierunek_w_dół)
    find_requested = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Znajdź tekst")
        self.setWindowFlags(Qt.WindowType.Tool) # Okno narzędziowe, nie blokuje głównego

        layout = QHBoxLayout(self)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Wpisz szukany tekst...")
        layout.addWidget(self.search_input)

        # Użycie ikon dla lepszego wyglądu
        style = self.style()
        icon_up = style.standardIcon(style.StandardPixmap.SP_ArrowUp)
        icon_down = style.standardIcon(style.StandardPixmap.SP_ArrowDown)

        self.btn_down = QPushButton(icon_down, "W dół", self)
        self.btn_up = QPushButton(icon_up, "W górę", self)

        layout.addWidget(self.btn_up)
        layout.addWidget(self.btn_down)

        self.btn_down.clicked.connect(self.find_down)
        self.btn_up.clicked.connect(self.find_up)
        self.search_input.returnPressed.connect(self.find_down)

    def find_down(self):
        text = self.search_input.text()
        if text:
            self.find_requested.emit(text, True)

    def find_up(self):
        text = self.search_input.text()
        if text:
            self.find_requested.emit(text, False)

    def keyPressEvent(self, event):
        # Zamknięcie okna klawiszem Escape
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

# --- Główna klasa edytora ---
class HtmlEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_file_path = None
        self._is_updating_code = False
        self._is_updating_web = False
        self.find_dialog = None

        # Inicjalizacja UI
        self._setup_ui()
        self._setup_menus()
        self._setup_signals()

    def _setup_ui(self):
        """Konfiguracja głównego interfejsu użytkownika."""
        self.setWindowTitle("Nowoczesny Edytor HTML")
        self.setGeometry(100, 100, 1366, 768)

        # Główny kontener z podziałką
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(self.splitter)

        # Widok wizualny (lewy panel)
        self.web_view = QWebEngineView()
        self.web_page = self.web_view.page()
        # Edycję włączymy po załadowaniu strony, używając sygnału loadFinished.
        self.web_page.loadFinished.connect(self.make_content_editable)

        # Edytor kodu (prawy panel)
        self.code_editor = QPlainTextEdit()
        self.code_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap) # Wyłącza zawijanie wierszy dla kodu
        font = self.code_editor.font()
        font.setFamily("Courier New")
        font.setPointSize(10)
        self.code_editor.setFont(font)

        self.splitter.addWidget(self.web_view)
        self.splitter.addWidget(self.code_editor)
        self.splitter.setSizes([self.width() // 2, self.width() // 2]) # Równy podział

        # Pasek statusu do wyświetlania komunikatów
        self.statusBar()

    def _setup_menus(self):
        """Konfiguracja menu i paska narzędzi."""
        menu_bar = self.menuBar()

        # --- Menu Plik ---
        file_menu = menu_bar.addMenu("&Plik")

        open_action = QAction(QIcon.fromTheme("document-open"), "&Otwórz...", self)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        open_action.triggered.connect(self.open_file)
        file_menu.addAction(open_action)

        save_action = QAction(QIcon.fromTheme("document-save"), "&Zapisz", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.triggered.connect(self.save_file)
        file_menu.addAction(save_action)

        save_as_action = QAction(QIcon.fromTheme("document-save-as"), "Zapisz &jako...", self)
        save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as_action.triggered.connect(self.save_file_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        exit_action = QAction("&Wyjście", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # --- Menu Widok ---
        view_menu = menu_bar.addMenu("&Widok")

        self.toggle_view_action = QAction("Pokaż/Ukryj edytor kodu", self, checkable=True)
        self.toggle_view_action.setChecked(True)
        self.toggle_view_action.triggered.connect(self.toggle_dual_view)
        view_menu.addAction(self.toggle_view_action)

        fullscreen_action = QAction("Pełny ekran", self, checkable=True)
        fullscreen_action.setShortcut(QKeySequence("F11"))
        fullscreen_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(fullscreen_action)

        # --- Menu Edycja ---
        edit_menu = menu_bar.addMenu("&Edycja")
        find_action = QAction(QIcon.fromTheme("edit-find"), "&Znajdź...", self)
        find_action.setShortcut(QKeySequence.StandardKey.Find)
        find_action.triggered.connect(self.show_find_dialog)
        edit_menu.addAction(find_action)


    def _setup_signals(self):
        """Konfiguracja sygnałów i timerów do synchronizacji."""
        # Synchronizacja: Zmiany w kodzie aktualizują widok wizualny
        self.code_editor.textChanged.connect(self.update_web_view_from_code)

        # Synchronizacja: Kliknięcie w widoku wizualnym przenosi kursor w kodzie
        self.web_page.runJavaScript(
            """
            document.addEventListener('click', (event) => {
                let py_channel = new QWebChannel(qt.webChannelTransport, function(channel) {
                    window.py_bridge = channel.objects.bridge;
                });
                if (window.py_bridge) {
                    window.py_bridge.elementClicked(event.target.outerHTML);
                }
            });
            """
        )

    def make_content_editable(self, ok):
        """Uruchamia edycję w widoku web po załadowaniu strony."""
        if ok:
            # Użycie designMode to standardowy sposób na włączenie edycji całego dokumentu.
            self.web_page.runJavaScript("document.designMode = 'on';")

    # --- Funkcje obsługi plików ---
    def _inject_base_tag(self, html_content, base_url_str):
        """Wstrzykuje tag <base> do sekcji <head> dokumentu HTML."""
        if not base_url_str:
            return html_content

        # Upewniamy się, że URL kończy się ukośnikiem
        if not base_url_str.endswith('/'):
            base_url_str += '/'

        base_tag = f'<base href="{base_url_str}">'

        # Znajdź pozycję <head> (ignorując wielkość liter)
        head_pos = html_content.lower().find('<head>')
        if head_pos != -1:
            # Wstaw tag <base> zaraz po otwarciu <head>
            insert_pos = head_pos + len('<head>')
            return f"{html_content[:insert_pos]}\n{base_tag}\n{html_content[insert_pos:]}"
        else:
            # Jeśli nie ma <head>, utwórz go i wstaw na początku
            return f"<head>\n{base_tag}\n</head>\n{html_content}"

    def open_file(self):
        """Otwiera plik HTML i ładuje jego zawartość."""
        path, _ = QFileDialog.getOpenFileName(self, "Otwórz plik HTML", "", "Pliki HTML (*.html *.htm)")
        if path:
            self.current_file_path = path
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()

                self._is_updating_web = True
                self._is_updating_code = True

                # Ustawienie base URL jest kluczowe dla ładowania CSS/JS
                dir_path = os.path.dirname(path)
                base_url = QUrl.fromLocalFile(dir_path)

                # Wstrzykujemy tag <base> do podglądu, ale nie do edytora kodu
                html_for_view = self._inject_base_tag(content, base_url.toString())

                self.web_page.setHtml(html_for_view, baseUrl=base_url)
                self.code_editor.setPlainText(content)
                self.statusBar().showMessage(f"Otworzono: {path}", 5000)

            except Exception as e:
                QMessageBox.critical(self, "Błąd", f"Nie można otworzyć pliku:\n{e}")
            finally:
                self._is_updating_web = False
                self._is_updating_code = False


    def save_file(self):
        """Inicjuje proces zapisu bieżącego pliku."""
        if self.current_file_path is None:
            self.save_file_as()
        else:
            # Pobierz aktualny HTML i zapisz go w callbacku
            self.web_page.toHtml(lambda html: self._complete_save(html, self.current_file_path))

    def save_file_as(self):
        """Inicjuje proces zapisu do nowego pliku."""
        path, _ = QFileDialog.getSaveFileName(self, "Zapisz plik jako", "", "Pliki HTML (*.html *.htm)")
        if path:
            self.current_file_path = path
            # Pobierz aktualny HTML i zapisz go w callbacku
            self.web_page.toHtml(lambda html: self._complete_save(html, path))

    def _complete_save(self, html, path):
        """Kończy operację zapisu po otrzymaniu HTML z web view."""
        # Najpierw zaktualizuj edytor kodu, który jest naszym źródłem prawdy
        self._is_updating_code = True
        self.code_editor.setPlainText(html)
        self._is_updating_code = False

        # Teraz zapisz zawartość z edytora kodu
        self._save_to_path(path)

    def _save_to_path(self, path):
        """Wewnętrzna funkcja zapisująca kod do podanej ścieżki."""
        try:
            # Zawsze zapisujemy zawartość z edytora kodu jako źródło prawdy
            content = self.code_editor.toPlainText()
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            self.statusBar().showMessage(f"Zapisano plik: {path}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie można zapisać pliku:\n{e}")

    # --- Funkcje synchronizacji i widoku ---
    def update_web_view_from_code(self):
        """Aktualizuje podgląd na podstawie zmian w edytorze kodu."""
        if self._is_updating_code:
            return

        self._is_updating_web = True
        current_html = self.code_editor.toPlainText()

        html_for_view = current_html
        base_url = QUrl()
        if self.current_file_path:
            dir_path = os.path.dirname(self.current_file_path)
            base_url = QUrl.fromLocalFile(dir_path)
            html_for_view = self._inject_base_tag(current_html, base_url.toString())

        self.web_page.setHtml(html_for_view, baseUrl=base_url)
        self._is_updating_web = False

    def element_clicked(self, outer_html):
        """Slot wywoływany przez JS, gdy element w widoku web jest kliknięty."""
        # Upraszczamy, biorąc pierwsze 100 znaków, aby uniknąć problemów z dużymi elementami
        search_text = outer_html.strip()
        if len(search_text) > 100:
            search_text = search_text[:100]

        cursor = self.code_editor.document().find(search_text)
        if not cursor.isNull():
            self.code_editor.setTextCursor(cursor)
            self.code_editor.setFocus()

    def toggle_dual_view(self, checked):
        """Pokazuje lub ukrywa panel edytora kodu."""
        self.code_editor.setVisible(checked)

    def toggle_fullscreen(self, checked):
        """Przełącza tryb pełnoekranowy."""
        if checked:
            self.showFullScreen()
        else:
            self.showNormal()

    # --- Funkcje wyszukiwania ---
    def show_find_dialog(self):
        """Tworzy i pokazuje okno dialogowe wyszukiwania."""
        if not self.find_dialog:
            self.find_dialog = FindDialog(self)
            self.find_dialog.find_requested.connect(self.find_text)
        self.find_dialog.show()
        self.find_dialog.activateWindow()
        self.find_dialog.search_input.setFocus()

    def find_text(self, text, find_down):
        """Logika wyszukiwania tekstu w edytorze kodu."""
        if find_down:
            found = self.code_editor.find(text)
        else:
            found = self.code_editor.find(text, QTextDocument.FindFlag.FindBackward)

        if not found:
            # Jeśli nie znaleziono, spróbuj od początku/końca dokumentu
            cursor = self.code_editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start if find_down else QTextCursor.MoveOperation.End)
            self.code_editor.setTextCursor(cursor)
            found = self.code_editor.find(text, QTextDocument.FindFlag.FindBackward if not find_down else QTextDocument.FindFlag(0))

            if not found:
                self.statusBar().showMessage("Nie znaleziono tekstu.", 3000)
            else:
                 self.statusBar().showMessage("Przeszukano od początku/końca dokumentu.", 3000)
        else:
            self.statusBar().clearMessage()


    def closeEvent(self, event):
        """Obsługa zamknięcia aplikacji."""
        # Tutaj można dodać logikę pytania o zapisanie niezapisanych zmian
        reply = QMessageBox.question(self, 'Wyjście',
                                     "Czy na pewno chcesz zamknąć edytor?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                     QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    # Potrzebne do przekazywania obiektów Pythona do JavaScript (dla synchronizacji kliknięć)
    from PyQt6.QtWebChannel import QWebChannel

    editor = HtmlEditor()

    # Utworzenie mostu między Pythonem a JavaScriptem
    channel = QWebChannel(editor.web_page)
    editor.web_page.setWebChannel(channel)
    # Rejestracja obiektu 'editor' pod nazwą 'bridge' w JS
    channel.registerObject("bridge", editor)

    editor.show()
    sys.exit(app.exec())
