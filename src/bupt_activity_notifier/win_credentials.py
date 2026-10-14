"""Windows Credential Manager storage for opt-in reauthentication.

Secrets are scoped to the logged-in Windows account. No secrets go to .env,
logs, Git, notifications, or command-line arguments. Never print exceptions
from Win32 / browser calls because they may include sensitive context.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os

ACCOUNT_TARGET = "BUPT-Activity-Notifier:Login"
TOKEN_TARGET = "BUPT-Activity-Notifier:RenewedToken"
_GENERIC = 1
_PERSIST_LOCAL_MACHINE = 2


class SecretStoreError(RuntimeError):
    """Sanitized credential-storage failure."""


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _win_api():
    if os.name != "nt":
        raise SecretStoreError("Automatic sign-in credentials require Windows.")
    api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    api.CredReadW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_Credential)),
    ]
    api.CredReadW.restype = wintypes.BOOL
    api.CredWriteW.argtypes = [ctypes.POINTER(_Credential), wintypes.DWORD]
    api.CredWriteW.restype = wintypes.BOOL
    api.CredFree.argtypes = [ctypes.c_void_p]
    api.CredFree.restype = None
    api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    api.CredDeleteW.restype = wintypes.BOOL
    return api


def _read(target: str) -> tuple[str, str] | None:
    api = _win_api()
    ptr = ctypes.POINTER(_Credential)()
    if not api.CredReadW(target, _GENERIC, 0, ctypes.byref(ptr)):
        if ctypes.get_last_error() == 1168:  # ERROR_NOT_FOUND
            return None
        raise SecretStoreError("Could not read Windows Credential Manager.")
    try:
        cred = ptr.contents
        blob = (
            ctypes.string_at(cred.CredentialBlob, cred.CredentialBlobSize)
            if cred.CredentialBlobSize else b""
        )
        return cred.UserName or "", blob.decode("utf-16-le")
    except (ValueError, UnicodeError):
        raise SecretStoreError("Windows credential has an invalid format.") from None
    finally:
        api.CredFree(ptr)


def _write(target: str, username: str, secret: str) -> None:
    if not username or not secret or len(username) > 513:
        raise SecretStoreError("Missing or invalid credential information.")
    blob = secret.encode("utf-16-le")
    if len(blob) > 2560:
        raise SecretStoreError("Secret exceeds the Windows credential size limit.")
    api = _win_api()
    memory = ctypes.create_string_buffer(blob)
    credential = _Credential()
    credential.Type = _GENERIC
    credential.TargetName = target
    credential.UserName = username
    credential.CredentialBlobSize = len(blob)
    credential.CredentialBlob = ctypes.cast(memory, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = _PERSIST_LOCAL_MACHINE
    if not api.CredWriteW(ctypes.byref(credential), 0):
        raise SecretStoreError("Could not save credential in Windows Credential Manager.")


def read_login() -> tuple[str, str] | None:
    return _read(ACCOUNT_TARGET)


def save_login(username: str, password: str) -> None:
    _write(ACCOUNT_TARGET, username, password)


def read_renewed_token() -> str | None:
    record = _read(TOKEN_TARGET)
    return record[1] if record else None


def save_renewed_token(token: str) -> None:
    _write(TOKEN_TARGET, "SecondClass-Student-Token", token)


def _delete(target: str) -> None:
    api = _win_api()
    if not api.CredDeleteW(target, _GENERIC, 0):
        if ctypes.get_last_error() != 1168:
            raise SecretStoreError("Could not delete stored credentials.")


def delete_login() -> None:
    _delete(ACCOUNT_TARGET)


def delete_renewed_token() -> None:
    _delete(TOKEN_TARGET)
