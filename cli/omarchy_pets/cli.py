"""The verbs. Exit 0 on success, 1 on a user error, 2 on a network or server error; --json prints one object."""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time

from . import VERSION, api
from .api import ApiError, CredentialsError, NetworkError, ServerError, pick
from .fs import FsError, open_child_dir, open_root, read_regular, replace_files
from .install import InstallError, codex_dir, default_dir, install
from .package import (
    MAX_MANIFEST_BYTES,
    MAX_SHEET_BYTES,
    PET_KINDS,
    PackageError,
    canonical_manifest,
    check_version_marker,
    parse_manifest,
    read_sheet,
    sha256_hex,
    valid_id,
)


class UserError(Exception):
    pass


class UsageError(Exception):
    pass


def pet_url(pet_id):
    return f"{api.api_base()}/pets/{pet_id}"


def require_token():
    credentials = api.bound_credentials()
    if not credentials:
        raise UserError("not signed in; run omarchy-pets login")
    return credentials["token"]


def pet_files(directory, pet_id):
    """pet.json and spritesheet.webp of <dir>/<id>/, read without following a link below the root."""
    try:
        root = open_root(directory)
    except FsError as error:
        raise UserError(str(error)) from None
    try:
        pet_dir = open_child_dir(root, pet_id)
        if pet_dir is None:
            raise UserError(f"{os.path.join(directory, pet_id)} does not exist")
        try:
            manifest = read_regular(pet_dir, "pet.json", MAX_MANIFEST_BYTES)
            sheet = read_regular(pet_dir, "spritesheet.webp", MAX_SHEET_BYTES)
        finally:
            os.close(pet_dir)
    except FsError as error:
        raise UserError(f"{os.path.join(directory, pet_id)}: {error}") from None
    finally:
        os.close(root)
    for name, data in (("pet.json", manifest), ("spritesheet.webp", sheet)):
        if data is None:
            raise UserError(f"{os.path.join(directory, pet_id, name)} is missing")
    return manifest, sheet


def open_browser(url):
    """`omarchy launch browser`, then `xdg-open`; True when one of them accepted the address."""
    for command in (["omarchy", "launch", "browser", url], ["xdg-open", url]):
        try:
            done = subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if done.returncode == 0:
            return True
    return False


def cmd_login(args):
    host = re.sub(r"[^A-Za-z0-9._-]", "-", socket.gethostname())[:64] or "host"
    grant = api.api_json("POST", "/api/cli/device", {"host": host})
    url = pick(grant, "verification_uri_complete", kind=str)
    device_code = pick(grant, "device_code", kind=str)
    print(f"Your code is {pick(grant, 'user_code', kind=str)}\nApprove it at {url}", file=sys.stderr)
    if not args.no_browser and not open_browser(url):
        print("Could not open a browser; open the address yourself.", file=sys.stderr)
    deadline = time.monotonic() + pick(grant, "expires_in", kind=(int, float))
    interval = pick(grant, "interval", kind=(int, float))
    while time.monotonic() < deadline:
        time.sleep(interval)
        try:
            data = api.api_json("POST", "/api/cli/device/token", {"device_code": device_code})
        except ApiError as error:
            reason = error.data.get("error")
            if reason == "authorization_pending":
                continue
            if reason == "access_denied":
                raise UserError("the sign-in was denied in the browser") from None
            if reason == "expired_token":
                raise UserError("the code expired; run login again") from None
            raise
        token = pick(data, "token", kind=str)
        handle = pick(api.api_json("GET", "/api/me", token=token), "user", "handle", kind=str)
        api.write_credentials({"api_base": api.api_base(), "token": token, "handle": handle})
        return {"ok": True, "handle": handle, "message": f"Signed in as @{handle}"}
    raise UserError("the code expired; run login again")


def cmd_logout(args):
    credentials = api.bound_credentials()
    if credentials:
        try:
            api.api_json("DELETE", "/api/cli/tokens/current", token=credentials["token"])
        except ApiError as error:
            if error.status != 401:
                raise
    removed = api.delete_credentials()
    return {"ok": True, "removed": removed, "message": "Signed out" if removed else "Not signed in"}


def cmd_whoami(args):
    me = pick(api.api_json("GET", "/api/me", token=require_token()), "user")
    handle, email = pick(me, "handle", kind=str), pick(me, "email", kind=str)
    return {"ok": True, "handle": handle, "email": email, "message": f"@{handle} <{email}>"}


