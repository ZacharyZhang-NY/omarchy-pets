"""The Codex Pets package rules (PRD F4), mirrored from src/lib/package.ts with the same messages."""

import hashlib
import io
import json
import re
import unicodedata
import zipfile
import zlib

PET_KINDS = ("object", "animal", "person", "creature")
RESERVED_IDS = {"api", "pets", "upload", "login", "admin", "cli", "assets", "u", "collections"}
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_MANIFEST_BYTES = 64 * 1024
MAX_SHEET_BYTES = 6 * 1024 * 1024
SHEET_WIDTH = 1536
SHEET_HEIGHTS = {1: 1872, 2: 2288}
PACKAGE_FILES = ("pet.json", "spritesheet.webp")


class PackageError(Exception):
    """A package rule violation; the message is the user-facing text."""


def _utf16_length(text):
    return len(text.encode("utf-16-le")) // 2


def _clean_string(value, field, lo, hi):
    if not isinstance(value, str):
        raise PackageError(f"{field} must be a string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise PackageError(f"{field} is not valid Unicode") from None
    text = unicodedata.normalize("NFC", value)
    if any(unicodedata.category(ch) in ("Cc", "Zl", "Zp") for ch in text):
        raise PackageError(f"{field} contains control characters")
    if not lo <= _utf16_length(text) <= hi:
        raise PackageError(f"{field} must be {lo} to {hi} characters")
    return text


def valid_id(pet_id):
    return isinstance(pet_id, str) and 1 <= len(pet_id) <= 64 and bool(SLUG.match(pet_id)) and pet_id not in RESERVED_IDS


def parse_manifest(data):
    if len(data) > MAX_MANIFEST_BYTES:
        raise PackageError("pet.json is larger than 64 KiB")
    try:
        raw = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise PackageError("pet.json is not valid JSON") from None
    if not isinstance(raw, dict):
        raise PackageError("pet.json must be a JSON object")
    pet_id = _clean_string(raw.get("id"), "id", 1, 64)
    if not SLUG.match(pet_id):
        raise PackageError("id must be lowercase letters, digits and single hyphens, at most 64 characters")
    if pet_id in RESERVED_IDS:
        raise PackageError(f'id "{pet_id}" is reserved')
    manifest = {
        "id": pet_id,
        "displayName": _clean_string(raw.get("displayName"), "displayName", 1, 80),
        "description": _clean_string(raw.get("description"), "description", 1, 280),
        "spritesheetPath": "spritesheet.webp",
    }
    if raw.get("spritesheetPath") != "spritesheet.webp":
        raise PackageError('spritesheetPath must be "spritesheet.webp"')
    if "spriteVersionNumber" in raw:
        if raw["spriteVersionNumber"] != 2 or isinstance(raw["spriteVersionNumber"], bool):
            raise PackageError("spriteVersionNumber must be 2 when present")
        manifest["spriteVersionNumber"] = 2
    if "kind" in raw:
        if raw["kind"] not in PET_KINDS:
            raise PackageError("kind must be one of object, animal, person, creature")
        manifest["kind"] = raw["kind"]
    return manifest


def canonical_manifest(manifest):
    """The six known keys in upstream order, two-space indent, trailing newline."""
    ordered = {
        "id": manifest["id"],
        "displayName": manifest["displayName"],
        "description": manifest["description"],
        "spritesheetPath": "spritesheet.webp",
    }
    if manifest.get("spriteVersionNumber") == 2:
        ordered["spriteVersionNumber"] = 2
    if manifest.get("kind"):
        ordered["kind"] = manifest["kind"]
    return json.dumps(ordered, indent=2, ensure_ascii=False) + "\n"


def _u16(b, at):
    return b[at] | (b[at + 1] << 8)


def _u24(b, at):
    return b[at] | (b[at + 1] << 8) | (b[at + 2] << 16)


def _u32(b, at):
    return _u24(b, at) | (b[at + 3] << 24)


def _framed(canvas, frame):
    if canvas is not None and canvas != frame:
        raise PackageError("spritesheet.webp declares a canvas that differs from its image")
    return frame


def webp_size(data):
    """Width and height from the container; a VP8X canvas must equal its frame; animation is refused."""
    if len(data) < 20 or data[0:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise PackageError("spritesheet.webp is not a WebP file")
    canvas = None
    offset = 12
    while offset + 8 <= len(data):
        chunk = data[offset : offset + 4]
        length = _u32(data, offset + 4)
        start = offset + 8
        if chunk == b"VP8X" and length >= 10 and start + 10 <= len(data):
            if data[start] & 0x02:
                raise PackageError("spritesheet.webp is animated")
            canvas = (1 + _u24(data, start + 4), 1 + _u24(data, start + 7))
        elif chunk == b"VP8 " and length >= 10 and start + 10 <= len(data):
            return _framed(canvas, (_u16(data, start + 6) & 0x3FFF, _u16(data, start + 8) & 0x3FFF))
        elif chunk == b"VP8L" and length >= 5 and start + 5 <= len(data) and data[start] == 0x2F:
            b1, b2, b3, b4 = data[start + 1], data[start + 2], data[start + 3], data[start + 4]
            return _framed(canvas, (1 + (((b2 & 0x3F) << 8) | b1), 1 + (((b4 & 0x0F) << 10) | (b3 << 2) | ((b2 & 0xC0) >> 6))))
        offset = start + length + (length % 2)
    raise PackageError("spritesheet.webp is not a WebP file")


def read_sheet(data):
    if len(data) > MAX_SHEET_BYTES:
        raise PackageError("spritesheet.webp is larger than 6 MiB")
    width, height = webp_size(data)
    version = 2 if height == SHEET_HEIGHTS[2] else 1 if height == SHEET_HEIGHTS[1] else None
    if width != SHEET_WIDTH or version is None:
        raise PackageError(f"spritesheet.webp must be 1536 wide and 1872 or 2288 tall, got {width}×{height}")
    return {"width": width, "height": height, "version": version, "bytes": len(data)}


def check_version_marker(manifest, sheet):
    if sheet["version"] == 2 and manifest.get("spriteVersionNumber") != 2:
        raise PackageError('a 1536×2288 sheet needs "spriteVersionNumber": 2 in pet.json')
    if sheet["version"] == 1 and manifest.get("spriteVersionNumber") == 2:
        raise PackageError("a 1536×1872 sheet must not set spriteVersionNumber")


def sha256_hex(data):
    return hashlib.sha256(data).hexdigest()


def read_package_zip(data):
    """The two files of a downloaded package; anything else in the zip is refused before it is read."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise PackageError("the download is not a zip file") from None
    with archive:
        infos = archive.infolist()
        if sorted(info.filename for info in infos) != sorted(PACKAGE_FILES):
            raise PackageError("the package must hold exactly pet.json and spritesheet.webp")
        for info in infos:
            if info.flag_bits & 0x08:
                raise PackageError("the package uses data descriptors, which are not accepted")
            if info.flag_bits & 0x01:
                raise PackageError("the package is encrypted, which is not accepted")
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise PackageError("the package uses a compression method that is not accepted")
            if info.file_size > MAX_SHEET_BYTES:
                raise PackageError("spritesheet.webp is larger than 6 MiB")
        try:
            return archive.read("pet.json"), archive.read("spritesheet.webp")
        except (zipfile.BadZipFile, zlib.error, EOFError) as error:
            raise PackageError(f"the package is damaged: {error}") from None
