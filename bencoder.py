'''
This module provides bencode and bdecode functions.

The functions are modified from <https://github.com/utdemir/bencoder>.
The original author specified no license, so it is assumed to be public domain.
'''

__all__ = ['bencode', 'bdecode', 'BdecodeError']

import string
import re

from functools import partial




class BdecodeError(ValueError):
    pass




def bencode(obj, enc: str = 'UTF-8') -> bytes:
    ''''''

    if isinstance(obj, bytes):
        ret = str(len(obj)).encode(enc) + b":" + obj
    elif isinstance(obj, str):
        ret = bencode(obj.encode(enc))
    elif isinstance(obj, int):
        ret = b"i" + str(obj).encode(enc) + b"e"
    elif isinstance(obj, (list, tuple)):
        ret = b"l" + b"".join(map(partial(bencode, enc=enc), obj)) + b"e"
    elif isinstance(obj, dict):
        ret = b'd'
        for key, val in sorted(obj.items()):
            if isinstance(key, (bytes, str)):
                ret += bencode(key, enc) + bencode(val, enc)
            else:
                raise TypeError(f"Expect str or bytes, not {key}:{type(key)}.")
        ret += b'e'
    else:
        raise TypeError(f"Expect int, bytes, list or dict, not {obj}:{type(obj)}.")

    return ret




def bdecode(s: bytes, encoding='utf-8') -> dict|list|str|int:
    '''Bdecode bytes. Modified from <https://github.com/utdemir/bencoder>.'''

    def decode_first(s):
        if s.startswith(b"i"):
            match = re.match(b"i(-?\\d+)e", s)
            return int(match.group(1)), s[match.span()[1]:]
        elif s.startswith(b"l") or s.startswith(b"d"):
            l = []
            rest = s[1:]
            while not rest.startswith(b"e"):
                elem, rest = decode_first(rest)
                l.append(elem)
            rest = rest[1:]
            if s.startswith(b"l"):
                return l, rest
            else:
                return {i: j for i, j in zip(l[::2], l[1::2])}, rest
        elif any(s.startswith(i.encode(encoding)) for i in string.digits):
            m = re.match(b"(\\d+):", s)
            length = int(m.group(1))
            rest_i = m.span()[1]
            start = rest_i
            end = rest_i + length
            return s[start:end], s[end:]
        else:
            raise BdecodeError("Malformed input.")

    s = s.encode(encoding) if isinstance(s, str) else s
    ret, rest = decode_first(s)
    if rest:
        raise BdecodeError("Malformed input.")

    return ret