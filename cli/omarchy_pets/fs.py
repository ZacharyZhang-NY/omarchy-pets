"""Local files, the way the bar plugin reads them: no symlink followed below the root, regular files only, sizes bounded."""

import os
import stat


class FsError(Exception):
    pass


READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
ROOT_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC


def open_root(path):
    """The pets directory itself; it may be a symlink, because the user chose it."""
    try:
        return os.open(path, ROOT_FLAGS)
    except FileNotFoundError:
        raise FsError(f"{path} does not exist; create it first") from None
    except NotADirectoryError:
        raise FsError(f"{path} is not a directory") from None


def open_child_dir(root_fd, name):
    """A pet directory under the root, or None when absent; a symlink or a file in its place is refused."""
    try:
        return os.open(name, DIR_FLAGS, dir_fd=root_fd)
    except FileNotFoundError:
        return None
    except NotADirectoryError:
        raise FsError(f"{name} is a symlink or not a directory; refusing to touch it") from None


def read_regular(dir_fd, name, cap):
    """The bytes of a regular file under dir_fd, or None when absent; symlinks, pipes and oversized files are refused."""
    try:
        fd = os.open(name, READ_FLAGS, dir_fd=dir_fd)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise FsError(f"{name} cannot be opened without following a link ({error.strerror})") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise FsError(f"{name} is not a regular file")
        if info.st_size > cap:
            raise FsError(f"{name} is larger than {_size(cap)}")
        chunks, remaining = [], cap + 1
        while remaining > 0:
            chunk = os.read(fd, min(1 << 20, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > cap:
            raise FsError(f"{name} is larger than {_size(cap)}")
        return data
    finally:
        os.close(fd)


def replace_files(dir_fd, files):
    """Writes every file to a temporary name first, then renames each into place; a failure leaves the old files."""
    temps = {}
    try:
        for name, data in files.items():
            tmp = f".{name}.{os.getpid()}.tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644, dir_fd=dir_fd)
            temps[name] = tmp
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
        for name, tmp in list(temps.items()):
            os.replace(tmp, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            del temps[name]
    finally:
        for tmp in temps.values():
            try:
                os.unlink(tmp, dir_fd=dir_fd)
            except FileNotFoundError:
                pass


def _size(cap):
    return f"{cap // (1024 * 1024)} MiB" if cap >= 1024 * 1024 else f"{cap // 1024} KiB"
