import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCAN = os.path.join(HERE, "..", "scan.py")
ATLAS_V2 = os.path.join(HERE, "atlas-v2.png")
ATLAS_V1 = os.path.join(HERE, "atlas-v1.png")
KIB = 1024
MIB = 1024 * KIB


def png_header(width, height, depth=8):
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes([depth, 6, 0, 0, 0])


def webp(chunk):
    return b"RIFF" + (4 + len(chunk)).to_bytes(4, "little") + b"WEBP" + chunk


def vp8x_header(width, height):
    return webp(b"VP8X" + (10).to_bytes(4, "little") + b"\x00\x00\x00\x00" + (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little"))


def vp8l_header(width, height):
    bits = (width - 1) | ((height - 1) << 14)
    return webp(b"VP8L" + (5).to_bytes(4, "little") + b"\x2f" + bits.to_bytes(4, "little"))


def vp8_header(width, height):
    return webp(b"VP8 " + (10).to_bytes(4, "little") + b"\x00\x00\x00" + b"\x9d\x01\x2a" + width.to_bytes(2, "little") + height.to_bytes(2, "little"))


def run(root):
    started = time.monotonic()
    result = subprocess.run([sys.executable, SCAN, root], capture_output=True, timeout=10)
    return result, time.monotonic() - started


def lines(result):
    return result.stdout.decode("utf-8").splitlines()


def read(path):
    with open(path, "rb") as f:
        return f.read()


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="omarchy-pets-")
        self.addCleanup(shutil.rmtree, self.root)

    def pet(self, name, meta=None, sheet=None, sheet_name="spritesheet.webp", json_bytes=None):
        directory = os.path.join(self.root, name)
        os.makedirs(directory)
        if json_bytes is None:
            payload = {"id": name, "displayName": name.title(), "kind": "animal", "spritesheetPath": sheet_name}
            payload.update(meta or {})
            json_bytes = json.dumps(payload).encode("utf-8")
        with open(os.path.join(directory, "pet.json"), "wb") as f:
            f.write(json_bytes)
        with open(os.path.join(directory, sheet_name), "wb") as f:
            f.write(vp8l_header(1536, 2288) if sheet is None else sheet)
        return directory

    def assert_skipped(self, result, name, reason):
        wanted = [l for l in lines(result) if l.startswith("skip\t" + os.path.join(self.root, name) + "\t")]
        self.assertEqual(len(wanted), 1, lines(result))
        self.assertIn(reason, wanted[0])

    def test_real_atlas_is_listed_with_exact_fields(self):
        directory = self.pet("bawi", {"displayName": "hyrax", "kind": "animal"}, sheet=read(ATLAS_V2), sheet_name="spritesheet.png")
        result, _ = run(self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(lines(result), ["pet\t%s\t%s" % (directory, json.dumps({"id": "bawi", "displayName": "hyrax", "kind": "animal", "spritesheetPath": "spritesheet.png"}, separators=(",", ":")))])
        self.assertEqual(result.stderr, b"")

    def test_v1_atlas_and_every_webp_header_kind_are_accepted(self):
        self.pet("a-v1", sheet=read(ATLAS_V1), sheet_name="sheet.png")
        self.pet("b-vp8x", sheet=vp8x_header(1536, 2288))
        self.pet("c-vp8l", sheet=vp8l_header(1536, 1872))
        self.pet("d-vp8", sheet=vp8_header(1536, 2288))
        result, _ = run(self.root)
        self.assertEqual([l.split("\t")[0] + " " + os.path.basename(l.split("\t")[1]) for l in lines(result)], ["pet a-v1", "pet b-vp8x", "pet c-vp8l", "pet d-vp8"])

    def test_non_ascii_names_round_trip(self):
        directory = self.pet("guga", {"displayName": "咕嘎", "kind": "creature"})
        result, _ = run(self.root)
        self.assertEqual(json.loads(lines(result)[0].split("\t")[2])["displayName"], "咕嘎")

    def test_fifo_pet_json_is_skipped_without_blocking(self):
        directory = os.path.join(self.root, "pipe")
        os.makedirs(directory)
        os.mkfifo(os.path.join(directory, "pet.json"))
        result, elapsed = run(self.root)
        self.assert_skipped(result, "pipe", "pet.json is not a regular file")
        self.assertLess(elapsed, 2)

    def test_fifo_sheet_is_skipped_without_blocking(self):
        directory = self.pet("pipesheet")
        os.remove(os.path.join(directory, "spritesheet.webp"))
        os.mkfifo(os.path.join(directory, "spritesheet.webp"))
        result, elapsed = run(self.root)
        self.assert_skipped(result, "pipesheet", "spritesheet.webp is not a regular file")
        self.assertLess(elapsed, 2)

    def test_symlinked_files_are_rejected_but_symlinked_directory_is_accepted(self):
        real = self.pet("real")
        linked_json = self.pet("linkjson")
        os.remove(os.path.join(linked_json, "pet.json"))
        os.symlink(os.path.join(real, "pet.json"), os.path.join(linked_json, "pet.json"))
        linked_sheet = self.pet("linksheet")
        os.remove(os.path.join(linked_sheet, "spritesheet.webp"))
        os.symlink(os.path.join(real, "spritesheet.webp"), os.path.join(linked_sheet, "spritesheet.webp"))
        os.symlink(real, os.path.join(self.root, "linkdir"))
        result, _ = run(self.root)
        self.assert_skipped(result, "linkjson", "pet.json is a symlink")
        self.assert_skipped(result, "linksheet", "spritesheet.webp is a symlink")
        self.assertEqual([os.path.basename(l.split("\t")[1]) for l in lines(result) if l.startswith("pet\t")], ["linkdir", "real"])

    def test_pet_json_size_limit_is_64_kib_inclusive(self):
        padded = json.dumps({"id": "big", "displayName": "Big", "kind": "object", "spritesheetPath": "spritesheet.webp"}).encode()
        self.pet("big", json_bytes=padded + b" " * (64 * KIB - len(padded)))
        self.pet("bigger", json_bytes=padded + b" " * (64 * KIB + 1 - len(padded)))
        result, _ = run(self.root)
        self.assertTrue(any(l.startswith("pet\t" + os.path.join(self.root, "big") + "\t") for l in lines(result)), lines(result))
        self.assert_skipped(result, "bigger", "pet.json is 65537 bytes, limit 65536")

    def test_sheet_file_size_limit_is_32_mib(self):
        directory = self.pet("sparse")
        os.truncate(os.path.join(directory, "spritesheet.webp"), 32 * MIB + 1)
        result, elapsed = run(self.root)
        self.assert_skipped(result, "sparse", "spritesheet.webp is 33554433 bytes, limit 33554432")
        self.assertLess(elapsed, 2)

    def test_dimension_rules(self):
        self.pet("wide", sheet=vp8x_header(1537, 2288))
        self.pet("bomb", sheet=vp8x_header(16384, 16384))
        self.pet("ragged", sheet=vp8l_header(1536, 2289))
        self.pet("short", sheet=vp8l_header(1536, 8 * 208))
        self.pet("tall", sheet=vp8l_header(1536, 33 * 208))
        self.pet("tallest-ok", sheet=vp8l_header(1536, 32 * 208))
        self.pet("shortest-ok", sheet=png_header(1536, 9 * 208))
        self.pet("unknown", sheet=b"GIF89a" + b"\x00" * 30)
        result, _ = run(self.root)
        self.assert_skipped(result, "wide", "atlas width 1537 is not 1536")
        self.assert_skipped(result, "bomb", "atlas width 16384 is not 1536")
        self.assert_skipped(result, "ragged", "atlas height 2289 is not a multiple of 208")
        self.assert_skipped(result, "short", "atlas has 8 rows, expected 9-32")
        self.assert_skipped(result, "tall", "atlas has 33 rows, expected 9-32")
        self.assert_skipped(result, "unknown", "spritesheet.webp is not a WebP or PNG file")
        self.assertEqual([os.path.basename(l.split("\t")[1]) for l in lines(result) if l.startswith("pet\t")], ["shortest-ok", "tallest-ok"])

    def test_entry_cap_is_500_with_a_warning(self):
        for i in range(501):
            self.pet("pet%03d" % i)
        result, elapsed = run(self.root)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(lines(result)), 500)
        self.assertIn("more than 500 entries", result.stderr.decode())
        self.assertLess(elapsed, 5)

    def test_long_strings_are_truncated(self):
        self.pet("long", {"id": "x" * 200, "displayName": "n" * 200, "kind": "k" * 100})
        result, _ = run(self.root)
        meta = json.loads(lines(result)[0].split("\t")[2])
        self.assertEqual((len(meta["id"]), len(meta["displayName"]), len(meta["kind"])), (80, 80, 32))

    def test_bad_sprite_paths_are_rejected(self):
        self.pet("dotdot", {"spritesheetPath": "../spritesheet.webp"})
        self.pet("absolute", {"spritesheetPath": "/etc/passwd"})
        self.pet("control", {"spritesheetPath": "sheet\x01.webp"})
        self.pet("toolong", {"spritesheetPath": "s" * 256})
        self.pet("empty", {"spritesheetPath": ""})
        self.pet("missing", {"spritesheetPath": "nothere.webp"})
        result, _ = run(self.root)
        for name in ("dotdot", "absolute", "control", "toolong", "empty"):
            self.assert_skipped(result, name, "spritesheetPath is not a plain relative path")
        self.assert_skipped(result, "missing", "spritesheet missing: nothere.webp")

    def test_bad_metadata_is_rejected(self):
        self.pet("notjson", json_bytes=b"{nope")
        self.pet("array", json_bytes=b"[1]")
        self.pet("noid", json_bytes=b'{"spritesheetPath": "spritesheet.webp"}')
        self.pet("emptyid", json_bytes=b'{"id": "", "spritesheetPath": "spritesheet.webp"}')
        self.pet("nopath", json_bytes=b'{"id": "x"}')
        self.pet("binary", json_bytes=b"\xff\xfe\x00")
        result, _ = run(self.root)
        self.assert_skipped(result, "notjson", "pet.json is not valid JSON")
        self.assert_skipped(result, "binary", "pet.json is not valid JSON")
        self.assert_skipped(result, "array", "pet.json is not a JSON object")
        self.assert_skipped(result, "noid", "pet.json has no id")
        self.assert_skipped(result, "emptyid", "pet.json has no id")
        self.assert_skipped(result, "nopath", "spritesheetPath is not a plain relative path")

    def test_optional_fields_are_omitted_when_absent(self):
        self.pet("bare", json_bytes=b'{"id": "bare", "spritesheetPath": "spritesheet.webp"}')
        result, _ = run(self.root)
        self.assertEqual(json.loads(lines(result)[0].split("\t")[2]), {"id": "bare", "spritesheetPath": "spritesheet.webp"})

    def test_missing_root_and_non_pet_entries_are_silent(self):
        result, _ = run(os.path.join(self.root, "nope"))
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        os.makedirs(os.path.join(self.root, "emptydir"))
        with open(os.path.join(self.root, "stray.zip"), "wb"):
            pass
        result, _ = run(self.root)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))

    def test_tab_in_directory_name_is_reported_safely(self):
        self.pet("tab\tname")
        result, _ = run(self.root)
        self.assertEqual(lines(result), ["skip\t%s\tdirectory name has control characters" % repr(os.path.join(self.root, "tab\tname"))])

    def test_output_is_sorted_by_directory_name(self):
        for name in ("zeta", "alpha", "Mid", "beta"):
            self.pet(name)
        result, _ = run(self.root)
        self.assertEqual([os.path.basename(l.split("\t")[1]) for l in lines(result)], ["Mid", "alpha", "beta", "zeta"])

    def test_root_under_unsearchable_parent_fails_loudly(self):
        parent = os.path.join(self.root, "parent")
        root = os.path.join(parent, "pets")
        os.makedirs(root)
        os.chmod(parent, 0)
        self.addCleanup(os.chmod, parent, 0o700)
        result, _ = run(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Permission denied", result.stderr.decode())

    def test_symlink_loop_entry_is_skipped_and_the_rest_listed(self):
        self.pet("good")
        os.symlink("loop", os.path.join(self.root, "loop"))
        result, _ = run(self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_skipped(result, "loop", "cannot stat: Too many levels of symbolic links")
        self.assertEqual([os.path.basename(l.split("\t")[1]) for l in lines(result) if l.startswith("pet\t")], ["good"])

    def test_unpaired_surrogates_in_metadata_are_skipped(self):
        self.pet("badname", json_bytes=b'{"id": "badname", "displayName": "\\ud800", "spritesheetPath": "spritesheet.webp"}')
        self.pet("badpath", json_bytes=b'{"id": "badpath", "spritesheetPath": "\\ud800.webp"}')
        self.pet("good")
        result, _ = run(self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_skipped(result, "badname", "displayName is not valid UTF-8")
        self.assert_skipped(result, "badpath", "spritesheetPath is not a plain relative path")
        self.assertEqual([os.path.basename(l.split("\t")[1]) for l in lines(result) if l.startswith("pet\t")], ["good"])

    def test_root_path_with_control_characters_fails_loudly(self):
        root = os.path.join(self.root, "bad\tdir")
        os.makedirs(root)
        result, _ = run(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("control characters", result.stderr.decode())
        self.assertEqual(result.stdout, b"")

    def test_16_bit_png_is_rejected(self):
        self.pet("deep", sheet=png_header(1536, 2288, depth=16))
        self.pet("eight", sheet=png_header(1536, 2288, depth=8))
        result, _ = run(self.root)
        self.assert_skipped(result, "deep", "PNG bit depth 16 is not supported")
        self.assertEqual([os.path.basename(l.split("\t")[1]) for l in lines(result) if l.startswith("pet\t")], ["eight"])

    def test_c1_controls_are_rejected_and_joiner_emoji_accepted(self):
        self.pet("nel", {"displayName": "a\u0085b"})
        self.pet("family", {"displayName": "\U0001F468\u200D\U0001F469\u200D\U0001F467"})
        self.pet("dir\u0085name")
        result, _ = run(self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_skipped(result, "nel", "displayName has control characters")
        self.assertIn("skip\t%s\tdirectory name has control characters" % repr(os.path.join(self.root, "dir\u0085name")), lines(result))
        family = [l for l in lines(result) if l.startswith("pet\t" + os.path.join(self.root, "family") + "\t")]
        self.assertEqual(json.loads(family[0].split("\t")[2])["displayName"], "\U0001F468\u200D\U0001F469\u200D\U0001F467")

    def test_deeply_nested_json_is_skipped_not_fatal(self):
        self.pet("nested", json_bytes=b"[" * 20000)
        self.pet("good")
        result, _ = run(self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_skipped(result, "nested", "pet.json is not valid JSON")
        self.assertEqual([os.path.basename(l.split("\t")[1]) for l in lines(result) if l.startswith("pet\t")], ["good"])

    def test_truncated_png_header_is_skipped_not_fatal(self):
        self.pet("cut", sheet=png_header(1536, 2288)[:24])
        self.pet("good")
        result, _ = run(self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_skipped(result, "cut", "spritesheet.webp is not a WebP or PNG file")
        self.assertEqual([os.path.basename(l.split("\t")[1]) for l in lines(result) if l.startswith("pet\t")], ["good"])

    def test_unreadable_root_fails_loudly(self):
        os.chmod(self.root, 0)
        self.addCleanup(os.chmod, self.root, 0o700)
        result, _ = run(self.root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Permission denied", result.stderr.decode())


if __name__ == "__main__":
    unittest.main()
