import hashlib
import pathlib
from typing import Iterable




def hashFiles(files: Iterable[pathlib.Path|str], nproc: int = 1, piece_size: int = 4 * 1024 * 1024) -> list[bytes]:
    files = [pathlib.Path(file) for file in files]
    for file in files:
        if not file.is_file():
            raise FileNotFoundError(file)




def toSHA1(bchars: bytes) -> bytes:
    '''Return the sha1 hash for the given bytes.'''
    if isinstance(bchars, bytes):
        hasher = hashlib.sha1()
        hasher.update(bchars)
        return hasher.digest()
    else:
        raise TypeError(f"Expect bytes, not {type(bchars)}.")