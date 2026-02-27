from qtpy.QtWidgets import (
    QWidget,
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QStyledItemDelegate,
    QListWidget,
    QAbstractItemView,
)
from qtpy.QtCore import Qt, QPoint
from qtpy.QtGui import QTextCursor, QFontMetrics


class PatternCompleter:
    """
    Mixin class that adds pattern completion to any text widget.

    Requirements for the widget:
    - Must have: text(), setText(), cursorPosition() or textCursor()
    - Must emit: textChanged signal
    - Must support: keyPressEvent override

    Usage:
        class MyLineEdit(QLineEdit, PatternCompleterMixin):
            def __init__(self, parent=None):
                super().__init__(parent)
                self.init_pattern_completer()
    """

    def init_pattern_completer(self, **kwargs):
        """
        Initialize the pattern completer system.

        Args:
            **kwargs: Global configuration options
                - min_width (int): Minimum popup width in pixels (default: 150)
                - max_width (int): Maximum popup width in pixels (default: 500)
                - visual_indicator (bool): Enable visual indicator globally (default: False)
                - case_sensitive (bool): Case sensitive completion (default: False)
                - auto_resize (bool): Auto-resize popup to content (default: True)
                - word_wrap (bool): Enable word wrap in popup (default: False)
        """
        self: QWidget  # Type hint for IDEs
        self.completers = {}
        self.active_pattern = None
        self.trigger_start_pos = -1
        self.inserting_completion = False
        self._is_destroyed = False

        # Global configuration with defaults
        self.global_config = {
            "min_width": kwargs.get("min_width", 150),
            "max_width": kwargs.get("max_width", 500),
            "visual_indicator": kwargs.get("visual_indicator", False),
            "case_sensitive": kwargs.get("case_sensitive", False),
            "auto_resize": kwargs.get("auto_resize", True),
            "word_wrap": kwargs.get("word_wrap", False),
        }

        # Single shared popup replaces per-pattern QCompleter instances
        self._popup = QListWidget(self)
        self._popup.setWindowFlags(Qt.WindowType.ToolTip)
        self._popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._popup.setFocusProxy(self)
        self._popup.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._popup.itemClicked.connect(
            lambda item: self._pattern_insert_completion(item.text())
        )
        self._popup.hide()

        # Connect to text changes
        if hasattr(self, "textChanged"):
            try:
                self.textChanged.connect(self._pattern_on_text_changed)
            except Exception as e:
                print(f"Error connecting textChanged signal: {e}")

    def add_completer(self, pattern, completions, **kwargs):
        """
        Add a completer for a specific trigger pattern.

        Args:
            pattern (str): Trigger string (e.g., '@', '#', '::')
            completions (list | callable): Static list of completion strings, or a
                callable ``(text_before_cursor: str, prefix: str) -> list[str]`` that
                returns candidates dynamically on every keystroke.
            **kwargs: Per-pattern configuration (overrides global config)
                - visual_indicator (bool): Show visual indicator for this pattern
                - case_sensitive (bool): Case sensitive completion
                - min_width (int): Minimum popup width
                - max_width (int): Maximum popup width
                - auto_resize (bool): Auto-resize popup
                - word_wrap (bool): Word wrap in popup
                - padding (int): Extra padding for width calculation (default: 20)
                - on_insert (callable): Custom insertion hook called instead of the
                    default replacement logic.  Signature:
                    ``(completion, text, trigger_pos, cursor_pos) -> (new_text, new_cursor_pos)``
        """
        on_insert = kwargs.pop('on_insert', None)

        config = {**self.global_config, **kwargs}

        self.completers[pattern] = {
            "completions": completions,
            "on_insert": on_insert,
            "config": config,
        }

    def update_completions(self, pattern, completions):
        """Update completion list for a pattern.

        ``completions`` may be a static list or a callable
        ``(text_before_cursor, prefix) -> list[str]``.  The popup is not updated
        until the next keystroke.
        """
        if pattern not in self.completers:
            return
        self.completers[pattern]["completions"] = completions

    def update_completer_config(self, pattern, **kwargs):
        """
        Update configuration for a specific pattern completer.

        Args:
            pattern (str): The pattern to update
            **kwargs: Configuration options to update.  ``on_insert`` is handled
                separately and stored directly on the completer entry rather than
                in the ``config`` sub-dict.
        """
        if pattern not in self.completers:
            return

        if 'on_insert' in kwargs:
            self.completers[pattern]['on_insert'] = kwargs.pop('on_insert')

        self.completers[pattern]["config"].update(kwargs)

    def set_global_config(self, **kwargs):
        """Update global configuration for all completers"""
        self.global_config.update(kwargs)

    def set_visual_indicator(self, enabled):
        """Enable/disable visual indicator globally"""
        self.global_config["visual_indicator"] = enabled

    def cleanup_pattern_completer(self):
        """Clean up completer resources"""
        # Disconnect text changed signal first
        if hasattr(self, "textChanged"):
            try:
                self.textChanged.disconnect(self._pattern_on_text_changed)
            except (TypeError, RuntimeError):
                pass

        # Clean up the shared popup
        if hasattr(self, '_popup'):
            try:
                self._popup.itemClicked.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._popup.hide()
            self._popup.deleteLater()

        self.completers.clear()

    def _get_candidates(self, pattern_config, text, cursor_pos, prefix):
        """Return completion candidates for the current prefix.

        Handles both callable and static-list completions, applying prefix
        filtering (case-aware) for static lists.
        """
        completions = pattern_config["completions"]
        config = pattern_config["config"]

        if callable(completions):
            return completions(text[:cursor_pos], prefix)

        case_sensitive = config.get("case_sensitive", False)
        if case_sensitive:
            return [c for c in completions if c.startswith(prefix)]
        else:
            return [c for c in completions if c.lower().startswith(prefix.lower())]

    def _show_popup(self, items, config):
        """Populate, size, and position the shared popup."""
        self._popup.clear()
        for item in items:
            self._popup.addItem(item)

        if not items:
            self._popup.hide()
            return

        # Word-wrap / elide settings
        word_wrap = config.get("word_wrap", False)
        self._popup.setWordWrap(word_wrap)
        self._popup.setTextElideMode(
            Qt.TextElideMode.ElideNone if not word_wrap else Qt.TextElideMode.ElideRight
        )

        # Auto-resize width to fit the widest item
        if config.get("auto_resize", True):
            fm = QFontMetrics(self._popup.font())
            padding = config.get("padding", 20)
            min_w = config.get("min_width", 150)
            max_w = config.get("max_width", 500)
            content_width = max(fm.horizontalAdvance(item) + padding for item in items)
            width = max(min_w, min(content_width, max_w))
        else:
            width = config.get("min_width", 150)

        # Height: fit content but cap at 260 px
        row_h = self._popup.sizeHintForRow(0) if self._popup.count() > 0 else 20
        height = min(len(items) * row_h, 260)

        self._popup.setFixedWidth(width)
        self._popup.setFixedHeight(height)

        # Position below the cursor
        if hasattr(self, "cursorRect"):
            # QTextEdit / QPlainTextEdit: cursorRect() gives cursor bounding box
            pos = self.mapToGlobal(self.cursorRect().bottomLeft())
        else:
            # QLineEdit: approximate cursor x via font metrics
            text, cursor_pos = self._get_text_and_cursor()
            fm_widget = QFontMetrics(self.font())
            pos = self.mapToGlobal(
                QPoint(fm_widget.horizontalAdvance(text[:cursor_pos]), self.height())
            )

        self._popup.move(pos)
        self._popup.setCurrentRow(0)
        self._popup.show()

    def _get_text_and_cursor(self):
        """Get text and cursor position (works for different widget types)"""
        text = self.toPlainText() if hasattr(self, "toPlainText") else self.text()

        if hasattr(self, "textCursor"):
            cursor_pos: QTextCursor = self.textCursor().position()
        else:
            cursor_pos = self.cursorPosition()

        return text, cursor_pos

    def _set_text_with_cursor(self, text, cursor_pos):
        """Set text and cursor position (works for different widget types)"""
        if hasattr(self, "setPlainText"):
            self.setPlainText(text)
            cursor: QTextCursor = self.textCursor()
            cursor.setPosition(min(cursor_pos, len(text)))
            self.setTextCursor(cursor)
        else:
            self.setText(text)
            self.setCursorPosition(min(cursor_pos, len(text)))

    def _find_active_trigger(self, text, cursor_pos):
        """
        Find which trigger pattern is currently active.

        Handles overlapping patterns (e.g., : and ::) by prioritizing:
        1. Patterns that appear later in the text
        2. Longer patterns over shorter ones at the same position
        """
        # Sort patterns by length (longest first) to check longer patterns first
        sorted_patterns = sorted(self.completers.keys(), key=len, reverse=True)

        active_pattern = None
        trigger_pos = -1
        trigger_end = -1

        search_text = text[:cursor_pos]

        for pattern in sorted_patterns:
            pos = search_text.rfind(pattern)

            while pos >= 0:
                end_pos = pos + len(pattern)

                # Validate end_pos doesn't exceed text length
                if end_pos > len(text):
                    pos = search_text.rfind(pattern, 0, pos)
                    continue

                text_after = text[end_pos:cursor_pos]

                # Only consider if no space/newline after trigger
                if " " not in text_after and "\n" not in text_after:
                    # Skip if this pattern overlaps with an already found longer pattern
                    # E.g., skip : at pos 1 if we already found :: at pos 0
                    if trigger_pos >= 0 and pos >= trigger_pos and pos < trigger_end:
                        pos = search_text.rfind(pattern, 0, pos)
                        continue

                    # Skip if a longer pattern exists at the same position
                    # E.g., skip : at pos 0 if :: also exists at pos 0
                    longer_exists = any(
                        len(other) > len(pattern)
                        and search_text[pos:].startswith(other)
                        and pos + len(other) <= cursor_pos
                        for other in sorted_patterns
                    )

                    if longer_exists:
                        pos = search_text.rfind(pattern, 0, pos)
                        continue

                    # Accept this pattern (later position or same position but longer)
                    if pos > trigger_pos or (pos == trigger_pos and len(pattern) > len(active_pattern)):
                        trigger_pos = pos
                        trigger_end = end_pos
                        active_pattern = pattern
                    break

                pos = search_text.rfind(pattern, 0, pos)

        return active_pattern, trigger_pos

    def _apply_visual_indicator(self, active):
        """Apply visual styling"""
        config = self.global_config
        if not config.get("visual_indicator", False):
            return

        if active:
            # Use object name for more reliable styling
            if not self.objectName():
                self.setObjectName("pattern_completer_widget")
            self.setStyleSheet(
                "#pattern_completer_widget { border: 2px solid #4CAF50; border-radius: 3px; }"
            )
        else:
            self.setStyleSheet("")

    def _pattern_on_text_changed(self):
        """Handle text changes"""
        if self.inserting_completion:
            return

        try:
            text, cursor_pos = self._get_text_and_cursor()
        except (RuntimeError, AttributeError):
            return

        active_pattern, trigger_pos = self._find_active_trigger(text, cursor_pos)

        if active_pattern and trigger_pos >= 0:
            self.active_pattern = active_pattern
            self.trigger_start_pos = trigger_pos

            pattern_config = self.completers[active_pattern]
            config = pattern_config["config"]

            pattern_len = len(active_pattern)
            prefix = text[trigger_pos + pattern_len: cursor_pos]

            candidates = self._get_candidates(pattern_config, text, cursor_pos, prefix)
            if not candidates:
                self._popup.hide()
                self._apply_visual_indicator(False)
                return

            self._show_popup(candidates, config)

            if config.get("visual_indicator", False):
                self._apply_visual_indicator(True)
        else:
            self.active_pattern = None
            self.trigger_start_pos = -1
            self._popup.hide()
            self._apply_visual_indicator(False)

    def _pattern_insert_completion(self, completion):
        """Insert the selected completion"""
        if self.trigger_start_pos < 0 or not self.active_pattern:
            return

        self.inserting_completion = True

        try:
            text, cursor_pos = self._get_text_and_cursor()

            on_insert = self.completers[self.active_pattern].get("on_insert")
            if callable(on_insert):
                new_text, new_cursor_pos = on_insert(
                    completion, text, self.trigger_start_pos, cursor_pos
                )
            else:
                # Default: replace trigger + typed prefix with the completion
                new_text = text[: self.trigger_start_pos] + completion + text[cursor_pos:]
                new_cursor_pos = self.trigger_start_pos + len(completion)
            self._set_text_with_cursor(new_text, new_cursor_pos)

            # Reset state BEFORE hiding popup to prevent re-triggering
            self.trigger_start_pos = -1
            self.active_pattern = None

            self._popup.hide()
            self._apply_visual_indicator(False)
        finally:
            self.inserting_completion = False

    def _pattern_key_press_event(self, event):
        """
        Handle pattern completion keys.
        Call this from your widget's keyPressEvent BEFORE calling super().

        Returns:
            bool: True if event was handled (don't call super), False otherwise
        """
        if self._popup.isVisible():
            key = event.key()
            if key in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Tab):
                current = self._popup.currentItem()
                if current is None and self._popup.count() > 0:
                    current = self._popup.item(0)
                if current:
                    self._pattern_insert_completion(current.text())
                event.accept()
                return True
            elif key == Qt.Key.Key_Down:
                self._popup.setCurrentRow(
                    min(self._popup.currentRow() + 1, self._popup.count() - 1)
                )
                event.accept()
                return True
            elif key == Qt.Key.Key_Up:
                self._popup.setCurrentRow(
                    max(self._popup.currentRow() - 1, 0)
                )
                event.accept()
                return True
            elif key == Qt.Key.Key_Escape:
                self._popup.hide()
                self._apply_visual_indicator(False)
                event.accept()
                return True

        return False  # Event not handled, continue normal processing


