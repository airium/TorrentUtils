import re
import os
import math
import time
import codecs
import hashlib
import pathlib
import warnings
import urllib.parse
from dataclasses import dataclass
from operator import methodcaller
from typing import Iterable, Optional, TypedDict, Any, Set

try:
    import tqdm
except ImportError:
    pass

try:
    import dateutil.parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False

from bencoder import bencode, bdecode


_ASCII = re.compile(r'[a-z0-9]+', re.IGNORECASE)




def _hash(bchars: bytes) -> bytes:
    '''Return the sha1 hash for the given bytes.'''
    if isinstance(bchars, bytes):
        hasher = hashlib.sha1()
        hasher.update(bchars)
        return hasher.digest()
    else:
        raise TypeError(f"Expect bytes, not {type(bchars)}.")




class TorrentNotReady(Exception):
    pass




class PieceSizeTooSmall(ValueError):
    pass




class PieceSizeTooLarge(ValueError):
    pass




class PieceSizeUncommon(ValueError):
    pass




class EmptySourceSize(ValueError):
    pass




def fromTorrent(path):
    '''Wrapper function to read a torrent file and return it.'''
    torrent = Torrent()
    torrent.read(pathlib.Path(path))
    return torrent




def fromFiles(path):
    '''Wrapper function to load files as a torrent and return it.'''
    torrent = Torrent()
    torrent.load(pathlib.Path(path))
    return torrent




'''=====================================================================================================================
Core Torrent Class
====================================================================================================================='''




@dataclass
class _TorrentMeta():

    '''The basic yet most common dict of the torrent'''
    trackers: list[str] = []  # the list of tracker urls
    comment: str = ''  # the comment message'
    creator: str = ''  # the creator of the torrent
    date: int = 0  # the creation time
    encoding: str = 'UTF-8'  # the encoding for text
    hash: str = ''  # the hash of the torrent




@dataclass
class _TorrentInfo():

    '''the `info` dict of the torrent'''
    files: list[tuple[pathlib.PurePath, int]] = []  # the list of list of file size and path parts
    name: str = ''  # the root name of the torrent
    piece_length: int = 4096 << 10  # the piece size in bytes
    pieces: bytes = b''  # the long raw bytes of pieces' sha1
    private: int = 0  # 1 if the torrent is private, otherwise 0
    source: str = ''  # the special message particularly used by private trackers




class FileInfo(TypedDict):
    path: tuple[str, ...]
    size: int




