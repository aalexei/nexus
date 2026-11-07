"""Regression coverage for search, undo focus, reordering and recovery."""
import os
from pathlib import Path
import unittest
from unittest import mock

import apsw
import pr_test_support as navigation
from PyQt6 import QtCore, QtGui, QtWidgets, QtTest
from nexus import graphics, recovery as workflow, mainwindow


class RecoveryTests(navigation.MapTestCase):
    def test_optional_inline_save_failure_blocks_manual_capture(self):
        from types import SimpleNamespace
        inline = mock.Mock()
        inline.checkpoint.return_value = False
        manager = mock.Mock()
        owner = SimpleNamespace(view=SimpleNamespace(inline=inline), recovery=manager)
        mainwindow.MainWindow.createRecoverySnapshot(owner)
        inline.checkpoint.assert_called_once_with()
        manager.capture.assert_not_called()

    def test_snapshots_are_valid_bounded_skip_unchanged_and_recover_without_overwrite(self):
        store = workflow.SnapshotStore(self.graph, Path(self.tmp.name) / 'recovery', keep=2)
        first = store.capture()
        self.assertTrue(first.exists())
        self.assertIsNone(store.capture())
        self.root.node['test_value'] = 'first change'
        self.root.node.save()
        second = store.capture()
        self.root.node['test_value'] = 'later change'
        self.root.node.save()
        third = store.capture()
        self.assertEqual(set(store.snapshots()), {second, third})
        self.assertFalse(first.exists())
        copied = Path(self.tmp.name) / 'recovered.nex'
        store.recover_copy(second, copied)
        connection = apsw.Connection(str(copied), flags=apsw.SQLITE_OPEN_READONLY)
        try:
            self.assertEqual(connection.execute('PRAGMA quick_check').fetchone()[0], 'ok')
            value = connection.execute("SELECT json_extract(data,'$.test_value') FROM nodes WHERE uid=?",
                                       [self.root.node['uid']]).fetchone()[0]
            self.assertEqual(value, 'first change')
        finally:
            connection.close()
        for existing in (copied, Path(self.graph.path), second):
            with self.assertRaises(FileExistsError):
                store.recover_copy(second, existing)
        self.assertEqual(self.graph.getuid(self.root.node['uid'])['test_value'], 'later change')
        with self.assertRaises(ValueError):
            store.recover_copy(copied, Path(self.tmp.name) / 'invalid.nex')


    def test_snapshot_failure_retries_and_does_not_prune_old_backup(self):
        store = workflow.SnapshotStore(self.graph, Path(self.tmp.name) / 'recovery')
        first = store.capture()
        self.root.node['test_value'] = 'new'
        self.root.node.save()
        with mock.patch('nexus.recovery.apsw.Connection', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                store.capture()
        self.assertEqual(store.snapshots(), [first])
        self.assertIsNotNone(store.capture())
        self.assertEqual(list(store.directory.glob('*.partial')), [])


    def test_recovery_timer_and_dialog_recover_a_new_copy(self):
        owner = QtWidgets.QWidget()
        owner.scene, owner.view = self.scene, self.view
        messages, opened, seen, errors = [], [], [], []
        owner.showMessage = lambda *args: messages.append(args)
        store_class = workflow.SnapshotStore
        destination = Path(self.tmp.name) / 'dialog-recovered.nex'
        with mock.patch('nexus.recovery.SnapshotStore', side_effect=lambda graph:
                        store_class(graph, Path(self.tmp.name) / 'recovery')), \
             mock.patch.object(self.app, 'raiseOrOpen', opened.append, create=True), \
             mock.patch.object(QtWidgets.QFileDialog, 'getSaveFileName', return_value=(str(destination), '')):
            manager = workflow.RecoveryManager(owner)
            self.assertEqual(manager.timer.interval(), 300000)
            self.root.node['test_value'] = 'timer change'
            self.root.node.save()
            manager.timer.timeout.emit()
            self.assertEqual(len(manager.store.snapshots()), 2)
            manager.timer.timeout.emit()
            self.assertEqual(len(manager.store.snapshots()), 2)

            def interact():
                dialog = self.app.activeModalWidget()
                try:
                    seen.append(dialog.findChild(QtWidgets.QListWidget).count())
                    button = next(b for b in dialog.findChildren(QtWidgets.QPushButton)
                                  if b.text() == 'Recover Copy…')
                    button.click()
                except Exception as error:
                    errors.append(error)
                finally:
                    if dialog is not None and dialog.isVisible():
                        dialog.reject()

            try:
                QtCore.QTimer.singleShot(0, interact)
                manager.showSnapshots()
                self.assertEqual(errors, [])
                self.assertEqual(seen, [2])
                self.assertEqual(opened, [str(destination)])
                self.assertTrue(destination.exists())
                self.assertTrue(Path(self.graph.path).exists())
                self.assertEqual(messages, [])
            finally:
                manager.timer.stop()
                owner.deleteLater()
                self.app.processEvents()