class PatternLineEdit(QLineEdit, PatternCompleter):
    """QLineEdit with pattern completion"""

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.init_pattern_completer(**kwargs)

    def keyPressEvent(self, event):
        """Override to handle completion keys"""
        if not self._pattern_key_press_event(event):
            # Event not handled by pattern completer, process normally
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        if hasattr(self, '_popup'):
            self._popup.hide()
        super().focusOutEvent(event)


class PatternTextEdit(QTextEdit, PatternCompleter):
    """QTextEdit with pattern completion"""

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.init_pattern_completer(**kwargs)

    def keyPressEvent(self, event):
        """Override to handle completion keys"""
        if not self._pattern_key_press_event(event):
            # Event not handled by pattern completer, process normally
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        if hasattr(self, '_popup'):
            self._popup.hide()
        super().focusOutEvent(event)


class PatternPlainTextEdit(QPlainTextEdit, PatternCompleter):
    """QPlainTextEdit with pattern completion"""

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)
        self.init_pattern_completer(**kwargs)

    def keyPressEvent(self, event):
        """Override to handle completion keys"""
        if not self._pattern_key_press_event(event):
            # Event not handled by pattern completer, process normally
            super().keyPressEvent(event)

    def focusOutEvent(self, event):
        if hasattr(self, '_popup'):
            self._popup.hide()
        super().focusOutEvent(event)