def cmd_install(args):
    directory = args.dir or ready_dir()
    ids = [args.id] if args.id else []
    if args.collection:
        ids = [pick(pet, "id", kind=str) for pet in pick(api.api_json("GET", f"/api/collections/{args.collection}"), "pets", kind=list)]
        if not ids:
            raise UserError(f'the collection "{args.collection}" is empty')
    if not ids:
        raise UserError("give a pet id or --collection <slug>")
    results = [install(pet_id, directory, force=args.force) for pet_id in ids]
    lines = [f"{r['status']}: {r['path']}" for r in results]
    lines.append("Open the bar panel to pick it." if len(results) == 1 else "Open the bar panel to pick them.")
    return {"ok": True, "pets": results, "message": "\n".join(lines)}


def ask(prompt):
    """A question on stderr, so stdout stays the result (one JSON object with --json); end of input cancels."""
    print(prompt, end="", file=sys.stderr, flush=True)
    try:
        return input().strip().lower()
    except EOFError:
        raise UserError("cancelled") from None


def ask_kind():
    if not sys.stdin.isatty():
        raise UserError("pet.json has no kind; pass --kind object|animal|person|creature")
    answer = ask(f"Kind ({', '.join(PET_KINDS)}): ")
    if answer not in PET_KINDS:
        raise UserError("kind must be one of object, animal, person, creature")
    return answer


def confirm_rights():
    if not sys.stdin.isatty():
        raise UserError("confirm that you have the right to publish this artwork with --yes")
    return ask("Do you have the right to publish this artwork? [y/N] ") in ("y", "yes")


def cmd_upload(args):
    token = require_token()
    directory = args.dir or ready_dir()
    manifest_bytes, sheet = pet_files(directory, args.id)
    manifest = parse_manifest(manifest_bytes)
    if manifest["id"] != args.id:
        raise UserError(f'{os.path.join(directory, args.id)}/pet.json says id "{manifest["id"]}", not "{args.id}"')
    info = read_sheet(sheet)
    check_version_marker(manifest, info)
    published_id = args.as_id or manifest["id"]
    if not valid_id(published_id):
        raise UserError(f'"{published_id}" is not a usable id: lowercase letters, digits and single hyphens, not reserved')
    digest = sha256_hex(sheet)
    found = api.api_json("GET", f"/api/pets/check?id={published_id}&sha256={digest}", token=token)
    status = pick(found, "status", kind=str)
    done = duplicate_verdict(status, found, published_id, args.update)
    if done:
        return done
    kind = args.kind or manifest.get("kind") or ask_kind()
    if not args.yes and not confirm_rights():
        raise UserError("upload cancelled; the licence was not confirmed")
    fields = {"kind": kind, "rights": "yes"}
    if args.tags is not None:
        fields["tags"] = args.tags
    body = canonical_manifest({**manifest, "id": published_id}).encode("utf-8")
    path = f"/api/pets/{published_id}/versions" if status == "replace" else "/api/pets"
    files = {"manifest": ("pet.json", body, "application/json"), "spritesheet": ("spritesheet.webp", sheet, "image/webp")}
    try:
        pet_id = pick(api.api_multipart("POST", path, fields, files, token), "pet", "id", kind=str)
    except ApiError as error:
        if error.status != 409 or not isinstance(error.data.get("code"), str):
            raise
        # Someone else won between the probe and the post; the same rules answer.
        return duplicate_verdict(error.data["code"], error.data, published_id, args.update)
    verb = "Replaced" if status == "replace" else "Published"
    return {
        "ok": True,
        "status": "replaced" if status == "replace" else "published",
        "id": pet_id,
        "url": pet_url(pet_id),
        "install": f"omarchy-pets install {pet_id}",
        "message": f"{verb} {pet_url(pet_id)}\nInstall with: omarchy-pets install {pet_id}",
    }


def duplicate_verdict(status, found, published_id, update):
    """The F4 duplicate table as the CLI states it; a result to print, None to go on, or a UserError."""
    if status == "published":
        return {"ok": True, "status": "published", "id": published_id, "url": pet_url(published_id), "message": f"already published as {published_id}: {pet_url(published_id)}"}
    if status == "replace" and not update:
        raise UserError(f'"{published_id}" is yours with a different sheet; pass --update to replace it')
    if status == "duplicate_id":
        raise UserError(f'the id "{published_id}" belongs to @{found.get("ownerHandle")}; publish under another id with --as <new-id>')
    if status == "duplicate_sheet":
        raise UserError(f'this sheet is already published as "{found.get("petId")}" by @{found.get("ownerHandle")}; one sheet, one pet')
    if status not in ("free", "replace"):
        raise ServerError(f'the server answered with an unknown duplicate status "{status}"')
    return None


