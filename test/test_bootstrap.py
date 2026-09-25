"""bootstrap.py against a temp home and a local server: the command line lands, the default pet lands, and it runs once."""

import hashlib
import http.server
import io
import json
import os
import stat
import subprocess
import tempfile
import threading
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "bootstrap.py")


def chunk(fourcc, data):
    padded = data + (b"\0" if len(data) % 2 else b"")
    return fourcc.encode() + len(data).to_bytes(4, "little") + padded


def riff(chunks):
    body = b"".join(chunks)
    return b"RIFF" + (len(body) + 4).to_bytes(4, "little") + b"WEBP" + body


def u24(n):
    return n.to_bytes(3, "little")


SHEET = riff([
    chunk("VP8X", bytes([0, 0, 0, 0]) + u24(1536 - 1) + u24(2288 - 1)),
    chunk("VP8 ", bytes([0, 0, 0, 0x9D, 0x01, 0x2A]) + (1536).to_bytes(2, "little") + (2288).to_bytes(2, "little") + b"\0\0"),
])
MANIFEST = (json.dumps({"id": "guga", "displayName": "咕嘎", "description": "A penguin.", "spritesheetPath": "spritesheet.webp", "spriteVersionNumber": 2, "kind": "creature"}, indent=2) + "\n").encode()


def package_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("pet.json", MANIFEST)
        archive.writestr("spritesheet.webp", SHEET)
    return buffer.getvalue()


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == "/api/pets/guga/share-data":
            body = json.dumps({"pet": {"id": "guga", "downloadUrl": "/api/pets/guga/download?v=1", "validationReport": {"sha256": hashlib.sha256(SHEET).hexdigest(), "spriteVersionNumber": 2}}}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path == "/api/pets/guga/download?v=1":
            body = package_zip()
            self.send_response(200); self.send_header("Content-Type", "application/zip"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            body = b'{"error":"pet not found"}'
            self.send_response(404); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.home = tempfile.TemporaryDirectory()
        self.cli = os.path.join(self.home.name, ".local", "bin", "omarchy-pets")
        self.pets = os.path.join(self.home.name, ".omarchy-pets", "pets")
        self.marker = os.path.join(self.home.name, ".omarchy-pets", "bootstrap.done")

    def tearDown(self):
        self.httpd.shutdown()
        self.home.cleanup()

    def run_script(self):
        env = {"HOME": self.home.name, "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "OMARCHY_PETS_API_BASE": f"http://127.0.0.1:{self.httpd.server_port}"}
        return subprocess.run(["python3", SCRIPT], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)

    def test_first_load_writes_the_command_line_and_the_default_pet_then_stops(self):
        done = self.run_script()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(stat.S_IMODE(os.stat(self.cli).st_mode), 0o755)
        version = subprocess.run([self.cli, "--version"], capture_output=True, text=True)
        self.assertRegex(version.stdout, r"^omarchy-pets \d+\.\d+\.\d+")
        with open(os.path.join(self.pets, "guga", "spritesheet.webp"), "rb") as handle:
            self.assertEqual(handle.read(), SHEET)
        self.assertIn("wrote", done.stderr)
        self.assertIn("installed: ", done.stderr)
        with open(self.marker) as handle:
            self.assertTrue(handle.read().startswith("cli written, guga installed "))
        again = self.run_script()
        self.assertEqual(again.returncode, 0)
        self.assertEqual(again.stderr, "")
        self.assertFalse(os.path.exists(os.path.join(ROOT, "cli", "omarchy_pets", "__pycache__")), "bytecode written under the plugin folder")
        self.assertFalse(os.path.exists(os.path.join(self.home.name, ".omarchy-pets", "bootstrap.lock")))

    def test_a_second_bootstrap_waits_for_the_first_and_a_dead_one_is_taken_over(self):
        state = os.path.join(self.home.name, ".omarchy-pets")
        os.makedirs(state)
        lock = os.path.join(state, "bootstrap.lock")
        with open(lock, "w") as handle:
            handle.write(f"{os.getpid()}\n")
        busy = self.run_script()
        self.assertEqual(busy.returncode, 0)
        self.assertIn("another bootstrap is running", busy.stderr)
        self.assertFalse(os.path.exists(self.marker))
        with open(lock, "w") as handle:
            handle.write("999999999\n")
        done = self.run_script()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(os.path.exists(self.marker))
        self.assertFalse(os.path.exists(lock))

    def test_an_existing_command_line_is_kept_and_a_present_pet_means_nothing_to_do(self):
        os.makedirs(os.path.dirname(self.cli))
        with open(self.cli, "w") as handle:
            handle.write("#!/bin/sh\necho mine\n")
        done = self.run_script()
        self.assertEqual(done.returncode, 0, done.stderr)
        with open(self.cli) as handle:
            self.assertEqual(handle.read(), "#!/bin/sh\necho mine\n")
        self.assertIn("left as it is", done.stderr)
        with open(self.marker) as handle:
            self.assertTrue(handle.read().startswith("cli kept, guga installed "))
        os.remove(self.marker)
        again = self.run_script()
        self.assertEqual(again.returncode, 0)
        self.assertIn("pets are already there", again.stderr)
        self.assertFalse(os.path.exists(self.marker))

    def test_a_failed_download_leaves_no_marker_so_the_next_start_retries(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        done = self.run_script()
        self.assertEqual(done.returncode, 1)
        self.assertIn("was not installed", done.stderr)
        self.assertFalse(os.path.exists(self.marker))
        self.assertTrue(os.path.exists(self.cli))