class PatternCompleterDelegate(QStyledItemDelegate):
    """
    Custom delegate for QTableWidget that uses PatternLineEdit with mixin.

    Usage:
        delegate = PatternCompleterDelegate(min_width=200, max_width=600)
        delegate.add_completer('@', ['USA', 'Canada', 'Mexico'])
        delegate.add_completer('#', ['Python', 'Java', 'C++'], case_sensitive=True)
        table.setItemDelegateForColumn(0, delegate)
    """

    def __init__(self, parent=None, **kwargs):
        """
        Initialize delegate with global configuration.

        Args:
            **kwargs: Global configuration options (same as init_pattern_completer)
        """
        super().__init__(parent)
        self.completer_configs = {}  # pattern -> config dict
        self.global_kwargs = kwargs

    def add_completer(self, pattern, completions, **kwargs):
        """
        Add a completer pattern for this delegate.

        Args:
            pattern: Trigger string (e.g., '@', '#')
            completions: List of completion strings
            **kwargs: Pattern-specific configuration (overrides global)
        """
        self.completer_configs[pattern] = {
            "completions": completions,
            "kwargs": kwargs,
        }

    def update_completions(self, pattern, completions):
        """Update the completion list for a specific pattern"""
        if pattern in self.completer_configs:
            self.completer_configs[pattern]["completions"] = completions

    def update_completer_config(self, pattern, **kwargs):
        """Update configuration for a specific pattern"""
        if pattern in self.completer_configs:
            self.completer_configs[pattern]["kwargs"].update(kwargs)

    def set_global_config(self, **kwargs):
        """Update global configuration"""
        self.global_kwargs.update(kwargs)

    def createEditor(self, parent, option, index):
        """Create a PatternLineEdit when editing starts"""
        try:
            editor = PatternLineEdit(parent, **self.global_kwargs)

            # Add all configured completers
            for pattern, config in self.completer_configs.items():
                editor.add_completer(
                    pattern, config["completions"], **config.get("kwargs", {})
                )

            return editor
        except Exception as e:
            print(f"Error creating editor: {e}")
            # Fallback to basic QLineEdit
            return QLineEdit(parent)

    def setEditorData(self, editor: PatternLineEdit, index):
        """Load data from model into editor"""
        try:
            if not editor or not index.isValid():
                return
            value = index.model().data(index, Qt.ItemDataRole.DisplayRole)
            if value is not None:
                editor.setText(str(value))
            else:
                editor.clear()
        except Exception as e:
            print(f"Error setting editor data: {e}")
            pass

    def setModelData(self, editor: PatternLineEdit, model, index):
        """Save data from editor back to model"""
        try:
            if not editor or not model or not index.isValid():
                return
            text = editor.text()
            model.setData(index, text, Qt.ItemDataRole.EditRole)
        except Exception as e:
            print(f"Error setting model data: {e}")
            pass

    def destroyEditor(self, editor: PatternLineEdit, index):
        """Clean up editor when done"""
        try:
            if editor and hasattr(editor, "cleanup_pattern_completer"):
                editor.cleanup_pattern_completer()
        except Exception as e:
            print(f"Error destroying editor: {e}")
            pass

        try:
            super().destroyEditor(editor, index)
        except Exception as e:
            print(f"Error in super destroyEditor: {e}")
            pass