class Torrent():

    def __init__(self, **torrent_set_kwargs):
        '''
        Instantiate a blank torrent, optionally with runtime parameters as well as any arguments acceptable by Torrent.set() to override the default metadata.
        '''
        self._meta: _TorrentMeta = _TorrentMeta()
        self._info: _TorrentInfo = _TorrentInfo()
        self._misc: dict = {}
        self.set(**torrent_set_kwargs)

    #* -----------------------------------------------------------------------------------------------------------------
    #* The following properties mimic the keys existing in an actual torrent.
    #* Note that if the boolen evaluation of the returned value is `False`, the key does not exist.
    #* -----------------------------------------------------------------------------------------------------------------

    @property
    def announce(self) -> str:
        '''Return the first tracker url if exists, otherwise an empty string.'''
        return self._meta.trackers[0] if self._meta.trackers else ''

    @announce.setter
    def announce(self, url: str):
        '''Overwrite the first tracker url.'''
        self.setTracker([url] + self._meta.trackers[1:])

    @property
    def announce_list(self) -> list[str]:
        '''Return all trackers if total trackers >=2, otherwise an empty list.'''
        return self._meta.trackers[:] if self.num_tracker >= 2 else []

    @announce_list.setter
    def announce_list(self, urls: Iterable[str]):
        '''Overwrite the whole tracker list with at least 2 trackers.'''
        urls = list(urls)  #! we dont have input check here, which may result in a bug
        if len(urls) < 2: raise ValueError(f'You must supply >=2 trackers to `announce-list` (got {len(urls)}.')
        self.setTracker(urls)

    @property
    def comment(self) -> str:
        '''Return the comment message displayable in various clients.'''
        return self._meta.comment[:]

    @comment.setter
    def comment(self, chars: str):
        '''Set the comment message.'''
        self.setComment(chars)

    @property
    def created_by(self) -> str:
        '''Return the creator of the torrent.'''
        return self._meta.creator[:]

    @created_by.setter
    def created_by(self, creator: str):
        '''Set the creator of the torrent.'''
        self.setCreator(creator)

    @property
    def creation_date(self) -> int:
        '''Return torrent creation time as the number of second since 1970-01-01.'''
        return self._meta.date

    @creation_date.setter
    def creation_date(self, date: int):
        '''Set torrent creation time.'''
        self.setDate(date)

    @property
    def encoding(self) -> str:
        '''Return the encoding for text.'''
        return self._meta.encoding[:]

    @encoding.setter
    def encoding(self, enc: str):
        '''Set the encoding for text.'''
        self.setEncoding(enc)

    @property
    def hash(self) -> str:
        '''Return the torrent hash at the moment. Read-only.'''
        return _hash(bencode(self.info_dict, self.encoding)).hex()

    @property
    def files(self) -> list[dict[str, int|tuple[str, ...]]]:
        '''
        Return a list of dict of file size and path parts if files number >=2. Read-only.
        Corresponding to torrent['info']['files'] in an actual torrent.
        '''
        return list({'path': fpath.parts, 'length': fsize} for (fpath, fsize) in self._info.files) \
               if len(self._info.files) > 1 else []

    @property
    def length(self) -> int:
        '''
        Return the size of single file torrent. Read-only.
        Corresponding to torrent['info']['length'] in an actual torrent.
        '''
        return self._info.files[0][1] if len(self._info.files) == 1 else 0

    @property
    def name(self) -> str:
        '''
        Return the root name of the torrent.
        Corresponding to torrent['info']['name'] in an actual torrent.
        '''
        return self._info.name[:]

    @name.setter
    def name(self, name: str):
        '''Set the root name of the torrent.'''
        self.setName(name)

    @property
    def piece_length(self) -> int:
        '''
        Return the piece size in bytes.
        Corresponding to torrent['info']['piece length'] in an actual torrent.
        '''
        return self._info.piece_length

    @piece_length.setter
    def piece_length(self, size: int):
        '''
        Set the piece size in bytes.
        Note that setting a new value will clear any existing torrent piece hashes.
        '''
        self.setPieceLength(size)

    @property
    def pieces(self) -> bytes:
        '''
        Return the long raw bytes of pieces' sha1. Read-only.
        Corresponding to torrent['info']['pieces'] in an actual torrent.
        '''
        return self._info.pieces[:]

    @property
    def private(self) -> int:
        '''
        Return 1 if the torrent is private, otherwise 0.
        Corresponding to torrent['info']['private'] in an actual torrent.
        '''
        return 1 if self._info.private else 0

    @private.setter
    def private(self, private: int|bool):
        '''Set torrent private or not.'''
        self.setPrivate(private)

    @property
    def source(self) -> str:
        '''
        Return a special message typically used in private torrent to alter hash.
        Corresponding to torrent['info']['source'] in an actual torrent.
        '''
        return self._info.source[:]

    @source.setter
    def source(self, src: str):
        '''
        Set a special message typically used in private torrent to alter hash.
        The value is normally invisible in various clients.
        '''
        self.setSource(src)

    #* -----------------------------------------------------------------------------------------------------------------
    #* Useful public torrent properties
    #* -----------------------------------------------------------------------------------------------------------------

    @property
    def tracker_list(self) -> list[str]:
        '''Unlike `announce` and `announce_list`, this function always returns the full tracker list.'''
        return self._meta.trackers[:]

    @tracker_list.setter
    def tracker_list(self, urls: Iterable[str]):
        '''Set the whole list of tracker urls.'''
        self.setTracker(urls)

    @property
    def num_tracker(self) -> int:
        '''Return the number of trackers. Read-only.'''
        return len(self._meta.trackers)

    @property
    def file_list(self) -> list[FileInfo]:
        '''Unlike `length` and `files`, this function always returns the full list of dict of file parts and size. Read-only.'''
        return list(FileInfo(path=fpath.parts, size=fsize) for (fpath, fsize) in self._info.files)

    @property
    def size(self) -> int:
        '''Return the total size of all source files recorded in the torrent. Read-only.'''
        return sum(fsize for (_, fsize) in self._info.files)

    @property
    def torrent_size(self) -> int:
        '''Return the file size of the torrent file itself. Read-only.'''
        return len(bencode(self.torrent_dict, self.encoding))

    @property
    def num_pieces(self) -> int:
        '''Return the total number of pieces within the torrent. Read-only.'''
        return len(self._info.pieces) // 20

    @property
    def num_files(self) -> int:
        '''Return the total number of files within the torrent. Read-only.'''
        return len(self.file_list)

    @property
    def magnet(self) -> str:
        '''Return the magnet link of the torrent. Read-only.'''
        ret = f"magnet:?xt=urn:btih:{self.hash}"
        if self.name:
            ret += f"&dn={urllib.parse.quote(self.name)}"
        if self.size:
            ret += f"&xl={self.size}"
        for url in self.tracker_list:
            ret += f"&tr={urllib.parse.quote(url)}"
        return ret

    @property
    def minimal_magnet(self) -> str:
        '''Return the minimal magnet link of the torrent. Read-only.'''
        return f"magnet:?xt=urn:btih:{self.hash}"

    def get(self, key: str, ret_on_missing_key: Any = None, error_on_unknown_key: bool = False) -> Any:
        '''
        Get metadata with flexible key aliases.

        All aliases are case-insensitive.
        Only ASCII letters and digits are used to find the key e.g. `dA_t e` => `date`.
        Similar to properties, the method raises no error on missing key and return `ret_on_missing_key` (default=None).
        But you can set `error_on_unknown_key` to True to raise `KeyError` on unknown key.

        #! the aliases are subject to change in future versions.

        Supported aliases: (most common ones have one-char shortcut)

            tracker: t|tl|trackers|tl|tlist|trackerlist|announce|announces|announcelist|alist
            comment: c|comm|comments
            creator: b|by|createdby|creator|tool|creatingtool|maker|madeby
            date: d|time|second|seconds|creationdate|creationtime|creatingdate|creatingtime
            encoding: e|enc|encoding|codec
            name: n|name|torrentname
            piece size: ps|pl|psz|psize|piecesize|piecelength
            private: p|priv|pt|pub|public #! note that (pub|public) give reverse result
            source: s|src
            filelist: fl|flist
            size: ssz|sourcesize|sourcesz
            torrentsize: tsz|torrentsize|torrentsz
            numpieces: np|numpiece
            numfiles: nf|numfile|numfiles
            hash: th|torrenthash|sha1
            magnet: magnetlink|magneturl
        '''
        key = _ASCII.sub('', key).lower()

        match key:
            case 't'|'tracker'|'trackers'|'tl'|'tlist'|'trackerlist'|'announce'|'announces'|'announcelist'|'alist':
                ret = self.tracker_list
            case 'comment'|'c'|'comm'|'comments':
                ret = self.comment
            case 'creator'|'b'|'by'|'createdby'|'creator'|'tool'|'creatingtool'|'maker'|'madeby':
                ret = self.created_by
            case 'date'|'time'|'second'|'seconds'|'creationdate'|'creationtime'|'creatingdate'|'creatingtime':
                ret = self.creation_date
            case 'encoding'|'e'|'enc'|'encoding'|'codec':
                ret = self.encoding
            case 'name'|'n'|'name'|'torrentname':
                ret = self.name
            case 'ps'|'pl'|'psz'|'psize'|'piecesize'|'piecelength':
                ret = self.piece_length
            case 'private'|'p'|'priv'|'pt'|'pub'|'public':
                ret = self.private
            case 'source'|'s'|'src':
                ret = self.source
            case 'filelist'|'fl'|'flist':
                ret = self.file_list
            case 'size'|'ssz'|'sourcesize'|'sourcesz':
                ret = self.size
            case 'torrentsize'|'tsz'|'torrentsize'|'torrentsz':
                ret = self.torrent_size
            case 'numpieces'|'np'|'numpiece':
                ret = self.num_pieces
            case 'numfiles'|'nf'|'numfile'|'numfiles':
                ret = self.num_files
            case 'hash'|'th'|'torrenthash'|'sha1':
                ret = self.hash
            case 'magnet'|'magnetlink'|'magneturl':
                ret = self.magnet
            case _:
                if error_on_unknown_key:
                    raise KeyError(f'Unknown key: {key}')
                else:
                    ret = ret_on_missing_key

        return ret

    #* -----------------------------------------------------------------------------------------------------------------
    #* The following properties does not support `get()` method
    #* -----------------------------------------------------------------------------------------------------------------

    @property
    def info_dict(self) -> dict[str, Any]:
        '''Return the `info` dict of the torrent that affects hash. Read-only.'''
        ret: dict[str, Any] = {}
        if length := self.length: ret['length'] = length
        if files := self.files: ret['files'] = files
        assert not (length and files), 'Torrent cannot have both `length` and `files`. Report file a bug report.'
        if tnm := self.name: ret['name'] = tnm
        if psz := self.piece_length: ret['piece length'] = psz
        if pcs := self.pieces: ret['pieces'] = pcs
        if pri := self.private: ret['private'] = pri
        if src := self.source: ret['source'] = src
        return ret

    @property
    def torrent_dict(self) -> dict[str, Any]:
        '''Return the complete dict of the torrent, ready to be bencoded and saved. Read-only.'''
        ret: dict[str, Any] = {}
        if annc := self.announce: ret['announce'] = annc
        if alst := self.announce_list: ret['announce-list'] = alst
        if comm := self.comment: ret['comment'] = comm
        if date := self.creation_date: ret['creation date'] = date
        if who := self.created_by: ret['created by'] = who
        if enc := self.encoding: ret['encoding'] = enc
        ret['info'] = self.info_dict
        ret['hash'] = self.hash
        return ret

    #* -----------------------------------------------------------------------------------------------------------------
    #* Property setters and editors
    #* -----------------------------------------------------------------------------------------------------------------

    def addTracker(self, urls: str|Iterable[str], top=True):
        '''
        Add one or more trackers.

        Arguments:
        urls: one or more trackers in one string or an iterable of strings.
            The function will deduplicate automatically.
        top: bool: True: whether to place the added tracker to the top.
        '''
        urls = [urls] if isinstance(urls, str) else list(urls)
        assert all(urls), 'Tracker url cannot be empty.'
        assert all(isinstance(url, str) for url in urls), 'All supplied tracker urls must be str.'
        self._meta.trackers = list(set(urls + self._meta.trackers)) if top else list(set(self._meta.trackers + urls))

    def setTracker(self, urls: str|Iterable[str]):
        '''
        Set tracker list with the given one or more urls, dropping all existing ones.

        Argument:
        urls: one or more trackers in one string or an iterable of strings.
            The function will deduplicate automatically.
        '''
        urls = [urls] if isinstance(urls, str) else list(urls)
        assert all(urls), 'Tracker url cannot be empty.'
        assert all(isinstance(url, str) for url in urls), 'All supplied tracker urls must be str.'
        self._meta.trackers = list(set(urls))

    def rmTracker(self, urls: str|Iterable[str]):
        '''
        Remove one or more trackers from the tracker list.

        Arguments:
        urls: one or more trackers in one string or an iterable of strings.
        '''
        urls = set((urls, )) if isinstance(urls, str) else set(urls)
        assert all(urls), 'Tracker url cannot be empty.'
        assert all(isinstance(url, str) for url in urls), 'All supplied tracker url must be str.'
        self._meta.trackers = list(set(self._meta.trackers) - urls)

    def setComment(self, comment: str):
        '''
        Set the comment message.

        Argument:
        comment: The comment message as str.
        '''
        assert isinstance(comment, str), 'Comment must be str.'
        self._meta.comment = comment

    def setCreator(self, creator):
        '''
        Set the creator of the torrent.

        Argument:
        creator: The str of the creator.
        '''
        assert isinstance(creator, str), 'Creator must be str.'
        self._meta.creator = creator

    def setDate(self, date: int|float|str|time.struct_time|Iterable[int], format: Optional[str] = None):
        '''
        Set the time.

        Argument:
        date: accepts multiple formats:
            if int or float, it must be the elapsed seconds since 1970-1-1;
            if time.struct_time or interable of int, it must be the time tuple;
            if str, it must be a valid date string that can be parsed by `time.strptime()` or `dateutil.parser.parse()`:
                note that if `dateutil` is not installed, you must specify a `format` in `strptime()` format.
        '''
        if isinstance(date, (int, float)):
            self._meta.date = int(date)
        elif isinstance(date, str):
            if format:
                self._meta.date = int(time.mktime(time.strptime(date, format)))
            elif HAS_DATEUTIL:
                self._meta.date = int(dateutil.parser.parse(date).timestamp())
            else:
                raise ValueError('You must install `python-dateutil` or specify a date format for str date.')
        elif isinstance(date, time.struct_time):
            self._meta.date = int(time.mktime(date))
        elif isinstance(date, Iterable) and (_date := list(date)) and all(isinstance(i, int) for i in _date):
            self._meta.date = int(time.mktime(time.struct_time(_date)))
        else:
            raise ValueError('The supplied date is not understood.')

    def setEncoding(self, enc: str):
        '''
        Set the encoding for text.

        Argument:
        enc: The encoding, must be a valid one in python.
        '''
        assert isinstance(enc, str), 'Encoding must be str.'
        codecs.lookup(enc)  # will raise LookupError if this encoding not exists
        self._meta.encoding = enc  # respect the encoding str supplied by user

    def setName(self, name: str):
        '''
        Set a new root name.

        Argument:
        name: The new root name.
        '''
        assert isinstance(name, str), 'Torrent name must be str.'
        assert name, 'Torrent name cannot be empty.'
        assert not any(c in name for c in r'\/:*?"<>|'), 'Torrent name contains invalid character.'
        self._info.name = name

    def setPieceLength(self, size: int, strict: bool = True):
        '''
        Set torrent piece size.
        Note that changing piece size to a different value will clear the existing torrent piece hash.
        Exception will be raised when the new piece size looks strange:
        1. the piece size divided by 16KiB does not obtain a power of 2.
        2. the piece size is beyond the range [256KiB, 32MiB].
        Piece size smaller than 16KiB is never allowed.

        Argument:
        size: the piece size in bytes
        strict: bool=True, whether to allow uncommon piece size and bypass exceptions
        '''
        assert isinstance(size, int), 'Piece size must be int.'
        assert isinstance(strict, bool), 'Check must be bool.'
        assert size >= 16384, 'Piece size must be larger than 16KiB.'
        if strict and size < 262144: raise PieceSizeTooSmall()
        if strict and size > 33554432: raise PieceSizeTooLarge()
        if strict and math.log2(size / 262144) % 1: raise PieceSizeUncommon()
        if size != self._info.piece_length:  # changing piece size will clear existing hash
            self._info.piece_length = size
            self._info.pieces = b''

    def setPrivate(self, private: bool|int):
        '''
        Set torrent to private or not.

        Argument:
        private: Any value that can be converted to `bool` and then set to private torrent if `True`.
        '''
        self._info.private = int(bool(private))

    def setSource(self, src: str):
        '''
        Set the source message.

        Argument:
        src: The message text that can be converted to `str`.
        '''
        assert isinstance(src, str), 'Source must be str.'
        self._info.source = str(src)

    def set(self, **metadata: Any):
        '''
        Set metadata with flexible key aliases.

        All aliases are case-insensitive.
        Only ASCII letters and digits are used to find the key e.g. `dA_t e` => `date`.

        #! the aliases are subject to change in future versions.

        Supported aliases: (most common ones have one-char shortcut)

            tracker: t|tl|trackers|tl|tlist|trackerlist|announce|announces|announcelist|alist
            comment: c|comm|comments
            creator: b|by|createdby|creator|tool|creatingtool|maker|madeby
            date: d|time|second|seconds|creationdate|creationtime|creatingdate|creatingtime
            encoding: e|enc|encoding|codec
            name: n|name|torrentname
            piece size: ps|pl|psz|psize|piecesize|piecelength
            private: p|priv|pt|pub|public #! note that (pub|public) give reverse result
            source: s|src
            filelist: fl|flist
            size: ssz|sourcesize|sourcesz
            torrentsize: tsz|torrentsize|torrentsz
            numpieces: np|numpiece
            numfiles: nf|numfile|numfiles
            hash: th|torrenthash|sha1
            magnet: magnetlink|magneturl
        '''
        for key, value in metadata.items():
            match key:
                case 't'|'tracker'|'trackers'|'tl'|'tlist'|'trackerlist'|'announce'|'announces'|'announcelist'|'alist':
                    self.setTracker(value)
                case 'comment'|'c'|'comm'|'comments':
                    self.setComment(value)
                case 'creator'|'b'|'by'|'createdby'|'creator'|'tool'|'creatingtool'|'maker'|'madeby':
                    self.setCreator(value)
                case 'date'|'time'|'second'|'seconds'|'creationdate'|'creationtime'|'creatingdate'|'creatingtime':
                    self.setDate(value)
                case 'encoding'|'e'|'enc'|'encoding'|'codec':
                    self.setEncoding(value)
                case 'name'|'n'|'name'|'torrentname':
                    self.setName(value)
                case 'ps'|'pl'|'psz'|'psize'|'piecesize'|'piecelength':
                    self.setPieceLength(value)
                case 'private'|'p'|'priv'|'pt'|'pub'|'public':
                    self.setPrivate(value)
                case 'source'|'s'|'src':
                    self.setSource(value)
                case _:
                    raise KeyError(f'Unknown key: {key}')

    #* -----------------------------------------------------------------------------------------------------------------
    #* Input/output operations
    #* -----------------------------------------------------------------------------------------------------------------

    def read(self, tpath: str|pathlib.Path):
        '''Read everything from the template, i.e. copy the torrent file.
        Note that this function will clear all existing properties.

        Argument:
        tpath: the path to the torrent.'''

        tpath = pathlib.Path(tpath)
        if not tpath.is_file():
            raise FileNotFoundError(f"The supplied '{tpath}' does not exist.")
        _torrent_dict: Any = bdecode(tpath.read_bytes())
        if not isinstance(_torrent_dict, dict):
            raise TypeError(f"The supplied '{tpath}' contains no valid content.")

        fulldict: dict = _torrent_dict
        # we need to know the encoding first
        encoding = fulldict.get(b'encoding', b'UTF-8').decode('UTF-8')
        self.setEncoding(encoding)

        # tracker list
        trackers: list[bytes] = []
        trackers += [announce] if (announce := fulldict.get(b'announce')) else []
        trackers += fulldict.get(b'announce-list', [])
        self.setTracker(url.decode(encoding) for url in trackers)
        self.setComment(fulldict.get(b'comment', b'').decode(encoding))
        self.setCreator(fulldict.get(b'created by', b'').decode(encoding))
        self.setDate(fulldict.get(b'creation date', 0))

        infodict: dict = fulldict.get(b'info', {})
        self.setName(fulldict.get(b'name', b'').decode(encoding))
        self.setPieceLength(infodict.get(b'piece length', 0), strict=False)
        self.setSource(infodict.get(b'source', b'').decode(encoding))
        self.setPrivate(infodict.get(b'private', 0))

        files = infodict.get(b'files', [])  # list
        length = infodict.get(b'length', 0)  # int
        pieces = infodict.get(b'pieces', b'')  # str

        self._srcsha1_byt = pieces
        if length and not files:
            self._srcpath_lst = [pathlib.Path('.')]
            self._srcsize_lst = [length]
        elif not length and files:
            fsize_list = []
            fpath_list = []
            for file in files:
                fsize_list.append(file[b'length'])
                fpath_list.append(pathlib.Path().joinpath(*map(methodcaller('decode', encoding), file[b'path'])))
            self._srcsize_lst = fsize_list
            self._srcpath_lst = fpath_list
        else:
            raise ValueError('Unexpected error in handling source files structure.')

    def readMetadata(
        self,
        tpath: str|pathlib.Path,
        include_key: Optional[str|Iterable[str]] = None,
        exclude_key: Optional[str|Iterable[str]] = None
        ):
        '''
        Unlike `read()`, this only loads and overwrites selected properties:
            trackers, comment, created_by, creation_date, encoding, source

        Arguments:
        tpath: the path to the torrent
        `include_key`: str or set of str, only these keys will be copied
            keys: {trackers, comment, created_by, creation_date, encoding, source} (default=all)
        `exclude_key`: str or set of str, these keys will not be copied (override `include_key`)
            keys: {trackers, comment, created_by, creation_date, encoding, source} (default='source')
        '''
        if not (tpath := pathlib.Path(tpath)).is_file():
            raise FileNotFoundError(f"The supplied torrent file '{tpath}' does not exist.")

        key_set = {'tracker', 'comment', 'created_by', 'creation_date', 'encoding', 'source'}
        include_key = {include_key} if isinstance(include_key, str) else (set(include_key) if include_key else key_set)
        exclude_key = {exclude_key} if isinstance(exclude_key,
                                                    str) else (set(exclude_key) if exclude_key else {'source'})
        if (not include_key.issubset(key_set)) or (not exclude_key.issubset(key_set)):
            raise KeyError('Invalid key supplied.')

        template = Torrent()
        template.read(tpath)
        for key in include_key.difference(exclude_key):
            if key == 'tracker':
                self.addTracker(template.tracker_list)
                continue
            elif key == 'comment' and template.comment:
                self.comment = template.comment
                continue
            elif key == 'created_by' and template.created_by:
                self.created_by = template.created_by
                continue
            elif key == 'creation_date' and template.creation_date:
                self.creation_date = template.creation_date
                continue
            elif key == 'encoding' and template.encoding:
                self.encoding = template.encoding
                continue
            elif key == 'source' and template.source:
                self.source = template.source
                continue
            raise RuntimeError('Loop not correctly continued.')

    def load(self, spath, keep_name=False, show_progress=False):
        '''Load new file list and piece hash from the Source PATH (spath).

        The following torrent keys will be overwritten on success:
            files, name (may be preserved by `keep_name=True`), pieces

        Arguments:
        spath: path-like objects, the source path to be loaded
        keep_name: bool=False, whether to keep the old torrent name
        show_progress: bool=False, whether to show a progress bar during loading, maybe removed in the future
        '''
        # argument handler
        spath = pathlib.Path(spath)
        if not spath.exists():
            raise FileNotFoundError(f"The supplied '{spath}' does not exist.")
        keep_name = bool(keep_name)
        show_progress = bool(show_progress)

        fpaths = [spath] if spath.is_file() else sorted(filter(methodcaller('is_file'), spath.rglob('*')))
        fpath_list = [fpath.relative_to(spath) for fpath in fpaths]
        fsize_list = [fpath.stat().st_size for fpath in fpaths]
        if sum(fsize_list):
            if show_progress:  # TODO: stdout is dirty in core class method and should be moved out in the future
                sha1 = b''
                piece_bytes = bytes()
                pbar1 = tqdm.tqdm(
                    total=sum(fsize_list), desc='Size', unit='B', unit_scale=True, ascii=True, dynamic_ncols=True
                    )
                pbar2 = tqdm.tqdm(total=len(fsize_list), desc='File', unit='', ascii=True, dynamic_ncols=True)
                for fpath in fpaths:
                    with fpath.open('rb', buffering=0) as fobj:
                        while (read_bytes := fobj.read(self.piece_length - len(piece_bytes))):
                            piece_bytes += read_bytes
                            if len(piece_bytes) == self.piece_length:
                                sha1 += _hash(piece_bytes)
                                piece_bytes = bytes()
                            pbar1.update(len(read_bytes))
                        pbar2.update(1)
                sha1 += _hash(piece_bytes) if piece_bytes else b''
                pbar1.close()
                pbar2.close()
            else:  # not show progress bar
                sha1 = b''
                piece_bytes = bytes()
                for fpath in fpaths:
                    with fpath.open('rb', buffering=0) as fobj:
                        while (read_bytes := fobj.read(self.piece_length - len(piece_bytes))):
                            piece_bytes += read_bytes
                            if len(piece_bytes) == self.piece_length:
                                sha1 += _hash(piece_bytes)
                                piece_bytes = bytes()
                sha1 += _hash(piece_bytes) if piece_bytes else b''
        else:
            raise EmptySourceSize()

        # Everything looks good, let's update internal parameters
        self.name = self.name if keep_name else spath.name
        self._srcpath_lst = fpath_list
        self._srcsize_lst = fsize_list
        self._srcsha1_byt = sha1

    def write(self, tpath, overwrite=False):
        '''Save the torrent to file.

        Arguments:
        tpath: path-like object, the path to save the torrent.
            If supplied an existing dir, it will be saved under that dir.
        overwrite: bool=False, whether to overwrite if the target file already exists.
        '''
        tpath = pathlib.Path(tpath)
        overwrite = bool(overwrite)
        if (error := self.check()):
            raise TorrentNotReady(f"The torrent is not ready to be saved: {error}.")

        fpath = tpath.joinpath(f"{self.name}.torrent") if tpath.is_dir() else tpath
        if fpath.is_file() and not overwrite:
            raise FileExistsError(f"The target '{fpath}' already exists.")
        else:
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_bytes(bencode(self.torrent_dict, self.encoding))

    def verify(self, spath):
        '''
        Verify external source files with the internal torrent.

        Argument:
        path: the path to source files.

        Return:
        The piece index from 0 that failed to hash
        '''
        spath = pathlib.Path(spath)
        if not spath.exists():
            raise FileNotFoundError(f"The source path '{spath}' does not exist.")
        if (error := self.check()):
            raise TorrentNotReady(f"The torrent is not ready for verification.")

        if self.num_files == 1:
            if spath.is_file() and spath.name == self.name:
                spath = spath
            elif spath.is_dir():
                raise IsADirectoryError(f"Expect a single file, not a directory '{spath}'.")
            else:
                raise RuntimeError('Unexpected Error.')
        elif self.num_files > 1:
            if spath.is_file():
                raise NotADirectoryError(f"Expect a directory, not a single file '{spath}'.")
            elif spath.is_dir() and spath.name == self.name:
                spath = spath
            else:
                raise RuntimeError('Unexpected Error.')
        else:
            raise RuntimeError('Unexpected Error.')

        piece_bytes = bytes()
        piece_idx = 0
        piece_error_list = []
        for finfo in self.file_list:
            fsize = finfo['size']
            fpath = finfo['path']
            dest_fpath = spath.joinpath(*fpath)
            if dest_fpath.is_file():
                read_quota = min(fsize, dest_fpath.stat().st_size)  # we only need to load the smaller file size
                with dest_fpath.open('rb', buffering=0) as dest_fobj:
                    while (read_bytes := dest_fobj.read(min(self.piece_length - len(piece_bytes), read_quota))):
                        piece_bytes += read_bytes
                        if len(piece_bytes) == self.piece_length:  # whole piece loaded
                            if _hash(piece_bytes) != self.pieces[20 * piece_idx:20*piece_idx + 20]:  # sha1 mismatch
                                piece_error_list.append(piece_idx)
                            piece_idx += 1  # whole piece loaded, piece index increase
                            piece_bytes = bytes()  # whole piece loaded, clear existing bytes
                        if (read_quota := read_quota - len(read_bytes)) == 0:  # smaller file read
                            # we need to fill remaining bytes
                            piece_bytes += b'\0' * diff if (diff := fsize - dest_fpath.stat().st_size) > 0 else b''
                            break
            else:  # the file does not exist
                size = len(piece_bytes) + fsize
                n_empty_piece, piece_blank_shift = divmod(size, self.piece_length)
                piece_bytes = b'\0' * piece_blank_shift  # it should be OK to just replace existing piece_bytes by \0
                for _ in range(n_empty_piece):
                    piece_error_list.append(piece_idx)
                    piece_idx += 1
        if piece_bytes and _hash(piece_bytes) != self.pieces[20 * piece_idx:20*piece_idx + 20]:  # remainder
            piece_error_list.append(piece_idx)

        return piece_error_list

    '''-----------------------------------------------------------------------------------------------------------------
    Other helper properties and members
    -----------------------------------------------------------------------------------------------------------------'''

    def check(self):
        '''Return the problems within the torrent.'''
        ret = []
        if not self.name:
            ret.append('Torrent name has not been set.')
        if not self.piece_length:
            ret.append('Piece size cannot be 0.')
        if not self.file_list:
            ret.append('There is no source file within the torrent.')
        if not self.pieces:
            ret.append('Piece hash is empty.')
        if not self.size:
            ret.append('Torrent size is 0.')
        if self.piece_length * (self.num_pieces - 1) > self.size:
            ret.append('Too many pieces for content size.')
        if self.piece_length * self.num_pieces < self.size:
            ret.append('Too less pieces for content size.')
        try:
            codecs.lookup(self.encoding)
        except LookupError as e:
            ret.append(f"Invalid encoding {self.encoding}.")
        try:
            bencode(self.torrent_dict, self.encoding)
        except Exception as e:
            ret.append(f"Torrent bencoding failed ({e}).")
        return ret

    def index(self, path, /, num=1):
        '''Given filename, return its piece index.

        Arguments:
        filename: str, the filename to find.
            Path parts are matched backward. e.g. 'b/c' will match 'a/b/c' instead of 'b/c/a'.
        num: int=1, stop search when this number of files are found (find all when num <= 0).

        Return:
        A list of 3-element tuple of (path, start-index, end-index)
            Indexed in python style, from 0 to len-1, and [m, n+1] for items from m to n
        '''
        fparts = pathlib.Path(path).parts
        num = int(num) if int(num) > 0 else 0
        if self.check():
            raise TorrentNotReady('Torrent is not ready for indexing.')

        ret = []
        loaded_size = 0
        for finfo in self.file_list:
            fsize = finfo['size']
            fpath = finfo['path']
            n_shorter = min(len(fpath), len(fparts))
            if fpath[:-n_shorter - 1:-1] == fparts[:-n_shorter - 1:-1]:
                ret.append([
                    os.path.join(self.name, *fpath),
                    math.floor(loaded_size / self.piece_length),
                    math.ceil((loaded_size+fsize) / self.piece_length)
                    ])
                if (num := num - 1) == 0:
                    break
            loaded_size += fsize

        return ret

    def __getitem__(self, key: int|slice) -> list[str]:
        '''Give 0-indexed piece index or slice, return files associated with the piece or piece range.'''

        if not isinstance(key, (int, slice)):
            raise TypeError(f"Expect int, not {key.__class__}.")

        if self.check():
            raise TorrentNotReady('Torrent is not ready to for item getter.')

        if isinstance(key, int):
            lsize = self.piece_length * (key if key >= 0 else self.num_pieces + key)
            hsize = lsize + self.piece_length
        elif isinstance(key, slice):
            if key.step and key.step != 1: warnings.warn('Step is not supported in slice.')
            size1 = self.piece_length * (key.start if key.start >= 0 else self.num_pieces + key.start)
            size2 = self.piece_length * (key.stop if key.stop >= 0 else self.num_pieces + key.stop)
            lsize, hsize = (size1, size2) if size1 < size2 else (size2, size1)
            hsize = hsize + self.piece_length if lsize == hsize else hsize
        else:
            raise RuntimeError('Unexpected Error. Please file a bug report.')

        ret = []
        total_size = 0
        for file_info in self.file_list:
            path = file_info['path']
            size = file_info['size']
            total_size += size
            if total_size > lsize:
                ret.append(os.pathsep.join(path))
            if total_size >= hsize:
                return ret

        raise RuntimeError('Unexpected Error. Please file a bug report.')
