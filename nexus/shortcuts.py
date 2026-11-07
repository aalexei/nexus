"""Keyboard reference shared by the map window and node editor."""
import sys
from PyQt6 import QtCore, QtGui, QtWidgets
from . import config


def key_label(sequence):
    label = sequence.toString(QtGui.QKeySequence.SequenceFormat.PortableText)
    if sys.platform == 'darwin':
        label = label.replace('Meta+', 'Control+').replace('Ctrl+', 'Cmd+')
    return label


def shortcut_rows(owner):
    window = owner if hasattr(owner, 'viewMenu') else None
    if window is None and getattr(owner, 'stem', None) is not None:
        for view in owner.stem.scene().views():
            if hasattr(view.window(), 'viewMenu'):
                window = view.window()
                break
    rows = []
    if window is not None:
        groups = (
            ('Files', ('newAct', 'openAct', 'printMapAct', 'printViewsAct', 'closeAct', 'exitAct')),
            ('Map editing', ('textModeAct', 'todoModeAct', 'cycleTaskAct', 'fullEditorAct', 'undoAct', 'findNodeAct', 'cutAct', 'copyAct', 'copyStemLinkAct', 'pasteAct', 'deleteAct')),
            ('Map selection', ('selectAllAct', 'selectChildrenAct', 'selectSiblingsAct', 'deselectAct')),
            ('Map appearance', ('childSizeAct', 'setScaleAct', 'increaseScaleAct', 'decreaseScaleAct', 'hideAct',
                                'setOpacityAct', 'toggleIconifyAct')),
            ('Map zoom', ('zoomInAct', 'zoomOutAct', 'zoomAllAct', 'zoomSelectionAct', 'zoomParentAct')),
            ('Modes and views', ('editModeAct', 'presentationModeAct', 'recordModeAct', 'viewsAct', 'contentsAct')),
        )
        for context, names in groups:
            for name in names:
                action = getattr(window, name, None)
                if action is not None and action.shortcuts():
                    rows.append((context, ' / '.join(dict.fromkeys(key_label(k) for k in action.shortcuts())),
                                 action.text().replace('&', '')))
    map_view = getattr(window, 'view', None) or getattr(owner, 'view', None)
    if map_view is None and isinstance(owner, QtWidgets.QGraphicsView):
        map_view = owner
    editor_owner = owner if hasattr(owner, 'textmode') else getattr(window, 'editDialog', None)

    def add_contextual_rows(entries):
        for context, key, description in entries:
            if context.startswith('Tasks') and not hasattr(map_view, 'tasks'):
                continue
            if context == 'Typing on the map' and not hasattr(map_view, 'inline'):
                continue
            if context in ('Map navigation', 'Map selection') and not hasattr(map_view, 'arrowTarget'):
                continue
            editor_view = getattr(editor_owner, 'view', None)
            if context.startswith('Editor —') and not hasattr(editor_view, 'editorKeyPress'):
                continue
            if description.startswith('Undo the last pen') and not hasattr(editor_view, 'undoEditor'):
                continue
            rows.append((context, key, description))

    add_contextual_rows((
        ('Tasks — typing or map', key_label(QtGui.QKeySequence('Ctrl+Shift+T')), 'Toggle Todo creation mode; existing nodes stay unchanged'),
        ('Tasks — typing or map', key_label(QtGui.QKeySequence('Ctrl+D')), 'Cycle current node: Note → Todo → Doing → Done → Note; skips Doing when disabled'),
        ('Tasks — mode ON', 'Enter / Tab', 'Save and add an unchecked sibling / child task; empty text creates nothing'),
        ('Tasks', 'Click checkbox', 'Cycle Todo → Doing (yellow) → Done → Todo; disable Doing under Settings for simple check/uncheck'),
        ('Typing on the map', 'Enter', 'Save and start a sibling (nonempty text only)'),
        ('Typing on the map', 'Tab', 'Save and start a child (nonempty text only)'),
        ('Typing on the map', 'Shift+Enter', 'Insert a newline'),
        ('Typing on the map', 'Esc', 'Save and return to node selection'),
        ('Typing on the map', key_label(QtGui.QKeySequence('Ctrl+Return')), 'Save and open the full editor'),
        ('Typing on the map', key_label(QtGui.QKeySequence('Ctrl+Z')), 'Undo text; after finishing, Undo affects the map'),
        ('Typing on the map', key_label(QtGui.QKeySequence('Ctrl+B')) + ' / I / U', 'Bold / italic / underline'),
        ('Typing on the map', 'Arrows / Backspace / Delete', 'Move the text cursor / delete text, not map nodes'),
        ('Every window', key_label(QtGui.QKeySequence('Ctrl+/')), 'Open keyboard shortcuts (press again to close)'),
        ('Map navigation', 'Tab', 'Create a child; with no selection, use the root'),
        ('Map navigation', 'Enter / F2', 'Edit the selected node'),
        ('Map navigation', 'Shift+Enter', 'Create a sibling; on the root, create a child'),
        ('Map navigation', 'Up / Down', 'Select a visible node above / below, across branches; prefer the same column'),
        ('Map selection', 'Shift+Up / Down', 'Extend selection above / below; reverse the last direction to shrink'),
        ('Map selection', 'Shift+Left / Right', 'Extend left / right through parent or visible children; does not expand collapsed branches'),
        ('Map selection', 'Arrows (multiple selected)', 'Keep the active node only, then navigate one step'),
        ('Map selection', 'Esc (multiple selected)', 'Keep only the active node; while typing, finish typing first'),
        ('Map selection', 'Shift+click', 'Add / remove a node; start a new keyboard-selection path'),
        ('Map navigation', 'Option+Up / Down' if sys.platform == 'darwin' else 'Alt+Up / Down',
         'Move the selected branch above / below a sibling on the same side'),
        ('Map navigation', 'Left / Right', 'Navigate left / right through parent or children; inward returns to parent on either side'),
        ('Map navigation', 'Left / Right (collapsed)', 'Outward arrow expands hidden children on that side; press again to enter'),
        ('Map navigation', 'Space', 'Collapse / expand children'),
        ('Map navigation', key_label(QtGui.QKeySequence('Ctrl+Up')) + ' / Down / Left / Right', 'Pan the whiteboard'),
        ('Editor — typing', 'Enter', 'Save and close the editor'),
        ('Editor — typing', 'Shift+Enter', 'Insert a newline'),
        ('Editor — typing', 'Esc', 'Finish typing and stay inside the editor'),
        ('Editor — typing', key_label(QtGui.QKeySequence('Ctrl+B')), 'Toggle bold'),
        ('Editor — typing', key_label(QtGui.QKeySequence('Ctrl+I')), 'Toggle italic'),
        ('Editor — typing', key_label(QtGui.QKeySequence('Ctrl+U')), 'Toggle underline'),
        ('Editor — tools', 'Esc', 'Save and close the editor'),
        ('Editor — tools', 'T', 'Text tool'),
        ('Editor — tools', 'P / B', 'Pen tool'),
        ('Editor — tools', 'H', 'Highlighter tool'),
        ('Editor — tools', 'E', 'Eraser tool'),
        ('Editor — tools', key_label(QtGui.QKeySequence('Ctrl+Z')),
         'Undo the last pen/highlighter stroke drawn since opening this editor; while typing, undo text'),
    ))
    editor = owner if hasattr(owner, 'textmode') else getattr(window, 'editDialog', None)
    if editor is not None:
        for name in ('cutAct', 'copyAct', 'pasteAct', 'deleteAct', 'zoomInAct', 'zoomOutAct'):
            action = getattr(editor, name)
            rows.append(('Editor', ' / '.join(key_label(k) for k in action.shortcuts()),
                         action.text().replace('&', '')))
    settings = config.get_config()
    for setting, description in (
            ('view_next_keys', 'Next saved view'),
            ('view_prev_keys', 'Previous saved view'),
            ('view_home_keys', 'Toggle home view / return'),
            ('view_first_keys', 'First saved view'),
            ('view_pointer_keys', 'Toggle pointer')):
        rows.append(('Presentation', ' / '.join(key_label(QtGui.QKeySequence(k))
                                               for k in settings[setting]), description))
    rows.extend((('Presentation', 'Esc / Q', 'Return to map editing'),
                 ('Recording', 'Esc', 'Pause recording')))
    return rows


