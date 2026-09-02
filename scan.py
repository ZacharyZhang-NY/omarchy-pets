#!/usr/bin/env python3
"""Lists valid Codex Pets, each verified sheet inline."""
import base64
import errno
import hashlib
import itertools
import json
import os
import stat
import sys
import unicodedata

MAX_ENTRIES = 500
MAX_JSON_BYTES = 64 * 1024
MAX_SHEET_BYTES = 6 * 1024 * 1024
MAX_SCAN_BYTES = 24 * 1024 * 1024
HEADER_BYTES = 30
SHEET_WIDTH = 192 * 8
CELL_HEIGHT = 208
MIN_ROWS = 9
MAX_ROWS = 32
MAX_TEXT = 80
MAX_KIND = 32
MAX_PATH = 255
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOCTTY
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class Skip(Exception):
    """Not a usable pet; the message says why."""


def open_component(dir_fd, name, flags):
    """One path component under dir_fd, never through a symlink."""
    try:
        return os.open(name, flags, dir_fd=dir_fd)
    except FileNotFoundError:
        raise
    except OSError as error:
        symlink = error.errno == errno.ELOOP or (
            error.errno == errno.ENOTDIR and stat.S_ISLNK(os.lstat(name, dir_fd=dir_fd).st_mode))
        if symlink:
            raise Skip(f"{name} is a symlink") from None
        raise Skip(f"{name}: {error.strerror}") from None


def open_below(dir_fd, relative, flags):
    """Open relative under dir_fd, checking every component."""
    parts = relative.split("/")
    opened = []
    try:
        for part in parts[:-1]:
            dir_fd = open_component(dir_fd, part, DIR_FLAGS)
            opened.append(dir_fd)
        return open_component(dir_fd, parts[-1], flags)
    finally:
        for fd in opened:
            os.close(fd)


def regular_size(fd, name, limit):
    """Size of the regular file behind fd, at most limit."""
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        raise Skip(f"{name} is not a regular file")
    if info.st_size > limit:
        raise Skip(f"{name} is {info.st_size} bytes, limit {limit}")
    return info.st_size


