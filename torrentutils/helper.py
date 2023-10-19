__all__ = []  # disable import *

from collections.abc import Sequence, Iterable
from typing import overload, cast
from torrentutils.type import strs
from itertools import chain

from torrentutils.config import CHECK_URL_FORMAT as _CHECK
from torrentutils.config import RAISE_MALFORMED_URL as _RAISE
from torrentutils.config import URL_PATH_CASE_SENSITIVE as _PCASE
from torrentutils.config import SIMPLE_URL_REGEX, TRACKER_URL_REGEX


def normalizeURL(url: str, path_case_sensitive: bool = _PCASE) -> str:
    if m := SIMPLE_URL_REGEX.match(url):
        ret = m.group('scheme_host_port').lower()
        return ret + (m.group('leftover') if path_case_sensitive else m.group('leftover').lower())
    else:
        return url if path_case_sensitive else url.lower()


def compareURL(url1: str, url2: str, path_case_sensitive: bool = _PCASE) -> bool:
    url1 = normalizeURL(url1, path_case_sensitive)
    url2 = normalizeURL(url2, path_case_sensitive)
    return url1 == url2


def dedupURL(urls: list[str]) -> list[str]:
    #! this has a side effect of changing the capitalization of the urls
    return list(set(u.lower() for u in urls))


def chkURLs(urls: str|Sequence[str]) -> list[str]:
    '''Check the input tracker(s), return a list version of the input.'''
    # TODO: add url check
    urls = [urls] if isinstance(urls, str) else list(urls)
    if not all(isinstance(url, str) for url in urls): raise TypeError('Some supplied tracker is non-str.')
    if not all(urls): raise ValueError('Tracker url cannot be empty.')
    return urls


@overload
def checkURL(
    urls: str,
    *,
    raise_malformed: bool = _RAISE,
    path_case_sensitive: bool = _PCASE,
    ) -> str:
    ...


@overload
def checkURL(
    urls: list[str],
    *,
    raise_malformed: bool = _RAISE,
    path_case_sensitive: bool = _PCASE,
    ) -> list[str]:
    ...


@overload
def checkURL(
    urls: list[list[str]],
    *,
    raise_malformed: bool = _RAISE,
    path_case_sensitive: bool = _PCASE,
    ) -> list[list[str]]:
    ...


def checkURL(urls, *, raise_malformed=_RAISE, path_case_sensitive=_PCASE):
    ret = None

    if isinstance(urls, str):
        urls = cast(str, urls)
        if TRACKER_URL_REGEX.match(urls):
            return normalizeURL(urls, path_case_sensitive)
        elif raise_malformed:
            raise ValueError(f'Invalid tracker url: "{urls}"')
        else:
            raise ValueError(f'Empty or no valid tracker.')

    elif isinstance(urls, list) and all(isinstance(u, str) for u in urls):
        urls = cast(list[str], urls)
        ret = [u for u in urls if TRACKER_URL_REGEX.match(u)]
        if len(ret) == len(urls) > 0:
            return [normalizeURL(u, path_case_sensitive) for u in ret]
        elif raise_malformed:
            raise ValueError(f'Invalid tracker url(s).')
        elif ret:
            return [normalizeURL(u, path_case_sensitive) for u in ret]
        else:
            raise ValueError(f'Empty or no valid tracker.')

    elif isinstance(urls, list) and all(isinstance(u, list) for u in urls):
        urls = cast(list[list[str]], urls)
        ret = [_lu for lu in urls if (_lu := [u for u in lu if TRACKER_URL_REGEX.match(u)])]
        if len(list(chain.from_iterable(ret))) == len(list(chain.from_iterable(urls))) > 0:
            return [[normalizeURL(u, path_case_sensitive) for u in lu] for lu in ret]
        elif raise_malformed:
            raise ValueError(f'Invalid tracker url(s).')
        elif ret:
            return [[normalizeURL(u, path_case_sensitive) for u in lu] for lu in ret]
        else:
            raise ValueError(f'Empty or no valid tracker.')

    else:
        raise TypeError('Invalid tracker url type.')


@overload
def handleIntIdx(
    index: int,
    length: int,
    ) -> int:
    ...


@overload
def handleIntIdx(
    index: Iterable[int],
    length: int,
    ) -> list[int]:
    ...


def handleIntIdx(index, length):
    if length < 2: raise ValueError('Invalid length.')
    if isinstance(index, int):
        a, b = divmod(index, length)
        if a > 0:
            return length  #! this means list.insert() always append
        elif a < -1:
            return 0  #! this means list.insert() always prepend
        else:
            return b
    elif isinstance(index, list):
        return [handleIntIdx(i, length) for i in index]
    else:
        raise TypeError('Invalid index type.')


@overload
def handleURL(
    urls: str,
    *,
    check_format: bool = _CHECK,
    raise_malformed: bool = _RAISE,
    ) -> str:
    ...


@overload
def handleURL(
    urls: strs,
    *,
    check_format: bool = _CHECK,
    raise_malformed: bool = _RAISE,
    ) -> list[str]:
    ...


@overload
def handleURL(
    urls: Sequence[strs],
    *,
    check_format: bool = _CHECK,
    raise_malformed: bool = _RAISE,
    ) -> list[list[str]]:
    ...


def handleURL(urls, *, check_format=_CHECK, raise_malformed=_RAISE):
    ret = None
    if isinstance(urls, str):
        ret = cast(str, urls)
    elif isinstance(urls, Sequence) and all(isinstance(i, str) for i in urls):
        ret = cast(list[str], list(urls))
    elif isinstance(urls, Sequence) and all(isinstance(i, Sequence) for i in urls):
        ret = cast(list[list[str]], [list(url) for url in urls])
    else:
        raise ValueError('Malformed urls input.')
    if not ret:
        raise ValueError(f'Empty tracker url.')
    return checkURL(ret, raise_malformed=raise_malformed) if check_format else ret
