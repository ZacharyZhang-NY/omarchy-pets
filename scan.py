#!/usr/bin/env python3
"""Lists the valid Codex Pets under one directory."""
import errno
import itertools
import json
import os
import stat
import sys
import unicodedata

MAX_ENTRIES = 500
MAX_JSON_BYTES = 64 * 1024
MAX_SHEET_BYTES = 32 * 1024 * 1024
HEADER_BYTES = 30
SHEET_WIDTH = 192 * 8
CELL_HEIGHT = 208
MIN_ROWS = 9
MAX_ROWS = 32
MAX_TEXT = 80
MAX_KIND = 32
MAX_PATH = 255
OPEN_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOCTTY


class Skip(Exception):
    """Not a usable pet; the message says why."""


def read_regular(path, limit, want):
    """Descriptor-bound read: no symlink, regular file, bounded size."""
    name = os.path.basename(path)
    try:
        fd = os.open(path, OPEN_FLAGS)
    except FileNotFoundError:
        raise
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise Skip(f"{name} is a symlink") from None
        raise Skip(f"{name}: {error.strerror}") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise Skip(f"{name} is not a regular file")
        if info.st_size > limit:
            raise Skip(f"{name} is {info.st_size} bytes, limit {limit}")
        chunks = []
        remaining = min(want, info.st_size)
        while remaining > 0:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


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


def metadata(directory):
    """Validated pet.json fields and the sprite sheet path."""
    data = read_regular(os.path.join(directory, "pet.json"), MAX_JSON_BYTES, MAX_JSON_BYTES)
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
    out["spritesheetPath"] = sheet
    return out, sheet


def describe(entry):
    """Protocol tuple for one entry, or None."""
    try:
        if not entry.is_dir():
            return None
    except OSError as error:
        return "skip", f"cannot stat: {error.strerror}"
    try:
        meta, sheet = metadata(entry.path)
    except FileNotFoundError:
        return None
    except Skip as skip:
        return "skip", str(skip)
    try:
        header = read_regular(os.path.join(entry.path, sheet), MAX_SHEET_BYTES, HEADER_BYTES)
    except FileNotFoundError:
        return "skip", f"spritesheet missing: {sheet}"
    except Skip as skip:
        return "skip", str(skip)
    size = sheet_size(header)
    if size is None:
        return "skip", f"{os.path.basename(sheet)} is not a WebP or PNG file"
    if header[:4] == b"\x89PNG" and header[24] > 8:
        return "skip", f"PNG bit depth {header[24]} is not supported"
    width, height = size
    if width != SHEET_WIDTH:
        return "skip", f"atlas width {width} is not {SHEET_WIDTH}"
    if height % CELL_HEIGHT:
        return "skip", f"atlas height {height} is not a multiple of {CELL_HEIGHT}"
    rows = height // CELL_HEIGHT
    if not MIN_ROWS <= rows <= MAX_ROWS:
        return "skip", f"atlas has {rows} rows, expected {MIN_ROWS}-{MAX_ROWS}"
    return "pet", json.dumps(meta, ensure_ascii=False, separators=(",", ":"))


def main(root):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    problem = text_problem(root)
    if problem:
        sys.exit(f"pets directory path {problem}: {root!r}")
    try:
        os.stat(root)
    except FileNotFoundError:
        return
    with os.scandir(root) as entries:
        listed = list(itertools.islice(entries, MAX_ENTRIES + 1))
    if len(listed) > MAX_ENTRIES:
        print(f"more than {MAX_ENTRIES} entries in {root}, ignoring the rest", file=sys.stderr)
        del listed[MAX_ENTRIES:]
    for entry in sorted(listed, key=lambda e: e.name):
        problem = text_problem(entry.name)
        if problem:
            print(f"skip\t{entry.path!r}\tdirectory name {problem}")
            continue
        described = describe(entry)
        if described:
            print(f"{described[0]}\t{entry.path}\t{described[1]}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: scan.py <pets-dir>")
    main(sys.argv[1])