def read_exact(fd, size):
    chunks = []
    remaining = size
    while remaining > 0:
        chunk = os.read(fd, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def sheet_size(header):
    """(width, height) from a PNG or WebP header, else None."""
    if header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR" and len(header) >= 25:
        return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")
    if header[:4] != b"RIFF" or header[8:12] != b"WEBP":
        return None
    chunk = header[12:16]
    if chunk == b"VP8X":
        return int.from_bytes(header[24:27], "little") + 1, int.from_bytes(header[27:30], "little") + 1
    if chunk == b"VP8L" and header[20:21] == b"\x2f":
        bits = int.from_bytes(header[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 " and header[23:26] == b"\x9d\x01\x2a":
        return int.from_bytes(header[26:28], "little") & 0x3FFF, int.from_bytes(header[28:30], "little") & 0x3FFF
    return None


def text_problem(text):
    """Why text cannot be emitted, or None."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return "is not valid UTF-8"
    if any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in text):
        return "has control characters"
    return None


def plain_relative(path):
    return (isinstance(path, str) and 0 < len(path) <= MAX_PATH and not path.startswith("/")
            and ".." not in path.split("/") and text_problem(path) is None)


def metadata(pet_fd):
    """Validated pet.json fields and the sprite sheet path."""
    fd = open_component(pet_fd, "pet.json", FILE_FLAGS)
    try:
        data = read_exact(fd, regular_size(fd, "pet.json", MAX_JSON_BYTES))
    finally:
        os.close(fd)
    try:
        meta = json.loads(data)
    except (ValueError, RecursionError):
        raise Skip("pet.json is not valid JSON") from None
    if not isinstance(meta, dict):
        raise Skip("pet.json is not a JSON object")
    pet_id = meta.get("id")
    if not isinstance(pet_id, str) or not pet_id:
        raise Skip("pet.json has no id")
    sheet = meta.get("spritesheetPath")
    if not plain_relative(sheet):
        raise Skip("spritesheetPath is not a plain relative path")
    out = {}
    for key, limit in (("id", MAX_TEXT), ("displayName", MAX_TEXT), ("kind", MAX_KIND)):
        if key in meta:
            if not isinstance(meta[key], str):
                raise Skip(f"{key} is not a string")
            problem = text_problem(meta[key])
            if problem:
                raise Skip(f"{key} {problem}")
            out[key] = meta[key][:limit]
    return out, sheet


def verified_sheet(pet_fd, sheet, budget):
    """(data URL, sha256, byte count) after the header checks."""
    name = os.path.basename(sheet)
    try:
        fd = open_below(pet_fd, sheet, FILE_FLAGS)
    except FileNotFoundError:
        raise Skip(f"spritesheet missing: {sheet}") from None
    try:
        size = regular_size(fd, name, MAX_SHEET_BYTES)
        if size > budget:
            raise Skip(f"{name} is {size} bytes, {budget} left of the {MAX_SCAN_BYTES} byte scan budget")
        data = read_exact(fd, size)
    finally:
        os.close(fd)
    if len(data) != size:
        raise Skip(f"{name} changed while being read")
    header = data[:HEADER_BYTES]
    dimensions = sheet_size(header)
    if dimensions is None:
        raise Skip(f"{name} is not a WebP or PNG file")
    png = header[:4] == b"\x89PNG"
    if png and header[24] > 8:
        raise Skip(f"PNG bit depth {header[24]} is not supported")
    width, height = dimensions
    if width != SHEET_WIDTH:
        raise Skip(f"atlas width {width} is not {SHEET_WIDTH}")
    if height % CELL_HEIGHT:
        raise Skip(f"atlas height {height} is not a multiple of {CELL_HEIGHT}")
    rows = height // CELL_HEIGHT
    if not MIN_ROWS <= rows <= MAX_ROWS:
        raise Skip(f"atlas has {rows} rows, expected {MIN_ROWS}-{MAX_ROWS}")
    kind = "png" if png else "webp"
    url = f"data:image/{kind};base64," + base64.b64encode(data).decode("ascii")
    return url, hashlib.sha256(data).hexdigest(), size


def describe(root_fd, entry, budget):
    """Protocol tuple for one entry, else None."""
    try:
        if entry.is_symlink():
            return "skip", f"{entry.name} is a symlink", 0
        if not entry.is_dir(follow_symlinks=False):
            return None
        pet_fd = open_component(root_fd, entry.name, DIR_FLAGS)
    except FileNotFoundError:
        return None
    except OSError as error:
        return "skip", f"cannot stat: {error.strerror}", 0
    except Skip as skip:
        return "skip", str(skip), 0
    try:
        meta, sheet = metadata(pet_fd)
        meta["sheet"], meta["digest"], size = verified_sheet(pet_fd, sheet, budget)
    except FileNotFoundError:
        return None
    except Skip as skip:
        return "skip", str(skip), 0
    finally:
        os.close(pet_fd)
    return "pet", json.dumps(meta, ensure_ascii=False, separators=(",", ":")), size


def main(root):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    problem = text_problem(root)
    if problem:
        sys.exit(f"pets directory path {problem}: {root!r}")
    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    except FileNotFoundError:
        return
    budget = MAX_SCAN_BYTES
    try:
        with os.scandir(root_fd) as entries:
            listed = list(itertools.islice(entries, MAX_ENTRIES + 1))
        if len(listed) > MAX_ENTRIES:
            print(f"more than {MAX_ENTRIES} entries in {root}, ignoring the rest", file=sys.stderr)
            del listed[MAX_ENTRIES:]
        for entry in sorted(listed, key=lambda e: e.name):
            path = os.path.join(root, entry.name)
            problem = text_problem(entry.name)
            if problem:
                print(f"skip\t{path!r}\tdirectory name {problem}")
                continue
            described = describe(root_fd, entry, budget)
            if described:
                print(f"{described[0]}\t{path}\t{described[1]}")
                budget -= described[2]
    finally:
        os.close(root_fd)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: scan.py <pets-dir>")
    main(sys.argv[1])
