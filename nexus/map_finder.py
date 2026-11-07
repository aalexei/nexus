"""Read-only map discovery off the UI thread, plus local fuzzy ranking."""
import os
import logging
import subprocess
import threading
import time
import uuid
from pathlib import Path

from PyQt6 import QtCore

EXTENSIONS = {'.nex', '.nexus'}
MAX_MAPS = 20000
SKIP_DIRECTORIES = {'.git', '.venv', 'node_modules', '__pycache__', '.Trash', '.Trashes'}
SPOTLIGHT_QUERY = 'kMDItemFSName == "*.nex"cd || kMDItemFSName == "*.nexus"cd'


def map_entry(filename, excluded=()):
    """Validate existence, normalize aliases, and never open the map database."""
    try:
        path = Path(filename).expanduser().resolve(strict=True)
        if path.suffix.casefold() not in EXTENSIONS or not path.is_file():
            return None
        if any(part in ('.Trash', '.Trashes') for part in path.parts):
            return None
        if any(root == path or root in path.parents for root in excluded):
            return None
        return {'path': str(path), 'name': path.name, 'stem': path.stem,
                'folder': str(path.parent), 'mtime': path.stat().st_mtime}
    except (OSError, RuntimeError, ValueError):
        return None


def _token_score(token, name):
    if token == name:
        return (0, 0)
    if name.startswith(token):
        return (1, len(name) - len(token))
    start = name.find(token)
    if start >= 0:
        boundary = start == 0 or not name[start - 1].isalnum()
        return (2 if boundary else 3, start)
    positions, offset = [], 0
    for letter in token:
        position = name.find(letter, offset)
        if position < 0:
            return None
        positions.append(position)
        offset = position + 1
    return (4, positions[-1] - positions[0] + 1 - len(token) + positions[0])


def fuzzy_score(query, entry):
    tokens = query.casefold().split()
    if not tokens:
        return (0, 0)
    name, stem = entry['name'].casefold(), entry['stem'].casefold()
    if query.strip().casefold() in (name, stem):
        return (0, 0)
    scores = [_token_score(token, name) for token in tokens]
    if any(score is None for score in scores):
        return None
    return (max(score[0] for score in scores), sum(score[1] for score in scores))


def ranked_maps(entries, query):
    matches = [(score, entry) for entry in entries
               for score in [fuzzy_score(query, entry)] if score is not None]
    matches.sort(key=lambda pair: (pair[0], -pair[1]['mtime'],
                                  pair[1]['name'].casefold(), pair[1]['path']))
    return [entry for _, entry in matches]


class DiscoverySignals(QtCore.QObject):
    finished = QtCore.pyqtSignal(object)


class DiscoveryJob(QtCore.QRunnable):
    """Cancellable Spotlight or explicit-folder search; no GUI access here."""
    def __init__(self, scope='spotlight', excluded=()):
        super().__init__()
        self.scope = scope
        self.token = uuid.uuid4().hex
        self.excluded = tuple(Path(path).resolve() for path in excluded)
        self.signals = DiscoverySignals()
        self.cancelled = threading.Event()

    def cancel(self):
        self.cancelled.set()

    def spotlight_paths(self):
        process = subprocess.Popen(['/usr/bin/mdfind', '-0', SPOTLIGHT_QUERY],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 15
        try:
            while True:
                if self.cancelled.is_set():
                    return []
                if time.monotonic() >= deadline:
                    raise TimeoutError('Spotlight took too long. Try Search a folder…')
                try:
                    output, error = process.communicate(timeout=.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode:
                raise OSError('Spotlight search failed. Try Search a folder…')
            return [os.fsdecode(path) for path in output.split(b'\0') if path]
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()

    def folder_paths(self, errors):
        if not Path(self.scope).is_dir():
            raise OSError('The selected folder is no longer available.')
        for root, directories, filenames in os.walk(self.scope, followlinks=False,
                                                     onerror=errors.append):
            if self.cancelled.is_set():
                return
            directories[:] = [name for name in directories if name not in SKIP_DIRECTORIES
                              and not any(Path(root) / name == excluded for excluded in self.excluded)]
            for name in filenames:
                if self.cancelled.is_set():
                    return
                if Path(name).suffix.casefold() in EXTENSIONS:
                    yield str(Path(root) / name)

    def discover(self):
        errors, found = [], {}
        candidates = self.spotlight_paths() if self.scope == 'spotlight' else self.folder_paths(errors)
        truncated = False
        for filename in candidates:
            if self.cancelled.is_set():
                break
            entry = map_entry(filename, self.excluded)
            if entry is not None:
                found[entry['path']] = entry
                if len(found) >= MAX_MAPS:
                    truncated = True
                    break
        notice = 'Some folders could not be read.' if errors else ''
        if truncated:
            notice = 'Discovery limit reached; choose a narrower folder to find more maps.'
        return list(found.values()), notice

    def run(self):
        result = {'scope': self.scope, 'token': self.token, 'entries': [],
                  'error': '', 'notice': '', 'cancelled': False}
        try:
            if not self.cancelled.is_set():
                result['entries'], result['notice'] = self.discover()
        except Exception as error:
            # QRunnable exceptions otherwise escape through Qt and can abort
            # the app. Report this read-only job failure to the GUI instead.
            logging.warning('Map discovery failed: %s', error)
            result['error'] = str(error)
        result['cancelled'] = self.cancelled.is_set()
        self.signals.finished.emit(result)
