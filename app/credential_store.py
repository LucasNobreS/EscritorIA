"""DPAPI encryption on Windows, with transparent reads of legacy plain JSON."""

import base64
import json
import os


def _dpapi(data, encrypt):
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    fn = crypt.CryptProtectData if encrypt else crypt.CryptUnprotectData
    fn.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    fn.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise OSError(
            "Não foi possível acessar o cofre de credenciais deste usuário Windows."
        )
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def load(path):
    if not path.exists():
        return {}
    result = json.loads(path.read_text("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("Arquivo de credenciais inválido.")
    if result.get("format") == "atelie-dpapi-v1":
        if os.name != "nt":
            raise ValueError(
                "Estas chaves pertencem ao cofre Windows original. Cadastre suas chaves neste computador."
            )
        result = json.loads(
            _dpapi(base64.b64decode(result["data"], validate=True), False)
        )
    if not isinstance(result, dict):
        raise ValueError("Arquivo de credenciais inválido.")
    return result


def save(path, values):
    raw = json.dumps(values).encode()
    if os.name == "nt":
        raw = json.dumps(
            {
                "format": "atelie-dpapi-v1",
                "data": base64.b64encode(_dpapi(raw, True)).decode(),
            }
        ).encode()
    temp = path.with_name(".credenciais.tmp")
    temp.write_bytes(raw)
    temp.chmod(0o600)
    temp.replace(path)
