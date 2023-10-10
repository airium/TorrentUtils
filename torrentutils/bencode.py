'''This module provides bencode and bdecode functions.'''

__all__ = ['bencode', 'bdecode', 'bdecode4torrent']

import re
import codecs
from typing import Optional
from functools import partial


_INT_REGEX = re.compile(rb'i(-?\d+)e(.*)')
_BYTES_REGEX = re.compile(rb'(\d+):(.*)')
_LIST_REGEX = re.compile(rb'l(.*)e')
_DICT_REGEX = re.compile(rb'd(.*)e')
_ENCODING = 'utf-8'




def bencode(obj: int|str|bytes|list|dict, encoding: str = 'utf-8') -> bytes:

    if isinstance(obj, bytes):
        return str(len(obj)).encode(encoding) + b':' + obj
    elif isinstance(obj, str):
        return bencode(obj.encode(encoding))
    elif isinstance(obj, int):
        return b'i' + str(obj).encode(encoding) + b'e'
    elif isinstance(obj, (list, tuple)):
        return b'l' + b''.join(map(partial(bencode, encoding=encoding), obj)) + b'e'
    elif isinstance(obj, dict):
        ret = b'd'
        for key, val in obj.items():
            if isinstance(key, str|bytes):
                ret += bencode(key, encoding) + bencode(val, encoding)
            else:
                raise TypeError(f'Bencode expects dict key as str|bytes, not {type(key)}.')
        ret += b'e'
        return ret
    else:
        raise TypeError(f'Bencode expects int|bytes|str|list|dict, not {type(obj)}.')




def _bdecode(bchars: bytes) -> tuple[dict|list|bytes|int, bytes]:
    if m := _INT_REGEX.match(bchars):
        return int(m.group(1)), m.group(2)
    elif m := _BYTES_REGEX.match(bchars):
        len = int(m.group(1))
        rest = m.group(2)
        return rest[:len], rest[len:]
    elif m := _LIST_REGEX.match(bchars):
        l: list = []
        payload = m.group(1)
        while payload:
            elem, payload = _bdecode(payload)
            l.append(elem)
        return l, b''
    elif m := _DICT_REGEX.match(bchars):
        d: dict = {}
        payload = m.group(1)
        while payload:
            key, payload = _bdecode(payload)
            val, payload = _bdecode(payload)
            d[key] = val
        return d, b''
    else:
        raise ValueError('Bdecode hits malformed content.')




def bdecode(bchars: bytes) -> dict|list|bytes|int:

    if not isinstance(bchars, bytes): raise TypeError(f'Bdecode expects bytes, not {type(bchars)}.')
    ret, rest = _bdecode(bchars)
    if rest: raise ValueError('Bdecode hits trailing content.')
    return ret




def _decode(obj: int|str|bytes|list|dict, encoding: str) -> str|int|list|dict:

    if isinstance(obj, int|str):
        return obj
    elif isinstance(obj, bytes):
        return obj.decode(encoding)
    elif isinstance(obj, list):
        return [_decode(elem, encoding) for elem in obj]
    elif isinstance(obj, dict):
        return {key.decode(encoding): _decode(val, encoding) for key, val in obj.items()}
    else:
        raise TypeError(f'Bdecode for torrent expects int|str|bytes|list|dict, not {type(obj)}.')




def bdecode4torrent(bchars: bytes, encoding: Optional[str] = None) -> dict[str, int|str|list|dict]:

    d = bdecode(bchars)
    if not isinstance(d, dict): raise TypeError(f'Expect bdecoded dict, not {type(d)}.')
    try:
        enc = d.get(b'encoding')
        assert isinstance(enc, bytes)
        enc = enc.decode(encoding or _ENCODING)
        codecs.lookup(enc)
    except Exception:
        enc = encoding or _ENCODING

    d = _decode(d, enc)
    if not isinstance(d, dict): raise TypeError(f'Expect decoded dict, not {type(d)}.')
    return d
