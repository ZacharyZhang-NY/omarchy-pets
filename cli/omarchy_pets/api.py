"""HTTP, the credentials file and the multipart body. Everything talks to one origin."""

import http.client
import json
import os
import socket
import urllib.error
import urllib.request
import uuid

from . import VERSION

DEFAULT_BASE = "https://omarchy-pets.com"
MAX_DOWNLOAD = 8 * 1024 * 1024


class ApiError(Exception):
    def __init__(self, status, message, data=None):
        super().__init__(message)
        self.status = status
        self.data = data or {}


class NetworkError(Exception):
    pass


class ServerError(Exception):
    """The server answered, but not with what the API promises."""


class CredentialsError(Exception):
    """The local credentials file is unreadable or not ours; the user fixes it or signs in again."""


def _decode(status, raw):
    try:
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except ValueError:
        data = None
    if isinstance(data, dict):
        return data
    if status >= 400:
        return {}
    raise ServerError(f"the server answered {status} with something that is not a JSON object")


def pick(data, *keys, kind=None):
    """A field the API promises, nested keys walked in order and typed; a miss is the server's fault, not the user's."""
    for key in keys:
        if not isinstance(data, dict) or key not in data:
            raise ServerError(f'the server\'s answer lacks "{key}"')
        data = data[key]
    if kind is not None and (not isinstance(data, kind) or isinstance(data, bool) and kind is not bool):
        raise ServerError(f'the server\'s answer has a "{keys[-1]}" of the wrong type')
    return data


def api_base():
    return os.environ.get("OMARCHY_PETS_API_BASE", DEFAULT_BASE).rstrip("/")


def config_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "omarchy-pets")


def credentials_path():
    return os.path.join(config_dir(), "credentials.json")


def read_credentials():
    try:
        with open(credentials_path(), encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as error:
        raise CredentialsError(f"cannot read {credentials_path()}: {error}") from None
    if not isinstance(data, dict) or not isinstance(data.get("token"), str) or not isinstance(data.get("api_base"), str):
        raise CredentialsError(f"{credentials_path()} holds no token; run omarchy-pets login")
    return data


def bound_credentials():
    """The credentials for the current API base only; a token never travels to another origin."""
    credentials = read_credentials()
    if credentials and credentials["api_base"].rstrip("/") != api_base():
        raise CredentialsError(
            f"signed in to {credentials['api_base']}, not {api_base()}; set OMARCHY_PETS_API_BASE={credentials['api_base']} or sign out there first"
        )
    return credentials


def write_credentials(data):
    """Mode 0600 inside a 0700 directory, written through a temporary file and a rename."""
    directory = config_dir()
    os.makedirs(directory, mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)
    path = credentials_path()
    tmp = f"{path}.{os.getpid()}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    os.chmod(path, 0o600)


def delete_credentials():
    try:
        os.unlink(credentials_path())
        return True
    except FileNotFoundError:
        return False


def request(method, path, body=None, headers=None, token=None, timeout=60):
    """One HTTP exchange: (status, bytes, headers). Network failures raise NetworkError."""
    url = path if path.startswith("http") else api_base() + path
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("User-Agent", f"omarchy-pets/{VERSION}")
    for name, value in (headers or {}).items():
        req.add_header(name, value)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        try:
            return error.code, error.read(), dict(error.headers)
        except (http.client.HTTPException, OSError) as failure:
            raise NetworkError(f"{url} answered {error.code} but the body was cut short: {failure}") from None
    except (urllib.error.URLError, http.client.HTTPException, socket.timeout, OSError) as error:
        raise NetworkError(f"cannot reach {url}: {getattr(error, 'reason', error)}") from None


def api_json(method, path, payload=None, token=None):
    """A JSON exchange; 4xx and 5xx become ApiError with the server's message."""
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    status, raw, _ = request(method, path, body=body, headers=headers, token=token)
    data = _decode(status, raw)
    if status >= 400:
        raise ApiError(status, data.get("error") or f"the server answered {status}", data)
    return data


def download(path, token=None):
    status, raw, _ = request("GET", path, token=token, headers={"Accept": "*/*"})
    if status >= 400:
        raise ApiError(status, f"download failed with {status}")
    if len(raw) > MAX_DOWNLOAD:
        raise ApiError(status, "the download is larger than 8 MiB")
    return raw


def multipart(fields, files):
    """A multipart/form-data body: fields are strings, files are (filename, bytes, content type)."""
    boundary = f"----omarchy-pets-{uuid.uuid4().hex}"
    out = bytearray()
    for name, value in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode("utf-8")
    for name, (filename, data, content_type) in files.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\nContent-Type: {content_type}\r\n\r\n".encode("utf-8")
        out += data
        out += b"\r\n"
    out += f"--{boundary}--\r\n".encode("utf-8")
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def api_multipart(method, path, fields, files, token):
    body, content_type = multipart(fields, files)
    status, raw, _ = request(method, path, body=body, headers={"Content-Type": content_type, "Accept": "application/json"}, token=token, timeout=300)
    data = _decode(status, raw)
    if status >= 400:
        raise ApiError(status, data.get("error") or f"the server answered {status}", data)
    return data
