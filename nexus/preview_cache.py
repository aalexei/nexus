"""Bounded, versioned thumbnail cache; no Qt or map database writes."""
import hashlib
import json
import re
import struct
import zlib
from pathlib import Path

VERSION = 1
WIDTH, HEIGHT = 720, 420
MAX_FILES, MAX_BYTES = 128, 50 * 1024 * 1024


def signature(filename):
    requested = Path(filename).expanduser()
    if requested.is_symlink():
        raise ValueError('Map path changed to a symlink')
    path = requested.resolve(strict=True)
    if requested.absolute() != path:
        raise ValueError('Map parent path changed')
    if not path.is_file() or path.suffix.casefold() not in ('.nex', '.nexus'):
        raise ValueError('Not a map file')
    stamps = []
    for candidate in (path, Path(str(path) + '-wal'), Path(str(path) + '-journal')):
        try:
            stat = candidate.stat()
            stamps.append((stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
        except FileNotFoundError:
            stamps.append(None)
    return {'version': VERSION, 'path': str(path), 'stamps': stamps}


def image_path(directory, stamp):
    key = hashlib.sha256(json.dumps(stamp, sort_keys=True).encode()).hexdigest()
    return Path(directory) / ('thumb-' + key + '.png')


def valid_png(path):
    try:
        if path.is_symlink() or path.stat().st_size > 2 * 1024 * 1024:
            return False
        with path.open('rb') as stream:
            data = stream.read(2 * 1024 * 1024 + 1)
        if not (data[:8] == b'\x89PNG\r\n\x1a\n' and data[12:16] == b'IHDR'
                and struct.unpack('>II', data[16:24]) == (WIDTH, HEIGHT)):
            return False
        offset, pixels = 8, False
        while offset + 12 <= len(data):
            length = struct.unpack('>I', data[offset:offset + 4])[0]
            end = offset + 12 + length
            if end > len(data):
                return False
            chunk = data[offset + 4:offset + 8 + length]
            checksum = struct.unpack('>I', data[offset + 8 + length:end])[0]
            if zlib.crc32(chunk) & 0xffffffff != checksum:
                return False
            pixels |= chunk[:4] == b'IDAT'
            if chunk[:4] == b'IEND':
                return pixels and end == len(data)
            offset = end
        return False
    except (OSError, ValueError, struct.error):
        return False


def prune(directory):
    """Only finalized, generated thumbnails in this explicit cache namespace."""
    files = []
    for path in Path(directory).glob('thumb-*.png'):
        if re.fullmatch(r'thumb-[0-9a-f]{64}\.png', path.name) and not path.is_symlink():
            try:
                stat = path.stat()
                files.append((stat.st_mtime_ns, stat.st_size, path))
            except OSError:
                pass
    files.sort(reverse=True)
    size = 0
    for index, (_, length, path) in enumerate(files):
        size += length
        if index >= MAX_FILES or size > MAX_BYTES:
            try:
                path.unlink()
            except OSError:
                pass