def ready_dir():
    """~/.omarchy-pets/pets, made on first use. Until the marker beside it records an answer, Codex pets missing here are offered as copies; the originals stay."""
    directory = default_dir()
    source = codex_dir()
    os.makedirs(directory, mode=0o755, exist_ok=True)
    marker = os.path.join(os.path.dirname(directory), "codex-copy")
    if os.path.exists(marker) or not os.path.isdir(source):
        return directory
    present = {os.path.basename(pet["path"]) for pet in local_pets(directory)[0]}
    missing = [pet for pet in local_pets(source)[0] if os.path.basename(pet["path"]) not in present]
    if not missing:
        return directory
    if not sys.stdin.isatty():
        print(f"{len(missing)} Codex pet(s) in {source} were not copied; run omarchy-pets list from a terminal to be asked.", file=sys.stderr)
        return directory
    answer = ask(f"Copy {len(missing)} pet(s) from {source} into {directory}? The originals stay. [Y/n] ")
    if answer not in ("", "y", "yes"):
        write_marker(marker, "declined")
        return directory
    copied = 0
    root = None
    try:
        root = open_root(directory)
        for pet in missing:
            pet_id = os.path.basename(pet["path"])
            manifest, sheet = pet_files(source, pet_id)
            try:
                os.mkdir(pet_id, 0o755, dir_fd=root)
            except FileExistsError:
                pass
            pet_dir = open_child_dir(root, pet_id)
            if pet_dir is None:
                raise UserError(f"{os.path.join(directory, pet_id)} is a symlink or a file; refusing to write there")
            try:
                # A pet that arrived while the question was open is not touched; `install --force` is the way to replace one.
                if read_regular(pet_dir, "spritesheet.webp", MAX_SHEET_BYTES) is not None:
                    print(f"skipped {pet_id}: already there", file=sys.stderr)
                    continue
                replace_files(pet_dir, {"pet.json": manifest, "spritesheet.webp": sheet})
                copied += 1
            finally:
                os.close(pet_dir)
    except FsError as error:
        raise UserError(str(error)) from None
    finally:
        if root is not None:
            os.close(root)
    write_marker(marker, f"copied {copied}")
    print(f"Copied {copied} pet(s) from {source} into {directory}.", file=sys.stderr)
    return directory


