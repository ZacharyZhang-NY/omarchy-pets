#!/usr/bin/env python3
"""First load with no pets: put the bundled command line at ~/.local/bin/omarchy-pets if absent, install the default pet, then never again."""

import fcntl
import io
import os
import subprocess
import sys
import time
import zipfile

PLUGIN = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(PLUGIN, "cli")
SCAN = os.path.join(PLUGIN, "scan.py")
DEFAULT_PET = "guga"
TIMEOUT = 120


def say(text):
    print(f"bootstrap: {text}", file=sys.stderr, flush=True)


def has_pets(pets):
    """What the plugin would show: the scanner's own verdict, one "pet" line per usable folder."""
    if not os.path.isdir(pets):
        return False
    done = subprocess.run([sys.executable, "-B", SCAN, pets], capture_output=True, text=True, timeout=TIMEOUT)
    return any(line.startswith("pet\t") for line in done.stdout.splitlines())


def zipapp_bytes():
    """The same layout the site builds: omarchy_pets/*.py plus a root __main__.py, stored, behind a python3 shebang."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        source = os.path.join(CLI, "omarchy_pets")
        for name in sorted(os.listdir(source)):
            if name.endswith(".py"):
                with open(os.path.join(source, name), "rb") as handle:
                    archive.writestr(f"omarchy_pets/{name}", handle.read())
        archive.writestr("__main__.py", b"from omarchy_pets.__main__ import *\n")
    return b"#!/usr/bin/env python3\n" + buffer.getvalue()


def install_cli(target):
    """Writes the command only when nothing is there; a file the user put there is theirs."""
    if os.path.lexists(target):
        say(f"{target} exists, left as it is")
        return False
    os.makedirs(os.path.dirname(target), mode=0o755, exist_ok=True)
    tmp = f"{target}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o755)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(zipapp_bytes())
        os.link(tmp, target)
    except FileExistsError:
        say(f"{target} appeared meanwhile, left as it is")
        return False
    finally:
        os.unlink(tmp)
    say(f"wrote {target}")
    return True


def install_pet(pet_id):
    """The bundled package installs the pet; no terminal, so the Codex copy question is left for the user's first command.
    No bytecode is written: a file appearing under the plugin folder makes the shell reload the plugin."""
    env = {**os.environ, "PYTHONPATH": CLI, "PYTHONDONTWRITEBYTECODE": "1"}
    done = subprocess.run(
        [sys.executable, "-B", "-m", "omarchy_pets", "install", pet_id],
        env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=TIMEOUT,
    )
    for line in (done.stdout + done.stderr).splitlines():
        if line.strip():
            say(line.strip())
    return done.returncode == 0


def write_marker(path, text):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644)
    except FileExistsError:
        return
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"{text} {time.strftime('%Y-%m-%d')}\n")


def hold_lock(path):
    """The one bootstrap at a time: an OS lock on a file that is never unlinked, released by the kernel when the holder dies.
    A second bootstrap waits for the first, so its caller rescans after the pet is there."""
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644)
    waited = False
    deadline = time.monotonic() + TIMEOUT + 30
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd, waited
        except BlockingIOError:
            if not waited:
                say("another bootstrap is running; waiting for it")
                waited = True
            if time.monotonic() > deadline:
                os.close(fd)
                raise TimeoutError("the other bootstrap did not finish in time")
            time.sleep(1)


def main():
    home = os.path.expanduser("~")
    state = os.path.join(home, ".omarchy-pets")
    marker = os.path.join(state, "bootstrap.done")
    pets = os.path.join(state, "pets")
    if os.path.lexists(marker):
        return 0
    if has_pets(pets):
        say("pets are already there, nothing to do")
        return 0
    os.makedirs(state, mode=0o755, exist_ok=True)
    try:
        fd, waited = hold_lock(os.path.join(state, "bootstrap.lock"))
    except TimeoutError as error:
        say(str(error))
        return 1
    try:
        # Another bootstrap may have finished between the checks above and the lock.
        if os.path.lexists(marker) or has_pets(pets):
            say("the other bootstrap finished" if waited else "done meanwhile")
            return 0
        wrote = install_cli(os.path.join(home, ".local", "bin", "omarchy-pets"))
        installed = install_pet(DEFAULT_PET)
        if not installed:
            say(f"{DEFAULT_PET} was not installed; the next start tries again")
            return 1
        if not has_pets(pets):
            say(f"{DEFAULT_PET} is in place but the scanner rejects it; delete {os.path.join(pets, DEFAULT_PET)} to have it fetched again")
            return 1
        write_marker(marker, f"cli {'written' if wrote else 'kept'}, {DEFAULT_PET} installed")
        return 0
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
