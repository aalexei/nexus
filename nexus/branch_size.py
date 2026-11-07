"""Per-map child-size policy, separate from viewport zoom and text fonts."""
import logging
import math
from collections import deque

from PyQt6 import QtCore, QtWidgets
from . import config, graphydb


KEY = 'child_size_ratio'


def valid_ratio(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and 0.05 <= value <= 2.0 else None


def map_ratio(graph):
    """None preserves the original policy for maps not explicitly configured."""
    roots = list(graph.fetch('[r:Root]'))
    return valid_ratio(roots[0].get(KEY)) if roots else None


def nested_nodes(graph, roots=None):
    """Reachable deeper nodes, including collapsed ones; roots stay larger."""
    roots = list(graph.fetch('[r:Root]')) if roots is None else roots
    nodes = {n['uid']: n for n in graph.fetch('[n:Stem]')}
    children = {}
    for edge in graph.fetch('(p) -[e:Child]> (n)'):
        if edge['enduid'] in nodes:
            children.setdefault(edge['startuid'], []).append(edge['enduid'])
    queue = deque((uid, 0) for root in roots for uid in children.get(root['uid'], []))
    seen, nested = set(), []
    while queue:
        uid, depth = queue.popleft()
        if uid in seen:
            continue  # Minimum depth wins; protect against damaged cycles.
        seen.add(uid)
        if depth >= 2:
            nested.append(nodes[uid])
        queue.extend((child, depth + 1) for child in children.get(uid, []))
    return nested


def apply_ratio(scene, value, resize_existing=False):
    """One atomic Undo batch; leave displayed roots/first-level sizes alone."""
    value = valid_ratio(value)
    if value is None:
        raise ValueError('Child size must be between 5% and 200%.')
    if scene.mode != 'edit':
        return False
    graph = scene.graph
    roots = list(graph.fetch('[r:Root]'))
    if not roots:
        raise ValueError('This map has no root to save its child-size setting.')
    nested = nested_nodes(graph, roots) if resize_existing else []
    changes = [(node, KEY) for node in roots if node.get(KEY) != value]
    resized = [node for node in nested if node.get('scale') != value]
    changes.extend((node, 'scale') for node in resized)
    if not changes:
        return False
    batch = graphydb.generateUUID()
    # Use fresh DB objects, not displayed nodes: failed saves cannot leave the
    # map graphics half-resized. Collapsed descendants are included in the DB.
    with graph.connection:
        for node, key in changes:
            node[key] = value
            node.save(batch=batch, setchange=True)
    if resized:
        for root in scene.childStems():
            root.renew(create=False)
        scene.update()  # Schedule a complete repaint, keeping redraw safeguards.
    scene.mapModified.emit()
    return True


class ChildSizeDialog(QtWidgets.QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle('Child size — this map')
        self.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        layout = QtWidgets.QVBoxLayout(self)
        note = QtWidgets.QLabel('Size of deeper nodes relative to their parent.\n'
                               '100% keeps them the same size; 50% halves each level.\n'
                               'The main topic and its first-level branches stay unchanged.\n'
                               'This does not change canvas zoom or font settings.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.presets = QtWidgets.QComboBox()
        for text, percent in (('50% — original shrinking', 50), ('85% — gentle shrinking', 85),
                              ('100% — same size (recommended)', 100), ('Custom', None)):
            self.presets.addItem(text, percent)
        self.presets.setAccessibleName('Child size presets')
        layout.addWidget(self.presets)
        self.percent = QtWidgets.QDoubleSpinBox()
        self.percent.setRange(5, 200)
        self.percent.setDecimals(2)
        self.percent.setSingleStep(5)
        self.percent.setSuffix('%')
        self.percent.setAccessibleName('Child size percentage')
        layout.addWidget(self.percent)
        self.existing = QtWidgets.QCheckBox('Resize this map’s existing nested nodes')
        self.existing.setToolTip('Includes collapsed branches. Preserves positions, angles, fonts and first-level sizes. '
                                 'Larger nodes may overlap; Undo restores previous sizes.')
        layout.addWidget(self.existing)
        warning = QtWidgets.QLabel('Existing positions stay fixed; larger labels may overlap.')
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.summary = QtWidgets.QLabel()
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        layout.addWidget(QtWidgets.QLabel('Saved in this map. Apply is undoable with Cmd+Z / Ctrl+Z.'))
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok |
                                            QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self.applyButton = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        self.applyButton.setText('Apply')
        self.applyButton.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.presets.activated.connect(self.choosePreset)
        self.percent.valueChanged.connect(self.matchPreset)
        self.percent.valueChanged.connect(self.updateSummary)
        self.existing.toggled.connect(self.updateSummary)
        self.finished.connect(self.returnFocus)
        self.refresh()

    def refresh(self):
        # Snapshot once on opening; changing the spin box need not query or
        # parse the entire map on every key. Apply re-reads the live DB.
        self._nested = nested_nodes(self.owner.scene.graph)
        ratio = map_ratio(self.owner.scene.graph)
        self.percent.setValue((ratio if ratio is not None else config.get_config()['child_scale']) * 100)
        self.matchPreset(self.percent.value())
        self.existing.setChecked(True)
        self.updateSummary()

    def updateSummary(self, *unused):
        if not hasattr(self, '_nested'):
            return
        ratio = self.percent.value() / 100
        count = sum(node.get('scale') != ratio for node in self._nested)
        if not self.existing.isChecked():
            self.applyButton.setText('Save for new nodes')
            text = 'New nodes only. The current graph will not be resized.'
        elif count:
            self.applyButton.setText('Apply to map')
            text = f'Will resize {count} existing nested node(s), including collapsed nodes.\n'
            text += 'New deeper nodes will use this ratio too.'
        elif self._nested:
            self.applyButton.setText('Apply to map')
            text = 'Existing nested nodes already have this ratio; their sizes will not change.'
        else:
            self.applyButton.setText('Save ratio')
            text = 'No deeper nodes to resize yet. First-level branches stay unchanged.\n'
            text += 'The ratio will apply when you create deeper nodes.'
        self.summary.setText(text)

    def matchPreset(self, percent):
        index = self.presets.findData(percent)
        self.presets.setCurrentIndex(index if index >= 0 else self.presets.count() - 1)

    def choosePreset(self, index):
        percent = self.presets.itemData(index)
        if percent is not None:
            self.percent.setValue(percent)
        else:
            self.percent.setFocus()
            self.percent.selectAll()

    def returnFocus(self):
        self.owner.activateWindow()
        self.owner.view.setFocus()

    def accept(self):
        if self.owner.scene.mode != 'edit':
            self.reject()
            return
        try:
            self.percent.interpretText()
            ratio = self.percent.value() / 100
            nodes = nested_nodes(self.owner.scene.graph) if self.existing.isChecked() else []
            count = sum(node.get('scale') != ratio for node in nodes)
            apply_ratio(self.owner.scene, ratio, self.existing.isChecked())
        except Exception as error:
            logging.exception('Could not apply child size')
            QtWidgets.QMessageBox.warning(self, 'Child size not saved', str(error))
            return
        super().accept()
        if not self.existing.isChecked():
            message = f'Child size {ratio * 100:g}% saved for new nodes only; current graph unchanged.'
        elif count:
            message = f'Resized {count} existing nested node(s) to {ratio * 100:g}%. Undo with Cmd+Z / Ctrl+Z.'
        elif nodes:
            message = f'Existing nested nodes are already at {ratio * 100:g}%; no resizing needed.'
        else:
            message = 'Ratio saved. No deeper nodes to resize yet; first-level branches stay unchanged.'
        if hasattr(self.owner, 'showMessage'):
            self.owner.showMessage(message, 8000)
        else:
            self.owner.scene.statusMessage.emit(message)