def write_marker(path, answer):
    """One line, so the question is not asked again; delete the file to be asked once more. Created exclusively, so a link planted meanwhile is never followed and an answer already there wins."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644)
    except FileExistsError:
        return
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"{answer} {time.strftime('%Y-%m-%d')}\n")


def local_pets(directory):
    """Every <dir>/*/ with a valid manifest and sheet header; the rest is skipped with a reason."""
    pets, skipped = [], []
    try:
        root = open_root(directory)
    except FsError as error:
        raise UserError(str(error)) from None
    try:
        for name in sorted(os.listdir(root)):
            try:
                pet_dir = open_child_dir(root, name)
            except FsError as error:
                skipped.append({"id": name, "reason": str(error)})
                continue
            if pet_dir is None:
                continue
            try:
                manifest_bytes = read_regular(pet_dir, "pet.json", MAX_MANIFEST_BYTES)
                sheet = read_regular(pet_dir, "spritesheet.webp", MAX_SHEET_BYTES)
                if manifest_bytes is None or sheet is None:
                    continue
                manifest = parse_manifest(manifest_bytes)
                info = read_sheet(sheet)
            except (FsError, PackageError) as error:
                skipped.append({"id": name, "reason": str(error)})
                continue
            finally:
                os.close(pet_dir)
            pets.append({"id": manifest["id"], "displayName": manifest["displayName"], "version": info["version"], "sha256": sha256_hex(sheet), "path": os.path.join(directory, name)})
    finally:
        os.close(root)
    return pets, skipped


def remote_pets(token):
    """Every page of the account's published pets."""
    handle = pick(api.api_json("GET", "/api/me", token=token), "user", "handle", kind=str)
    pets, page = [], 1
    while True:
        data = api.api_json("GET", f"/api/pets?owner={handle}&pageSize=60&page={page}", token=token)
        for pet in pick(data, "pets", kind=list):
            pet_id = pick(pet, "id", kind=str)
            pets.append({"id": pet_id, "displayName": pick(pet, "displayName", kind=str), "version": pick(pet, "validationReport", "spriteVersionNumber", kind=int), "url": pet_url(pet_id)})
        if page >= pick(data, "totalPages", kind=int):
            return pets
        page += 1


def cmd_list(args):
    if args.remote:
        pets = remote_pets(require_token())
        lines = [f"{p['id']}  v{p['version']}  {p['displayName']}" for p in pets] or ["No pets published."]
        return {"ok": True, "pets": pets, "message": "\n".join(lines)}
    pets, skipped = local_pets(args.dir or ready_dir())
    credentials = api.bound_credentials()
    for pet in pets:
        if credentials:
            found = api.api_json("GET", f"/api/pets/check?id={pet['id']}&sha256={pet['sha256']}", token=credentials["token"])
            pet["publishedAs"] = found.get("sheetPetId")
    lines = [f"{p['id']}  v{p['version']}  {p['displayName']}" + (f"  published as {p['publishedAs']}" if p.get("publishedAs") else "") for p in pets] or ["No pets installed."]
    lines += [f"skipped {s['id']}: {s['reason']}" for s in skipped]
    return {"ok": True, "pets": pets, "skipped": skipped, "message": "\n".join(lines)}


class Parser(argparse.ArgumentParser):
    """argparse that reports usage mistakes through the CLI's own error contract."""

    def error(self, message):
        raise UsageError(message)


def build_parser():
    parser = Parser(prog="omarchy-pets", description="Pets for the Omarchy bar, from omarchy-pets.com.")
    parser.add_argument("--version", action="version", version=f"omarchy-pets {VERSION}")
    parser.add_argument("--json", action="store_true", help="print one JSON object instead of prose")
    verbs = parser.add_subparsers(dest="verb", required=True)
    login = verbs.add_parser("login", help="sign in through the browser")
    login.add_argument("--no-browser", action="store_true", help="print the address instead of opening it")
    login.set_defaults(run=cmd_login)
    verbs.add_parser("logout", help="revoke this machine's token").set_defaults(run=cmd_logout)
    verbs.add_parser("whoami", help="show the signed-in account").set_defaults(run=cmd_whoami)
    inst = verbs.add_parser("install", help="install a pet into the pets directory")
    inst.add_argument("id", nargs="?")
    inst.add_argument("--collection", metavar="SLUG", help="install every pet of a collection")
    inst.add_argument("--force", action="store_true", help="replace a different local sheet")
    inst.add_argument("--dir", help="pets directory (default: ~/.omarchy-pets/pets)")
    inst.set_defaults(run=cmd_install)
    up = verbs.add_parser("upload", help="publish a local pet")
    up.add_argument("id")
    up.add_argument("--as", dest="as_id", metavar="NEW-ID", help="publish under another id; the folder is untouched")
    up.add_argument("--kind", choices=PET_KINDS)
    up.add_argument("--tags", help="comma-separated tags")
    up.add_argument("--update", action="store_true", help="replace the sheet of your existing pet")
    up.add_argument("--yes", action="store_true", help="confirm the licence without asking")
    up.add_argument("--dir", help="pets directory")
    up.set_defaults(run=cmd_upload)
    lst = verbs.add_parser("list", help="list local pets, or your published ones")
    lst.add_argument("--remote", action="store_true")
    lst.add_argument("--dir", help="pets directory")
    lst.set_defaults(run=cmd_list)
    return parser


def main(argv):
    as_json = "--json" in argv
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except UsageError as error:
        return fail(as_json, f"{error}\n{parser.format_usage().strip()}", 1)
    except SystemExit as exit_:
        return int(exit_.code or 0)
    try:
        result = args.run(args)
    except (UserError, PackageError, InstallError, CredentialsError, RuntimeError) as error:
        return fail(as_json, str(error), 1)
    except ApiError as error:
        return fail(as_json, str(error), 2 if error.status == 0 or error.status >= 500 else 1)
    except (NetworkError, ServerError) as error:
        return fail(as_json, str(error), 2)
    except OSError as error:
        return fail(as_json, f"{error.strerror or error}: {error.filename}" if error.filename else str(error), 1)
    except KeyboardInterrupt:
        return fail(as_json, "interrupted", 130)
    if as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result["message"])
    return 0


def fail(as_json, message, code):
    if as_json:
        print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    else:
        print(f"omarchy-pets: {message}", file=sys.stderr)
    return code