class KeyboardShortcutsDialog(QtWidgets.QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.finished.connect(owner.activateWindow)
        self.setWindowTitle('Keyboard Shortcuts')
        self.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        self.setMinimumSize(540, 360)
        area = self.screen().availableGeometry()
        self.resize(min(860, area.width() - 80), min(660, area.height() - 100))
        layout = QtWidgets.QVBoxLayout(self)
        note = QtWidgets.QLabel('Shortcuts depend on where you are. Shift+arrows extend node selection; '
                               'the active node has a stronger blue outline. Copy/Delete act on whole branches. '
                               'While typing, Shift+arrows select text; press Esc to finish typing.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText('Search shortcuts, tools or modes…')
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName('Search keyboard shortcuts')
        layout.addWidget(self.search)
        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(('Where', 'Shortcut', 'Action'))
        self.table.setAccessibleName('Keyboard shortcut reference')
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)
        self.empty = QtWidgets.QLabel('No matching shortcuts.')
        self.empty.hide()
        layout.addWidget(self.empty)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.search.textChanged.connect(self.filter_rows)
        close_action = QtGui.QAction(self)
        close_action.setShortcut('Ctrl+/')
        close_action.triggered.connect(self.reject)
        self.addAction(close_action)

    def refresh(self, owner):
        rows = shortcut_rows(owner)
        self.table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            for column, text in enumerate(row):
                self.table.setItem(index, column, QtWidgets.QTableWidgetItem(text))
        self.search.clear()
        self.filter_rows('')
        self.table.resizeRowsToContents()

    def filter_rows(self, query):
        terms = query.casefold().split()
        visible = 0
        for row in range(self.table.rowCount()):
            text = ' '.join(self.table.item(row, c).text() for c in range(3)).casefold()
            matches = all(term in text for term in terms)
            self.table.setRowHidden(row, not matches)
            visible += matches
        self.empty.setVisible(visible == 0)


def show_keyboard_shortcuts(owner):
    dialog = getattr(owner, '_shortcut_dialog', None)
    if dialog is None:
        dialog = KeyboardShortcutsDialog(owner)
        owner._shortcut_dialog = dialog
    dialog.refresh(owner)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    dialog.search.setFocus()
