__all__ = ['Trackers']

from itertools import chain
from collections.abc import Sequence
from typing import Optional, overload, cast

from torrentutils.type import strs
from torrentutils.helper import handleIntIdx, handleURL, compareURL
from torrentutils.config import CHECK_URL_FORMAT, RAISE_MALFORMED_URL, URL_UNIQUE_IN_TIERS, KEEP_EMPTY_TIER, TRACKER_URL_REGEX


class Trackers():

    def __init__(self, *args, **kwargs):
        '''Initialise a tracker list. Optionally set the initial trackers by calling the way as set().'''

        self._tiers: list[list[str]] = []  # List of List of Urls
        self._urls: list[str]|None = None  # All List of Urls, cached from self._llu

        if args or kwargs: self.set(*args, **kwargs)

    #* -----------------------------------------------------------------------------------------------------------------
    #* access internal data
    #* -----------------------------------------------------------------------------------------------------------------

    @property
    def tiers(self) -> list[list[str]]:
        '''Get a shallow copy of all tracker urls in all tiers.'''
        return [lu[:] for lu in self._tiers]

    @property
    def urls(self) -> list[str]:
        '''Get a simply deduplicated full list of all tracker urls.'''
        if self._urls is None: self._urls = list(set(chain.from_iterable(self._tiers)))
        return self._urls[:]

    #* -----------------------------------------------------------------------------------------------------------------
    #* general methods
    #* -----------------------------------------------------------------------------------------------------------------

    def has(self, url: str) -> bool:
        '''Check if the specified tracker url exists.'''
        for u in self.urls:
            if compareURL(u, url): return True
        return False

    def index(self, url: str) -> Optional[tuple[int, int]]:
        '''
        Get the (first) index [tier, pos] of the specified tracker url.
        Note that according to BEP 12, the tracker url's position in the tier does not matter as it should be shuffled.
        '''
        for i, lu in enumerate(self._tiers):
            for j, u in enumerate(lu):
                if compareURL(u, url): return (i, j)
        return None

    def set(
        self,
        urls: str|strs|Sequence[strs],
        index: Optional[int|Sequence[int]] = None,
        *,
        check_format: bool = CHECK_URL_FORMAT,
        raise_malformed: bool = RAISE_MALFORMED_URL,
        unique_in_tiers: bool = URL_UNIQUE_IN_TIERS,
        keep_empty_tier: bool = KEEP_EMPTY_TIER,
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
                self._tiers.insert(index, [urls])
                if not keep_empty_tier: self._dropEmptyTier()
            else:
                raise ValueError('Invalid index.')

        elif isinstance(urls, Sequence) and all(isinstance(item, str) for item in urls):
            urls = cast(list[str], urls)  #! cast to list[str] to avoid pyright error
            index = 0 if index is None else index
            if isinstance(index, int):
                index = handleIntIdx(index, len(self))
                if unique_in_tiers: self.remove(urls, keep_empty_tier=True)
                self._tiers.insert(index, urls)
                if not keep_empty_tier: self._dropEmptyTier()
            else:
                raise ValueError('Invalid index.')

        elif isinstance(urls, Sequence) and all(isinstance(item, Sequence) for item in urls
                                                ) and all(isinstance(item, str) for item in chain.from_iterable(urls)):
            urls = [list(lu) for lu in urls]
            index = 0 if index is None else index
            if isinstance(index, int):
                index = handleIntIdx(index, len(self))
                index = list(range(index, index + len(urls)))
            elif isinstance(index, Sequence) and all(isinstance(i, int) for i in index):
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
                self._tiers.insert(i, lu)
                if i < len(self): n_tier_added += 1
            if not keep_empty_tier: self._dropEmptyTier()

        else:
            raise ValueError('Malformed urls input.')

        self._urls = None

    def extend(
        self,
        urls: str|strs|Sequence[strs],
        *,
        index: Optional[int|Sequence[int]] = None,
        check_format: bool = CHECK_URL_FORMAT,
        raise_malformed: bool = RAISE_MALFORMED_URL,
        unique_in_tiers: bool = URL_UNIQUE_IN_TIERS,
        keep_empty_tier: bool = KEEP_EMPTY_TIER,
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
                self._tiers.insert(index, ([urls] + self._tiers.pop(index)) if index < len(self) else [urls])
                if not keep_empty_tier: self._dropEmptyTier()
            else:
                raise ValueError('Invalid index.')

        elif isinstance(urls, Sequence) and all(isinstance(item, str) for item in urls):
            urls = cast(list[str], urls)  #! cast to list[str] to avoid pyright error
            index = 0 if index is None else index
            if isinstance(index, int):
                index = handleIntIdx(index, len(self))
                if unique_in_tiers: self.remove(urls, keep_empty_tier=True)
                self._tiers.insert(index, (urls + self._tiers.pop(index)) if index < len(self) else urls)
                if not keep_empty_tier: self._dropEmptyTier()
            else:
                raise ValueError('Invalid index.')

        elif isinstance(urls, Sequence) and all(isinstance(item, Sequence) for item in urls
                                                ) and all(isinstance(item, str) for item in chain.from_iterable(urls)):
            urls = [list(lu) for lu in urls]
            index = 0 if index is None else index
            if isinstance(index, int):
                index = handleIntIdx(index, len(self))
                index = list(range(index, index + len(urls)))
            elif isinstance(index, Sequence) and all(isinstance(i, int) for i in index):
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
                    self._tiers.insert(i, lu + self._tiers.pop(i))
                else:
                    self._tiers.append(lu)
                    n_tier_added += 1
            if not keep_empty_tier: self._dropEmptyTier()

        else:
            raise ValueError('Malformed urls input.')

        self._urls = None

    def insert(
        self,
        urls: str|strs|Sequence[strs],
        *,
        index: Optional[int|Sequence[int]] = None,
        check_format: bool = CHECK_URL_FORMAT,
        raise_malformed: bool = RAISE_MALFORMED_URL,
        unique_in_tiers: bool = URL_UNIQUE_IN_TIERS,
        keep_empty_tier: bool = KEEP_EMPTY_TIER,
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
                self._tiers.insert(index, [urls])
                if not keep_empty_tier: self._dropEmptyTier()
            else:
                raise ValueError('Invalid index.')

        elif isinstance(urls, Sequence) and all(isinstance(item, str) for item in urls):
            urls = cast(list[str], urls)  #! cast to list[str] to avoid pyright error
            index = 0 if index is None else index
            if isinstance(index, int):
                index = handleIntIdx(index, len(self))
                if unique_in_tiers: self.remove(urls, keep_empty_tier=True)
                self._tiers.insert(index, urls)
                if not keep_empty_tier: self._dropEmptyTier()
            else:
                raise ValueError('Invalid index.')

        elif isinstance(urls, Sequence) and all(isinstance(item, Sequence) for item in urls
                                                ) and all(isinstance(item, str) for item in chain.from_iterable(urls)):
            urls = [list(lu) for lu in urls]
            index = 0 if index is None else index
            if isinstance(index, int):
                index = handleIntIdx(index, len(self))
                index = list(range(index, index + len(urls)))
            elif isinstance(index, Sequence) and all(isinstance(i, int) for i in index):
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
                self._tiers.insert(i, lu)
            if not keep_empty_tier: self._dropEmptyTier()

        else:
            raise ValueError('Malformed urls input.')
        self._urls = None

    def remove(self, urls: str|strs, keep_empty_tier: bool = KEEP_EMPTY_TIER):
        '''
        Remove specified tracker url(s) from all tiers.

        Arguments:
        urls: str|strs, one or more tracker urls to be removed.
        keep_empty_tier: bool=False, whether to keep tier(s) with no tracker left after removal.
        '''
        urls = [urls] if isinstance(urls, str) else list(urls)
        if keep_empty_tier:
            self._tiers = [[_url for _url in _tier if not any(compareURL(_url, url) for url in urls)]
                           for _tier in self._tiers]
        else:
            self._tiers = [
                tier for _tier in self._tiers
                if (tier := [_url for _url in _tier if not any(compareURL(_url, url) for url in urls)])
                ]
        self._urls = None

    def check(self) -> bool:
        '''
        Check if all tracker urls are valid.
        For now, this only checks if the url matches a regex pattern.
        '''
        for _tier in self._tiers:
            for _url in _tier:
                if not TRACKER_URL_REGEX.match(_url): return False
        return True

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
        self._urls = None

    def clear(self):
        '''Remove all tracker urls.'''
        self._tiers = []
        self._urls = []

    #* -----------------------------------------------------------------------------------------------------------------
    #* internal methods
    #* -----------------------------------------------------------------------------------------------------------------

    def _dropMalformedURL(self):
        for _tier in self._tiers:
            for j, _url in enumerate(_tier):
                if not TRACKER_URL_REGEX.match(_url):
                    _tier[j] = ''
            _tier[:] = [_url for _url in _tier if _url]
        self._urls = None

    def _dropDuplicatedURL(self):
        seen_urls: set[str] = set()
        for _tier in self._tiers:
            for i, _url in enumerate(_tier):
                if any(compareURL(_url, url) for url in seen_urls):
                    _tier[i] = ''
                else:
                    seen_urls.add(_url)
            _tier[:] = [_url for _url in _tier if _url]
        self._urls = None

    def _dropEmptyTier(self):
        self._tiers = [_tier for _tier in self._tiers if _tier]
        self._urls = None

    #* -----------------------------------------------------------------------------------------------------------------
    #* special methods
    #* -----------------------------------------------------------------------------------------------------------------

    @overload
    def __getitem__(self, key: int) -> list[str]:
        ...

    @overload
    def __getitem__(self, key: slice|Sequence[int]) -> list[list[str]]:
        ...

    def __getitem__(self, key):
        '''Get tracker urls of specified tier(s).'''
        if isinstance(key, int):
            return self._tiers[key][:]
        elif isinstance(key, slice):
            return [_tier[:] for _tier in self._tiers[key]]
        elif isinstance(key, Sequence) and all(isinstance(i, int) for i in key):
            return [self._tiers[i][:] for i in key]
        else:
            raise TypeError('Invalid index.')

    @overload
    def __setitem__(self, key: int, value: str|strs):
        ...

    @overload
    def __setitem__(self, key: slice|Sequence[int], value: Sequence[strs]):
        ...

    def __setitem__(self, key, value):
        '''Set tracker urls to specified tier.'''
        if isinstance(key, int):
            self.set(value, index=key)
        elif isinstance(key, slice):
            self.set(value, index=key)
        elif isinstance(key, Sequence) and all(isinstance(i, int) for i in key):
            self.set(value, index=list(key))
        else:
            raise TypeError('Invalid index.')

    def __delitem__(self, index: int|slice|Sequence[int]):
        '''Delete specified tier(s).'''
        if isinstance(index, int):
            del self._tiers[index]
            self._urls = None
        elif isinstance(index, slice):
            del self._tiers[index]
            self._urls = None
        elif isinstance(index, Sequence) and all(isinstance(i, int) for i in index):
            for i in index:
                self._tiers[i] = []
            self._dropEmptyTier()
        else:
            raise TypeError('Invalid index.')

    def __len__(self) -> int:
        '''Get the number of tiers.'''
        return len(self._tiers)

    def __contains__(self, url: str) -> bool:
        '''Alias of `has(url)`.'''
        return self.has(url)

    #* -----------------------------------------------------------------------------------------------------------------
    #* operators
    #* -----------------------------------------------------------------------------------------------------------------

    def __add__(self, urls: str|strs|Sequence[strs]) -> 'Trackers':
        '''Alias of `insert(urls)`.'''
        self.insert(urls)
        return self

    def __radd__(self, urls: str|strs|Sequence[strs]) -> 'Trackers':
        '''Alias of `insert(urls)`.'''
        self.insert(urls)
        return self

    def __iadd__(self, urls: str|strs|Sequence[strs]):
        '''Alias of `insert(urls)`.'''
        self.insert(urls)

    def __sub__(self, urls: str|strs) -> 'Trackers':
        '''Alias of `remove(urls)`.'''
        self.remove(urls)
        return self

    def __rsub__(self, urls: str|strs) -> 'Trackers':
        '''Alias of `remove(urls)`.'''
        self.remove(urls)
        return self

    def __isub__(self, urls: str|strs):
        '''Alias of `remove(urls)`.'''
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
            return self._tiers[0][0]
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
        return [_tier[:] for _tier in self._tiers] if len(self.urls) >= 2 else None

    @announce_list.setter
    def announce_list(self, urls: strs|Sequence[strs]):
        '''Overwrite the whole tracker list with at least 2 trackers.'''
        if all(isinstance(u, str) for u in urls):
            urls = cast(strs, urls)  #! cast to list[str] to avoid pyright error
            new_urls = list(urls)
        elif all(isinstance(u, Sequence) for u in urls) and all(isinstance(u, str) for u in chain.from_iterable(urls)):
            urls = cast(Sequence[strs], urls)
            new_urls = list(chain.from_iterable(urls))
        else:
            raise ValueError('Malformed urls input.')
        if len([u for u in list(set(new_urls)) if u]) < 2:
            raise ValueError('At least 2 trackers are required for setting announce-list.')
        else:
            self.clear()
            self.set(urls)
