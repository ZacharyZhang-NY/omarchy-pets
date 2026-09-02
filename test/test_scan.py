import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCAN = os.path.join(HERE, "..", "scan.py")
sys.path.insert(0, os.path.dirname(SCAN))
import scan
ATLAS_V2 = os.path.join(HERE, "atlas-v2.png")
ATLAS_V1 = os.path.join(HERE, "atlas-v1.png")
MIB = 1024 * 1024


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


def lines(result):
    return result.stdout.decode("utf-8").splitlines()


def read(path):
    with open(path, "rb") as f:
        return f.read()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="omarchy-pets-")
        self.addCleanup(shutil.rmtree, self.root)
        self.base = tempfile.mkdtemp(prefix="omarchy-pets-store-")
        self.addCleanup(shutil.rmtree, self.base)
        self.store = os.path.join(self.base, sha256(self.root.encode())[:16])

    def run_scan(self, root=None, base=None):
        started = time.monotonic()
        result = subprocess.run([sys.executable, SCAN, root or self.root, base or self.base], capture_output=True, timeout=10)
        return result, time.monotonic() - started

    def pet(self, name, meta=None, sheet=None, sheet_name="spritesheet.webp", json_bytes=None):
        directory = os.path.join(self.root, name)
        os.makedirs(directory)
        if json_bytes is None:
            payload = {"id": name, "displayName": name.title(), "kind": "animal", "spritesheetPath": sheet_name}
            payload.update(meta or {})
            json_bytes = json.dumps(payload).encode("utf-8")
        with open(os.path.join(directory, "pet.json"), "wb") as f:
            f.write(json_bytes)
        os.makedirs(os.path.dirname(os.path.join(directory, sheet_name)), exist_ok=True)
        with open(os.path.join(directory, sheet_name), "wb") as f:
            f.write(vp8l_header(1536, 2288) if sheet is None else sheet)
        return directory

    def assert_skipped(self, result, name, reason):
        wanted = [l for l in lines(result) if l.startswith("skip\t" + os.path.join(self.root, name) + "\t")]
        self.assertEqual(len(wanted), 1, lines(result))
        self.assertIn(reason, wanted[0])

    def listed(self, result):
        return [os.path.basename(l.split("\t")[1]) for l in lines(result) if l.startswith("pet\t")]

    def meta(self, result, name):
        for line in lines(result):
            if line.startswith("pet\t" + os.path.join(self.root, name) + "\t"):
                return json.loads(line.split("\t")[2])
        self.fail("%s not listed: %s" % (name, lines(result)))

    def store_files(self):
        return sorted(os.listdir(self.store))

    def test_real_atlas_is_listed_with_a_private_copy(self):
        atlas = read(ATLAS_V2)
        directory = self.pet("bawi", {"displayName": "hyrax", "kind": "animal"}, sheet=atlas, sheet_name="spritesheet.png")
        result, _ = self.run_scan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b"")
        copy = os.path.join(self.store, sha256(atlas) + ".png")
        self.assertEqual(lines(result), ["pet\t%s\t%s" % (directory, json.dumps({"id": "bawi", "displayName": "hyrax", "kind": "animal", "sheet": copy}, separators=(",", ":")))])
        self.assertEqual(read(copy), atlas)
        self.assertEqual(stat.S_IMODE(os.lstat(copy).st_mode), 0o400)
        self.assertEqual(stat.S_IMODE(os.lstat(self.store).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.lstat(self.base).st_mode), 0o700)
        self.assertEqual(self.store_files(), [os.path.basename(copy)])

    def test_v1_atlas_and_every_webp_header_kind_are_accepted(self):
        self.pet("a-v1", sheet=read(ATLAS_V1), sheet_name="sheet.png")
        self.pet("b-vp8x", sheet=vp8x_header(1536, 2288))
        self.pet("c-vp8l", sheet=vp8l_header(1536, 1872))
        self.pet("d-vp8", sheet=vp8_header(1536, 2288))
        result, _ = self.run_scan()
        self.assertEqual(self.listed(result), ["a-v1", "b-vp8x", "c-vp8l", "d-vp8"])
        self.assertEqual([os.path.splitext(self.meta(result, n)["sheet"])[1] for n in ("a-v1", "b-vp8x")], [".png", ".webp"])

    def test_identical_sheets_share_one_copy_and_rescan_rewrites_nothing(self):
        self.pet("one")
        self.pet("two")
        result, _ = self.run_scan()
        self.assertEqual(self.meta(result, "one")["sheet"], self.meta(result, "two")["sheet"])
        self.assertEqual(len(self.store_files()), 1)
        copy = self.meta(result, "one")["sheet"]
        inode = os.lstat(copy).st_ino
        os.utime(copy, (1, 1))
        result, _ = self.run_scan()
        self.assertEqual(self.listed(result), ["one", "two"])
        self.assertEqual(os.lstat(copy).st_ino, inode)
        self.assertGreater(os.lstat(copy).st_mtime, time.time() - 30, "a reused copy is touched so a concurrent sweep keeps it")

    def test_short_read_after_fstat_is_rejected(self):
        data = vp8l_header(1536, 2288) + b"\0" * 1000
        directory = self.pet("shrinking", sheet=data)
        store = scan.Store(self.base, self.root)
        pet_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, pet_fd)
        with mock.patch.object(scan, "read_exact", lambda fd, size: data[:25]):
            with self.assertRaises(scan.Skip) as caught:
                scan.verified_sheet(pet_fd, "spritesheet.webp", store)
        self.assertEqual(str(caught.exception), "spritesheet.webp changed while being read")
        self.assertEqual(os.listdir(store.path), [])

    def test_store_is_locked_for_the_whole_scan(self):
        self.pet("real")
        os.makedirs(self.store, 0o700)
        lock = os.open(self.store, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, lock)
        fcntl.flock(lock, fcntl.LOCK_EX)
        with self.assertRaises(subprocess.TimeoutExpired):
            subprocess.run([sys.executable, SCAN, self.root, self.base], capture_output=True, timeout=1)
        self.assertEqual(self.store_files(), [])
        fcntl.flock(lock, fcntl.LOCK_UN)
        result, _ = self.run_scan()
        self.assertEqual(self.listed(result), ["real"])

    def test_copy_is_unaffected_by_swapping_the_source_after_the_scan(self):
        directory = self.pet("swap", sheet=vp8l_header(1536, 2288))
        result, _ = self.run_scan()
        copy = self.meta(result, "swap")["sheet"]
        with open(os.path.join(directory, "spritesheet.webp"), "wb") as f:
            f.write(vp8x_header(16384, 16384))
        self.assertEqual(read(copy), vp8l_header(1536, 2288))
        result, _ = self.run_scan()
        self.assert_skipped(result, "swap", "atlas width 16384 is not 1536")
        self.assertEqual(read(copy), vp8l_header(1536, 2288))

    def test_unused_copies_are_swept_after_a_minute(self):
        self.pet("gone")
        self.pet("stays")
        result, _ = self.run_scan()
        gone = self.meta(result, "gone")["sheet"]
        stays = self.meta(result, "stays")["sheet"]
        shutil.rmtree(os.path.join(self.root, "gone"))
        stray = os.path.join(self.store, "leftover.tmp")
        with open(stray, "wb") as f:
            f.write(b"x")
        result, _ = self.run_scan()
        self.assertEqual(self.listed(result), ["stays"])
        self.assertTrue(os.path.exists(gone), "a copy younger than a minute must survive")
        old = time.time() - 120
        for path in (gone, stays, stray):
            os.utime(path, (old, old))
        result, _ = self.run_scan()
        self.assertEqual(self.store_files(), [os.path.basename(stays)])

    def test_missing_root_sweeps_its_store(self):
        self.pet("gone")
        result, _ = self.run_scan()
        copy = self.meta(result, "gone")["sheet"]
        old = time.time() - 120
        os.utime(copy, (old, old))
        shutil.rmtree(self.root)
        result, _ = self.run_scan()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        self.assertEqual(self.store_files(), [])
        os.makedirs(self.root)

    def test_store_budget_is_256_mib_per_root(self):
        for i in range(9):
            directory = self.pet("big%d" % i, sheet=vp8l_header(1536, 2288) + bytes([i]))
            os.truncate(os.path.join(directory, "spritesheet.webp"), 32 * MIB)
        result, elapsed = self.run_scan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.listed(result), ["big%d" % i for i in range(8)])
        self.assert_skipped(result, "big8", "spritesheet.webp is 33554432 bytes, over the 268435456 byte store budget")
        self.assertEqual(len(self.store_files()), 8)
        self.assertLess(elapsed, 8)

    def test_store_must_be_a_private_directory(self):
        for mode in (0o755, 0o500, 0o600):
            os.makedirs(self.store, mode)
            result, _ = self.run_scan()
            self.assertNotEqual(result.returncode, 0, mode)
            self.assertIn("mode 0700", result.stderr.decode())
            self.assertEqual(result.stdout, b"")
            os.rmdir(self.store)
        os.symlink(self.root, self.store)
        result, _ = self.run_scan()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mode 0700", result.stderr.decode())

    def test_precreated_digest_entries_are_replaced_unless_regular_and_complete(self):
        data = vp8l_header(1536, 2288)
        self.pet("real", sheet=data)
        os.makedirs(self.store, 0o700)
        digest = os.path.join(self.store, sha256(data) + ".webp")
        os.symlink("/etc/hostname", digest)
        result, _ = self.run_scan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.meta(result, "real")["sheet"], digest)
        self.assertTrue(stat.S_ISREG(os.lstat(digest).st_mode))
        self.assertEqual(read(digest), data)
        for wrong in (b"short", data[:-1] + b"\0"):
            os.chmod(digest, 0o600)
            with open(digest, "wb") as f:
                f.write(wrong)
            os.chmod(digest, 0o400)
            result, _ = self.run_scan()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(read(digest), data)
            self.assertEqual(stat.S_IMODE(os.lstat(digest).st_mode), 0o400)

    def test_failed_copy_leaves_no_temporary_file(self):
        data = vp8l_header(1536, 2288)
        self.pet("real", sheet=data)
        os.makedirs(self.store, 0o700)
        os.mkdir(os.path.join(self.store, sha256(data) + ".webp"))
        result, _ = self.run_scan()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Is a directory", result.stderr.decode())
        self.assertEqual(self.store_files(), [sha256(data) + ".webp"])

    def test_relative_store_path_fails_loudly(self):
        result, _ = self.run_scan(base="relative-store")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute", result.stderr.decode())
        self.assertEqual(result.stdout, b"")

    def test_store_path_with_control_characters_fails_loudly(self):
        result, _ = self.run_scan(base=os.path.join(self.base, "bad\tstore"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("control characters", result.stderr.decode())
        self.assertEqual(result.stdout, b"")

    def test_non_ascii_names_round_trip(self):
        self.pet("guga", {"displayName": "咕嘎", "kind": "creature"})
        result, _ = self.run_scan()
        self.assertEqual(self.meta(result, "guga")["displayName"], "咕嘎")

    def test_fifo_pet_json_is_skipped_without_blocking(self):
        directory = os.path.join(self.root, "pipe")
        os.makedirs(directory)
        os.mkfifo(os.path.join(directory, "pet.json"))
        result, elapsed = self.run_scan()
        self.assert_skipped(result, "pipe", "pet.json is not a regular file")
        self.assertLess(elapsed, 2)

    def test_fifo_sheet_is_skipped_without_blocking(self):
        directory = self.pet("pipesheet")
        os.remove(os.path.join(directory, "spritesheet.webp"))
        os.mkfifo(os.path.join(directory, "spritesheet.webp"))
        result, elapsed = self.run_scan()
        self.assert_skipped(result, "pipesheet", "spritesheet.webp is not a regular file")
        self.assertLess(elapsed, 2)

    def test_symlinked_files_and_directories_are_rejected(self):
        real = self.pet("real")
        linked_json = self.pet("linkjson")
        os.remove(os.path.join(linked_json, "pet.json"))
        os.symlink(os.path.join(real, "pet.json"), os.path.join(linked_json, "pet.json"))
        linked_sheet = self.pet("linksheet")
        os.remove(os.path.join(linked_sheet, "spritesheet.webp"))
        os.symlink(os.path.join(real, "spritesheet.webp"), os.path.join(linked_sheet, "spritesheet.webp"))
        os.symlink(real, os.path.join(self.root, "linkdir"))
        result, _ = self.run_scan()
        self.assert_skipped(result, "linkjson", "pet.json is a symlink")
        self.assert_skipped(result, "linksheet", "spritesheet.webp is a symlink")
        self.assert_skipped(result, "linkdir", "linkdir is a symlink")
        self.assertEqual(self.listed(result), ["real"])

    def test_symlinked_path_component_is_rejected_and_real_subdirectory_accepted(self):
        real = self.pet("real", {"spritesheetPath": "art/sheet.webp"}, sheet_name="art/sheet.webp")
        linked = self.pet("linkcomponent", {"spritesheetPath": "art/sheet.webp"})
        os.symlink(os.path.join(real, "art"), os.path.join(linked, "art"))
        self.pet("filecomponent", {"spritesheetPath": "spritesheet.webp/sheet.webp"})
        result, _ = self.run_scan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_skipped(result, "linkcomponent", "art is a symlink")
        self.assert_skipped(result, "filecomponent", "spritesheet.webp: Not a directory")
        self.assertEqual(self.listed(result), ["real"])

    def test_pet_json_size_limit_is_64_kib_inclusive(self):
        padded = json.dumps({"id": "big", "displayName": "Big", "kind": "object", "spritesheetPath": "spritesheet.webp"}).encode()
        self.pet("big", json_bytes=padded + b" " * (64 * 1024 - len(padded)))
        self.pet("bigger", json_bytes=padded + b" " * (64 * 1024 + 1 - len(padded)))
        result, _ = self.run_scan()
        self.assertEqual(self.listed(result), ["big"])
        self.assert_skipped(result, "bigger", "pet.json is 65537 bytes, limit 65536")

    def test_sheet_file_size_limit_is_32_mib(self):
        directory = self.pet("sparse")
        os.truncate(os.path.join(directory, "spritesheet.webp"), 32 * MIB + 1)
        result, elapsed = self.run_scan()
        self.assert_skipped(result, "sparse", "spritesheet.webp is 33554433 bytes, limit 33554432")
        self.assertLess(elapsed, 2)
        self.assertEqual(self.store_files(), [])

    def test_dimension_rules(self):
        self.pet("wide", sheet=vp8x_header(1537, 2288))
        self.pet("bomb", sheet=vp8x_header(16384, 16384))
        self.pet("ragged", sheet=vp8l_header(1536, 2289))
        self.pet("short", sheet=vp8l_header(1536, 8 * 208))
        self.pet("tall", sheet=vp8l_header(1536, 33 * 208))
        self.pet("tallest-ok", sheet=vp8l_header(1536, 32 * 208))
        self.pet("shortest-ok", sheet=png_header(1536, 9 * 208))
        self.pet("unknown", sheet=b"GIF89a" + b"\x00" * 30)
        result, _ = self.run_scan()
        self.assert_skipped(result, "wide", "atlas width 1537 is not 1536")
        self.assert_skipped(result, "bomb", "atlas width 16384 is not 1536")
        self.assert_skipped(result, "ragged", "atlas height 2289 is not a multiple of 208")
        self.assert_skipped(result, "short", "atlas has 8 rows, expected 9-32")
        self.assert_skipped(result, "tall", "atlas has 33 rows, expected 9-32")
        self.assert_skipped(result, "unknown", "spritesheet.webp is not a WebP or PNG file")
        self.assertEqual(self.listed(result), ["shortest-ok", "tallest-ok"])
        self.assertEqual(len(self.store_files()), 2)

    def test_entry_cap_is_500_with_a_warning(self):
        for i in range(501):
            self.pet("pet%03d" % i)
        result, elapsed = self.run_scan()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(lines(result)), 500)
        self.assertIn("more than 500 entries", result.stderr.decode())
        self.assertLess(elapsed, 5)

    def test_long_strings_are_truncated(self):
        self.pet("long", {"id": "x" * 200, "displayName": "n" * 200, "kind": "k" * 100})
        result, _ = self.run_scan()
        meta = self.meta(result, "long")
        self.assertEqual((len(meta["id"]), len(meta["displayName"]), len(meta["kind"])), (80, 80, 32))

    def test_bad_sprite_paths_are_rejected(self):
        self.pet("dotdot", {"spritesheetPath": "../spritesheet.webp"})
        self.pet("absolute", {"spritesheetPath": "/etc/passwd"})
        self.pet("control", {"spritesheetPath": "sheet\x01.webp"})
        self.pet("toolong", {"spritesheetPath": "s" * 256})
        self.pet("empty", {"spritesheetPath": ""})
        self.pet("missing", {"spritesheetPath": "nothere.webp"})
        result, _ = self.run_scan()
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
        result, _ = self.run_scan()
        self.assert_skipped(result, "notjson", "pet.json is not valid JSON")
        self.assert_skipped(result, "binary", "pet.json is not valid JSON")
        self.assert_skipped(result, "array", "pet.json is not a JSON object")
        self.assert_skipped(result, "noid", "pet.json has no id")
        self.assert_skipped(result, "emptyid", "pet.json has no id")
        self.assert_skipped(result, "nopath", "spritesheetPath is not a plain relative path")

    def test_optional_fields_are_omitted_when_absent(self):
        self.pet("bare", json_bytes=b'{"id": "bare", "spritesheetPath": "spritesheet.webp"}')
        result, _ = self.run_scan()
        self.assertEqual(self.meta(result, "bare"), {"id": "bare", "sheet": os.path.join(self.store, sha256(vp8l_header(1536, 2288)) + ".webp")})

    def test_missing_root_and_non_pet_entries_are_silent(self):
        result, _ = self.run_scan(root=os.path.join(self.root, "nope"))
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        os.makedirs(os.path.join(self.root, "emptydir"))
        with open(os.path.join(self.root, "stray.zip"), "wb"):
            pass
        result, _ = self.run_scan()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))

    def test_tab_in_directory_name_is_reported_safely(self):
        self.pet("tab\tname")
        result, _ = self.run_scan()
        self.assertEqual(lines(result), ["skip\t%s\tdirectory name has control characters" % repr(os.path.join(self.root, "tab\tname"))])

    def test_output_is_sorted_by_directory_name(self):
        for name in ("zeta", "alpha", "Mid", "beta"):
            self.pet(name)
        result, _ = self.run_scan()
        self.assertEqual(self.listed(result), ["Mid", "alpha", "beta", "zeta"])

    def test_root_under_unsearchable_parent_fails_loudly(self):
        parent = os.path.join(self.root, "parent")
        root = os.path.join(parent, "pets")
        os.makedirs(root)
        os.chmod(parent, 0)
        self.addCleanup(os.chmod, parent, 0o700)
        result, _ = self.run_scan(root=root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Permission denied", result.stderr.decode())

    def test_symlink_loop_entry_is_skipped_and_the_rest_listed(self):
        self.pet("good")
        os.symlink("loop", os.path.join(self.root, "loop"))
        result, _ = self.run_scan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_skipped(result, "loop", "loop is a symlink")
        self.assertEqual(self.listed(result), ["good"])

    def test_unpaired_surrogates_in_metadata_are_skipped(self):
        self.pet("badname", json_bytes=b'{"id": "badname", "displayName": "\\ud800", "spritesheetPath": "spritesheet.webp"}')
        self.pet("badpath", json_bytes=b'{"id": "badpath", "spritesheetPath": "\\ud800.webp"}')
        self.pet("good")
        result, _ = self.run_scan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_skipped(result, "badname", "displayName is not valid UTF-8")
        self.assert_skipped(result, "badpath", "spritesheetPath is not a plain relative path")
        self.assertEqual(self.listed(result), ["good"])

    def test_root_path_with_control_characters_fails_loudly(self):
        root = os.path.join(self.root, "bad\tdir")
        os.makedirs(root)
        result, _ = self.run_scan(root=root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("control characters", result.stderr.decode())
        self.assertEqual(result.stdout, b"")

    def test_16_bit_png_is_rejected(self):
        self.pet("deep", sheet=png_header(1536, 2288, depth=16))
        self.pet("eight", sheet=png_header(1536, 2288, depth=8))
        result, _ = self.run_scan()
        self.assert_skipped(result, "deep", "PNG bit depth 16 is not supported")
        self.assertEqual(self.listed(result), ["eight"])

    def test_c1_controls_are_rejected_and_joiner_emoji_accepted(self):
        self.pet("nel", {"displayName": "a\u0085b"})
        self.pet("family", {"displayName": "\U0001F468\u200D\U0001F469\u200D\U0001F467"})
        self.pet("dir\u0085name")
        result, _ = self.run_scan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_skipped(result, "nel", "displayName has control characters")
        self.assertIn("skip\t%s\tdirectory name has control characters" % repr(os.path.join(self.root, "dir\u0085name")), lines(result))
        self.assertEqual(self.meta(result, "family")["displayName"], "\U0001F468\u200D\U0001F469\u200D\U0001F467")

    def test_deeply_nested_json_is_skipped_not_fatal(self):
        self.pet("nested", json_bytes=b"[" * 20000)
        self.pet("good")
        result, _ = self.run_scan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_skipped(result, "nested", "pet.json is not valid JSON")
        self.assertEqual(self.listed(result), ["good"])

    def test_truncated_png_header_is_skipped_not_fatal(self):
        self.pet("cut", sheet=png_header(1536, 2288)[:24])
        self.pet("good")
        result, _ = self.run_scan()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_skipped(result, "cut", "spritesheet.webp is not a WebP or PNG file")
        self.assertEqual(self.listed(result), ["good"])

    def test_unreadable_root_fails_loudly(self):
        os.chmod(self.root, 0)
        self.addCleanup(os.chmod, self.root, 0o700)
        result, _ = self.run_scan()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Permission denied", result.stderr.decode())


if __name__ == "__main__":
    unittest.main()
