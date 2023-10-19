__all__ = ['Trackers']

from itertools import chain
from collections.abc import Sequence, Sequence
from typing import Optional, overload, cast
from torrentutils.type import strs

from torrentutils.helper import handleIntIdx, handleURL
from torrentutils.config import CHECK_URL_FORMAT as _CHECK
from torrentutils.config import RAISE_MALFORMED_URL as _RAISE
from torrentutils.config import URL_UNIQUE_IN_TIERS as _DEDUP
from torrentutils.config import KEEP_EMPTY_TIER as _KPEPY
from torrentutils.config import TRACKER_URL_REGEX


class Trackers():

    def __init__(self, *args, **kwargs):
        '''Initialise a tracker list. Optionally set the tracker urls, the same as calling set().'''

        self._llu: list[list[str]] = []  # List of List of Urls
        self._alu: list[str]|None = None  # All List of Urls, cached from self._llu

        if args or kwargs: self.set(*args, **kwargs)

    #* -----------------------------------------------------------------------------------------------------------------
    #* access internal data
    #* -----------------------------------------------------------------------------------------------------------------

    @property
    def tiers(self) -> list[list[str]]:
        '''Get a shallow copy of all tracker urls in all tiers.'''
        return [lu[:] for lu in self._llu]

    @property
    def urls(self) -> list[str]:
        '''Get a deduplicated full list of tracker urls.'''
        if self._alu is None: self._alu = list(set(chain.from_iterable(self._llu)))
        return self._alu[:]

    #* -----------------------------------------------------------------------------------------------------------------
    #* general methods
    #* -----------------------------------------------------------------------------------------------------------------

    def has(self, url: str) -> bool:
        '''Check if the specified tracker url exists.'''
        return url in self.urls

    def index(self, url: str) -> Optional[tuple[int, int]]:
        '''
        Get the (first) index [tier, pos] of the specified tracker url.
        Note that according to BEP 12, the tracker url's position in the tier does not matter as it should be shuffled.
        '''
        for i, lu in enumerate(self._llu):
            for j, u in enumerate(lu):
                if u == url: return i, j
        return None

    def set(
        self,
        urls: str|strs|Sequence[strs],
        index: Optional[int|Sequence[int]] = None,
        *,
        check_format: bool = _CHECK,
        raise_malformed: bool = _RAISE,
        unique_in_tiers: bool = _DEDUP,
        keep_empty_tier: bool = _KPEPY,
        ):
        '''
        Set the tracker urls of one or more tiers (!drop! previous ones).

        Arguments:
        urls: str|strs|Sequence[strs]
        index: Optional[int|Sequence[int]] = None
            if str, set a tier to this single tracker
                if index is None, it will be set to the 1st tier, same as index=0;
                if index is int, it will be set to the specified tier;
                raise error if index is Sequence[int].
            if strs (Sequence[str]), set a tier to these trackers
                if index is None, they will be set to the 1st tier, same as index=0;
                if index is int, they will be set to the specified tier;
                raise error if index is Sequence[int].
            if Sequence[strs], set tiers to these lists of trackers respectively
                if index is None, each list will be set starting from the 1st tier, same as index=0;
                if index is int, each list will be set to tiers starting from the specified tier;
                if index is Sequence[int], each list will be set to the specified tiers respectively.
                    this asks for len(urls)==len(index)
            note that if any specified tier does not exist, given trackers will be created as a new tier to the end.
        check_format: bool=True, whether to check the url matches a regex pattern.
            this will also change the scheme and host part to lower case (RFC 3986 Section 6.2.2.1)
            leaving this to False to preserve the original url stored in existing torrent files when loading them
        raise_malformed: bool=False, only works when check_format==True
            if True, raise ValueError if any url does not match the regex pattern
            if False, silently drop the url from input
            note that empty or emptied input will always cause ValueError
        unique_in_tiers: bool=True, whether to remove duplications of this tracker from other tiers
            this is done before the setting operation
        keep_empty_tier: bool=False, whether to keep empty tier(s) if unique_in_tiers==True
            set True will always keep the specified tier(s) seen at expected tiers
        '''

        urls = handleURL(urls, check_format=check_format, raise_malformed=raise_malformed)

        if isinstance(urls, str):
            index = 0 if index is None else index
            if isinstance(index, int):
                index = handleIntIdx(index, len(self))
                if unique_in_tiers: self.remove(urls, keep_empty_tier=True)
                self._llu.insert(index, [urls])
                if not keep_empty_tier: self._dropEmptyTier()
            else:
                raise ValueError('Invalid index.')

        elif isinstance(urls, Sequence) and all(isinstance(item, str) for item in urls):
            urls = cast(list[str], urls)  #! cast to list[str] to avoid pyright error
            index = 0 if index is None else index
            if isinstance(index, int):
                index = handleIntIdx(index, len(self))
                if unique_in_tiers: self.remove(urls, keep_empty_tier=True)
                self._llu.insert(index, urls)
                if not keep_empty_tier: self._dropEmptyTier()
            else:
                raise ValueError('Invalid index.')

        elif isinstance(urls, Sequence) and all(isinstance(item, Sequence) for item in urls):
            urls = [list(lu) for lu in urls]
            index = 0 if index is None else index
            if isinstance(index, int):
                index = handleIntIdx(index, len(self))
                index = list(range(index, index + len(urls)))
            elif isinstance(index, Sequence):
                if not all(isinstance(i, int) for i in index): raise ValueError('Invalid index.')
                if len(index) != len(urls): raise ValueError('Invalid index length.')
                index = handleIntIdx(index, len(self))
                index, urls = list(zip(*sorted(zip(index, urls), key=lambda x: x[0])))  # must be stable sort
                index = cast(list[int], index)  #! cast to list[int] to avoid pyright error
                urls = cast(list[list[str]], urls)  #! cast to list[list[str]] to avoid pyright error
            else:
                raise ValueError('Invalid index.')
            n_tier_added = 0
            for i, lu in zip(index, urls):
                if unique_in_tiers: self.remove(lu, keep_empty_tier=True)
                i += n_tier_added
                self._llu.insert(i, lu)
                if i < len(self): n_tier_added += 1
            if not keep_empty_tier: self._dropEmptyTier()

        else:
            raise ValueError('Malformed urls input.')

        self._alu = None

    def extend(
        self,
        urls: str|strs|Sequence[strs],
        *,
        index: Optional[int|Sequence[int]] = None,
        check_format: bool = _CHECK,
        raise_malformed: bool = _RAISE,
        unique_in_tiers: bool = _DEDUP,
        keep_empty_tier: bool = _KPEPY,
        ):
        '''
        Extend tracker tier(s) with new tracker url(s).

        Arguments:
        urls: str|strs|Sequence[strs]
        index: Optional[int|Sequence[int]] = None
            if str, append a single tracker to a tier
                if index is None, it will be prepended to the 1st tier, same as index=0;
                if index is int, it will be prepended into the specified tier;
                raise error if index is Sequence[int].
            if urls is strs (Sequence[str]), append multiple trackers to a tier
                if index is None, they will be prepended to the 1st tier, same as index=0;
                if index is int, they will be prepended to the specified tier;
                raise error if index is Sequence[int].
            if Sequence[strs], append multiple lists of trackers to corresponding tiers
                if index is None, each list will be prepended as same as index=0 (1st tier);
                if index is int, each list will be prepended to tiers starting from the specified tier;
                if index is Sequence[int], each list will be prepended to the specified tiers respectively.
                    this asks for the length of index to be the same as the length of the list of trackers.
            note that if any specified tier does not exist, given trackers will be created as a new tier to the end.
        check_format: bool=True, whether to check the url matches a regex pattern.
            this will also change the scheme and host part to lower case (RFC 3986 Section 6.2.2.1)
            leaving this to False to preserve the original url stored in existing torrent files when loading them
        raise_malformed: bool=False, only works when check_format==True
            if True, raise ValueError if any url does not match the regex pattern
            if False, silently drop the url from input
            note that empty or emptied input will always cause ValueError
        unique_in_tiers: bool=True, whether to remove duplications of this tracker from other tiers
            this is done before the extending operation
        keep_empty_tier: bool=False, whether to keep empty tier(s) if unique_in_tiers==True
            set True will always keep the specified tier(s) seen at expected tiers
        '''

        urls = handleURL(urls, check_format=check_format, raise_malformed=raise_malformed)

        if isinstance(urls, str):
            index = 0 if index is None else index
            if isinstance(index, int):
                index = handleIntIdx(index, len(self))
                if unique_in_tiers: self.remove(urls, keep_empty_tier=True)
                self._llu.insert(index, ([urls] + self._llu.pop(index)) if index < len(self) else [urls])
                if not keep_empty_tier: self._dropEmptyTier()
            else:
                raise ValueError('Invalid index.')

        elif isinstance(urls, Sequence) and all(isinstance(item, str) for item in urls):
            urls = cast(list[str], urls)  #! cast to list[str] to avoid pyright error
            index = 0 if index is None else index
            if isinstance(index, int):
                index = handleIntIdx(index, len(self))
                if unique_in_tiers: self.remove(urls, keep_empty_tier=True)
                self._llu.insert(index, (urls + self._llu.pop(index)) if index < len(self) else urls)
                if not keep_empty_tier: self._dropEmptyTier()
            else:
                raise ValueError('Invalid index.')

        elif isinstance(urls, Sequence) and all(isinstance(item, Sequence) for item in urls):
            urls = [list(lu) for lu in urls]
            index = 0 if index is None else index
            if isinstance(index, int):
                index = handleIntIdx(index, len(self))
                index = list(range(index, index + len(urls)))
            elif isinstance(index, Sequence):
                if not all(isinstance(i, int) for i in index): raise ValueError('Invalid index.')
                if len(index) != len(urls): raise ValueError('Invalid index length.')
                index = handleIntIdx(index, len(self))
                index, urls = list(zip(*sorted(zip(index, urls), key=lambda x: x[0])))  # must be stable sort
                index = cast(list[int], index)  #! cast to list[int] to avoid pyright error
                urls = cast(list[list[str]], urls)  #! cast to list[list[str]] to avoid pyright error
            else:
                raise ValueError('Invalid index.')
            n_tier_added = 0
            for i, lu in zip(index, urls):
                if unique_in_tiers: self.remove(lu, keep_empty_tier=True)
                i += n_tier_added
                if i < len(self):
                    self._llu.insert(i, lu + self._llu.pop(i))
                else:
                    self._llu.append(lu)
                    n_tier_added += 1
            if not keep_empty_tier: self._dropEmptyTier()

        else:
            raise ValueError('Malformed urls input.')

        self._alu = None

    def insert(
        self,
        urls: str|strs|Sequence[strs],
        *,
        index: Optional[int|Sequence[int]] = None,
        check_format: bool = _CHECK,
        raise_malformed: bool = _RAISE,
        unique_in_tiers: bool = _DEDUP,
        keep_empty_tier: bool = _KPEPY,
        ):
        '''
        Insert new tier(s) with tracker url(s) at the specified position(s).

        Arguments:
        urls: str|strs|Sequence[strs]
        index: Optional[int|Sequence[int]] = None
            if urls is str, add this single tracker as a new tier
                if index is None, it will be inserted as the new 1st tier, same as index=0;
                if index is int, it will be inserted as a new tier as specified by index;
                raise raise_malformed if index is Sequence[int].
            if urls is strs (Sequence[str]), add these trackers as a new tier
                if index is None, they will be inserted as the new 1st tier, same as index=0;
                if index is int, they will be inserted as a new tier as specified by index;
                raise error if index is Sequence[int].
            if Sequence[strs], add these lists of trackers as new tiers
                if index is None, these list will be inserted as new tiers over all existing tiers, same as index=0;
                if index is int, these list will be inserted as new tiers starting from the specified tier;
                if index is Sequence[int], each list will be inserted into the specified tiers respectively.
                    this asks for the length of index to be the same as the length of the list of trackers.
            note that if any specified tier does not exist, given trackers will be created as a new tier to the end.
        check_format: bool=True, whether to check the url matches a regex pattern.
            this will also change the scheme and host part to lower case (RFC 3986 Section 6.2.2.1)
            leaving this to False to preserve the original url stored in existing torrent files when loading them
        raise_malformed: bool=False, only works when check_format==True
            if True, raise ValueError if any url does not match the regex pattern
            if False, silently drop the url from input
            note that empty or emptied input will always cause ValueError
        unique_in_tiers: bool=True, whether to remove duplications of this tracker from other tiers
            this is done before the setting operation
        keep_empty_tier: bool=False, whether to keep empty tier(s) if unique_in_tiers==True
            set True will always keep the specified tier(s) seen at expected tiers
        '''

        urls = handleURL(urls, check_format=check_format, raise_malformed=raise_malformed)

        if isinstance(urls, str):
            index = 0 if index is None else index
            if isinstance(index, int):
                index = handleIntIdx(index, len(self))
                if unique_in_tiers: self.remove(urls, keep_empty_tier=True)
                self._llu.insert(index, [urls])
                if not keep_empty_tier: self._dropEmptyTier()
            else:
                raise ValueError('Invalid index.')

        elif isinstance(urls, Sequence) and all(isinstance(item, str) for item in urls):
            urls = cast(list[str], urls)  #! cast to list[str] to avoid pyright error
            index = 0 if index is None else index
            if isinstance(index, int):
                index = handleIntIdx(index, len(self))
                if unique_in_tiers: self.remove(urls, keep_empty_tier=True)
                self._llu.insert(index, urls)
                if not keep_empty_tier: self._dropEmptyTier()
            else:
                raise ValueError('Invalid index.')

        elif isinstance(urls, Sequence) and all(isinstance(item, Sequence) for item in urls):
            urls = [list(lu) for lu in urls]
            index = 0 if index is None else index
            if isinstance(index, int):
                index = handleIntIdx(index, len(self))
                index = list(range(index, index + len(urls)))
            elif isinstance(index, Sequence):
                if not all(isinstance(i, int) for i in index): raise ValueError('Invalid index.')
                if len(index) != len(urls): raise ValueError('Invalid index length.')
                index = handleIntIdx(index, len(self))
                index, urls = list(zip(*sorted(zip(index, urls), key=lambda x: x[0])))  # must be stable sort
                index = cast(list[int], index)  #! cast to list[int] to avoid pyright error
                urls = cast(list[list[str]], urls)  #! cast to list[list[str]] to avoid pyright error
            else:
                raise ValueError('Invalid index.')
            for n_tier_added, (i, lu) in enumerate(zip(index, urls)):
                if unique_in_tiers: self.remove(lu, keep_empty_tier=True)
                i = i + n_tier_added
                self._llu.insert(i, lu)
            if not keep_empty_tier: self._dropEmptyTier()

        else:
            raise ValueError('Malformed urls input.')
        self._alu = None

    def remove(self, urls: str|strs, keep_empty_tier: bool = _KPEPY):
        '''
        Remove specified tracker url(s) from all tiers.

        Arguments:
        urls: str|strs, the tracker url(s) to be removed.
        keep: bool=False, whether to keep tier(s) with no tracker left.
        # count: int=0
        #     only remove this number of occurrences.
        #     if count <= 0, remove all occurrences.

        '''
        urls = [urls] if isinstance(urls, str) else list(urls)
        urls = [u.lower() for u in urls]
        if keep_empty_tier:
            self._llu = [[u for u in _lu if (u.lower() not in urls)] for _lu in self._llu]
        else:
            self._llu = [lu for _lu in self._llu if (lu := [u for u in _lu if (u.lower() not in urls)])]
        self._alu = None

    def check(self) -> bool:
        '''Check if all tracker urls are valid.'''
        for tier in self._llu:
            for url in tier:
                if not TRACKER_URL_REGEX.match(url): return False
        return True

    def _dropMalformedURL(self):
        for ul in self._llu:
            for j, u in enumerate(ul[:]):
                if not TRACKER_URL_REGEX.match(u):
                    ul.pop(j)

    def _dropDuplicatedURL(self):
        for url in self.urls:
            for ul in self._llu:
                for j, u in enumerate(ul[:]):
                    if u == url:
                        ul.pop(j)

    def _dropEmptyTier(self):
        for i, ul in enumerate(self._llu[:]):
            if not ul:
                self._llu.pop(i)

    def clean(
        self,
        *,
        keep_malformed: bool = False,
        keep_duplicated: bool = False,
        keep_empty_tier: bool = False,
        ):
        '''
        Clean up the tracker list, with options to turn off some cleaning.

        Arguments:
        keep_malformed: bool = False, whether to keep malformed tracker urls.
        keep_duplicated: bool = False, whether to keep duplicated tracker urls.
        keep_empty_tier: bool = False, whether to keep empty tier(s).
        '''
        if not keep_malformed:
            self._dropMalformedURL()
        if not keep_duplicated:
            self._dropDuplicatedURL()
        if not keep_empty_tier:
            self._dropEmptyTier()

    def clear(self):
        '''Remove all tracker urls.'''
        self._llu = []
        self._alu = []

    #* -----------------------------------------------------------------------------------------------------------------
    #* special methods
    #* -----------------------------------------------------------------------------------------------------------------

    @overload
    def __getitem__(self, key: int) -> list[str]:
        ...

    @overload
    def __getitem__(self, key: slice|Sequence[int]) -> list[list[str]]:
        ...

    def __getitem__(self, key: int|slice|Sequence[int]) -> list[str]|list[list[str]]:
        '''Get tracker urls of specified tier(s).'''
        if isinstance(key, int):
            return self._llu[key][:]
        elif isinstance(key, slice):
            return [lu[:] for lu in self._llu[key]]
        elif isinstance(key, Sequence) and all(isinstance(i, int) for i in key):
            return [self._llu[i][:] for i in set(key)]
        else:
            raise TypeError('Invalid index.')

    def __setitem__(self, key: int, values: str|strs):
        '''Set the tracker urls in the specified tier if index is int.'''
        if isinstance(key, int):
            self.set(values, index=key, check_format=_CHECK, raise_malformed=_RAISE)
        else:
            self[key] = values

    def __delitem__(self, index: int|slice|Sequence[int]):
        '''Delete the specified tier.'''
        if isinstance(index, int):
            del self._llu[index]
            self._alu = None
        elif isinstance(index, slice):
            del self._llu[index]
            self._alu = None
        elif isinstance(index, Sequence) and all(isinstance(i, int) for i in index):
            for i in sorted(index, reverse=True):
                del self._llu[i]
            self._alu = None
        else:
            raise TypeError('Invalid index.')

    def __len__(self) -> int:
        '''Get the number of tiers.'''
        return len(self._llu)

    #* -----------------------------------------------------------------------------------------------------------------
    #* operators
    #* -----------------------------------------------------------------------------------------------------------------

    def __contains__(self, url: str) -> bool:
        '''Check if the specified tracker url exists.'''
        return self.has(url)

    def __add__(self, urls: str|strs|Sequence[strs]) -> 'Trackers':
        '''Prepend the specified tracker url(s) as the new 1st tier.'''
        self.insert(urls)
        return self

    def __radd__(self, urls: str|strs|Sequence[strs]) -> 'Trackers':
        '''Prepend the specified tracker url(s) as the new 1st tier.'''
        self.insert(urls)
        return self

    def __iadd__(self, urls: str|strs|Sequence[strs]):
        '''Prepend the specified tracker url(s) as the new 1st tier.'''
        self.insert(urls)

    def __sub__(self, urls: str|strs) -> 'Trackers':
        '''Remove the specified tracker url(s).'''
        self.remove(urls)
        return self

    def __rsub__(self, urls: str|strs) -> 'Trackers':
        '''Remove the specified tracker url(s).'''
        self.remove(urls)
        return self

    def __isub__(self, urls: str|strs):
        '''Remove the specified tracker url(s).'''
        self.remove(urls)

    #* -----------------------------------------------------------------------------------------------------------------
    #* properties imitating keys existing in an actual torrent
    #* -----------------------------------------------------------------------------------------------------------------

    @property
    def announce(self) -> Optional[str]:
        '''
        Return the `announce` entry of the torrent.
        In practice, this means the first tracker url in the `announce-list` entry.
        '''
        try:
            return self._llu[0][0]
        except IndexError:
            return None

    @announce.setter
    def announce(self, url: str):
        '''
        Modify the `announce` entry of the torrent.
        In practice, this means the first tracker url in the `announce-list` entry.
        '''
        self.extend(url)

    @property
    def announce_list(self) -> Optional[list[list[str]]]:
        '''
        Return the `announce-list` entry of the torrent (BEP 12)
        In practice, this is only valid if total trackers >=2.

        Note that this property returns a shallow copy of the tracker list.
        i.e. list operations on the returned list or its nested lists has no effect on the original tracker list.
        '''
        return [lu[:] for lu in self._llu] if len(self.urls) > 1 else None

    @announce_list.setter
    def announce_list(self, urls: strs|Sequence[strs]):
        '''Overwrite the whole tracker list with at least 2 trackers.'''
        new_urls = list(urls) if all(isinstance(u, str) for u in urls) else list(chain.from_iterable(urls))
        new_urls = cast(list[str], new_urls)  #! cast to list[str] to avoid pyright error
        new_urls = [u for u in list(set(new_urls)) if u]
        if len(new_urls) < 2:
            raise ValueError('At least 2 trackers are required for setting announce-list.')
        else:
            self.clear()
            self.set(urls)
