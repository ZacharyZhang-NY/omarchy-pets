"""`install`: fetch, verify, and write exactly two files under <dir>/<id>/, through a directory descriptor."""

import os

from . import api
from .fs import FsError, open_child_dir, open_root, read_regular, replace_files
from .package import MAX_SHEET_BYTES, PackageError, check_version_marker, parse_manifest, read_package_zip, read_sheet, sha256_hex, valid_id


class InstallError(Exception):
    pass


def default_dir():
    return os.path.join(os.path.expanduser("~"), ".omarchy-pets", "pets")


def codex_dir():
    return os.path.join(os.path.expanduser("~"), ".codex", "pets")


def describe(pet_id):
    if not valid_id(pet_id):
        raise InstallError(f'"{pet_id}" is not a pet id: lowercase letters, digits and single hyphens')
    return api.pick(api.api_json("GET", f"/api/pets/{pet_id}/share-data"), "pet")


def fetch_package(pet_id, pet):
    """The zip behind share-data, checked as PRD F6 says: two files, the id, the sheet, the hash."""
    manifest_bytes, sheet = read_package_zip(api.download(api.pick(pet, "downloadUrl", kind=str)))
    manifest = parse_manifest(manifest_bytes)
    if manifest["id"] != pet_id:
        raise PackageError(f'the package says id "{manifest["id"]}", not "{pet_id}"')
    info = read_sheet(sheet)
    check_version_marker(manifest, info)
    if sha256_hex(sheet) != api.pick(pet, "validationReport", "sha256", kind=str):
        raise PackageError("the downloaded sheet does not match the published hash")
    return manifest_bytes, sheet, info


def _decide(existing_sha, published, target, pet_id, version, force):
    """The F6 rule for a folder that already holds a sheet: same hash means done, another needs --force."""
    if existing_sha == published:
        return {"status": "already installed", "id": pet_id, "path": target, "version": version}
    if existing_sha is not None and not force:
        raise InstallError(f"{target} holds a different sheet; pass --force to replace it")
    return None


def install(pet_id, directory, force=False):
    """Installs one pet. Every write goes through a descriptor of <dir>/<id>/, so a path swapped underneath is never followed."""
    try:
        root = open_root(directory)
    except FsError as error:
        raise InstallError(str(error)) from None
    pet_dir = None
    try:
        pet = describe(pet_id)
        published = api.pick(pet, "validationReport", "sha256", kind=str)
        version = api.pick(pet, "validationReport", "spriteVersionNumber", kind=int)
        target = os.path.join(directory, pet_id)
        pet_dir = open_child_dir(root, pet_id)
        existing = read_regular(pet_dir, "spritesheet.webp", MAX_SHEET_BYTES) if pet_dir is not None else None
        existing_sha = sha256_hex(existing) if existing is not None else None
        done = _decide(existing_sha, published, target, pet_id, version, force)
        if done:
            return done
        manifest_bytes, sheet, info = fetch_package(pet_id, pet)
        if pet_dir is None:
            try:
                os.mkdir(pet_id, 0o755, dir_fd=root)
            except FileExistsError:
                pass
            pet_dir = open_child_dir(root, pet_id)
            if pet_dir is None:
                raise InstallError(f"{target} vanished while the package was downloaded")
        # Something else may have written the folder during the download; the same rule applies to what is there now.
        appeared = read_regular(pet_dir, "spritesheet.webp", MAX_SHEET_BYTES)
        existing_sha = sha256_hex(appeared) if appeared is not None else None
        done = _decide(existing_sha, published, target, pet_id, version, force)
        if done:
            return done
        replace_files(pet_dir, {"pet.json": manifest_bytes, "spritesheet.webp": sheet})
        return {"status": "replaced" if existing_sha else "installed", "id": pet_id, "path": target, "version": info["version"]}
    except FsError as error:
        raise InstallError(str(error)) from None
    finally:
        if pet_dir is not None:
            os.close(pet_dir)
        os.close(root)
