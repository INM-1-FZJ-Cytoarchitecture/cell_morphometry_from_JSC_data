"""File hashing."""
import hashlib
from pathlib import Path


def sha256_file(path, chunk=8 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_info(path) -> dict:
    p = Path(path)
    st = p.stat()
    return {"path": str(p), "size_bytes": st.st_size, "mtime": st.st_mtime}
