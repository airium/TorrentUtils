import re
import sys
import math
import time
import json
import codecs
import urllib
import shutil
import string
import hashlib
import pathlib
import warnings
import argparse

from operator import methodcaller
from itertools import chain
from functools import partial
from collections import namedtuple




'''=====================================================================================================================
Helper Error Types
====================================================================================================================='''


class PieceSizeTooSmall(ValueError):
    pass


class PieceSizeUncommon(ValueError):
    pass




'''=====================================================================================================================
Public Helper Functions
====================================================================================================================='''


def bencode(obj, enc:str='UTF-8') -> bytes:
    '''Bencode objects. Modified from <https://github.com/utdemir/bencoder>.'''

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
        raise TypeError(f"Expect int, bytes, list or dict; not {obj}:{type(obj)}.")

    return ret


def bdecode(s:(bytes, str), encoding='ascii'):
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
            raise ValueError("Malformed input.")

    s = s.encode(encoding) if isinstance(s, str) else s
    ret, rest = decode_first(s)
    if rest:
        raise ValueError("Malformed input.")

    return ret


def hash(bchars:bytes, /) -> bytes:
    '''Return the sha1 hash for the given bytes.'''
    if isinstance(bchars, bytes):
        hasher = hashlib.sha1()
        hasher.update(bchars)
        return hasher.digest()
    else:
        raise TypeError(f"Expect bytes, not {type(bchars)}.")


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


class Torrent():


    def __init__(self, **kwargs):
        '''The function basically creates the instance of an empty torrent.
        Optionally, you can supply arbitrary arguments supported by `self.set()` to initialise some metadata.

        Currently, this class only supports most regular torrent file specifications.
        The first level in a torrent's dict can have the following keys:
            `announce`, `announce-list`, `comment`, `created by`, `creation data`, `encoding`, `info`
        And in the `info` key:
            `files`, `name`, `piece length`, `pieces`, `private`, `source`
        This means attributes other than these will be lost through the class.
        '''
        # internal attributes
        self._tracker_list = []                     # for `announce` and `announce-list`
        self._comment_str = ''                      # for `comment`
        self._creator_str = ''                      # for `created by`
        self._datesec_int = 0                       # for `creation date`
        self._encoding_str = 'UTF-8'                # for `encoding`
        self._content_fpath_list = []               # for `files`
        self._content_fsize_list = []               # for `length`
        self._torrent_name_str = ''                 # for `name`
        self._piece_size_int = 4096 << 10           # for `piece length`
        self._content_sha1 = b''                    # for `pieces`
        self._private_int = 0                       # for `private`
        self._source_str = ''                       # for `source`

        # allow partial metadata initialisation
        self.set(**kwargs)


    '''-----------------------------------------------------------------------------------------------------------------
    Baisc properties that mimic keys in an actual torrent, providing a straightforward access (except `info`).

    If the return value == `False`, the key does not exist. Some allow value assignment.
    -----------------------------------------------------------------------------------------------------------------'''


    @property
    def announce(self) -> str:
        '''The first tracker's url. Settable, which sets the first url.'''
        return self._tracker_list[0] if self._tracker_list else ''


    @property
    def announce_list(self) -> list:
        '''All tracker urls if more than 2, otherwise empty. Settable, which sets the whole tracker list.'''
        return self._tracker_list if len(self._tracker_list) >= 2 else []


    @property
    def comment(self) -> str:
        '''The message to be displayed in various clients. Settable.'''
        return self._comment_str


    @property
    def created_by(self) -> str:
        '''Who created the torrent. Settable.'''
        return self._creator_str


    @property
    def creation_date(self) -> int:
        '''Torrent creation time, counted as the number of second since 1970-01-01. Settable.'''
        return self._datesec_int


    @property
    def encoding(self) -> str:
        '''How text and path are encoded. Settable.'''
        return self._encoding_str


    @property
    def files(self) -> list:
        '''List of list of file size and path parts if more than 2 files (repel `length`). Read-only.'''
        return list([fsize, fpath.parts] for fsize, fpath in zip(self._content_fsize_list, self._content_fpath_list)) \
               if len(self._content_fpath_list) >= 2 else []


    @property
    def length(self) -> int:
        '''The size of the file in bytes if only 1 file (repel `files`). Read-only.'''
        return self._content_fsize_list[0] if len(self._content_fsize_list) == 1 else 0


    @property
    def name(self) -> str:
        '''The root dir name or the only filename. Settable.'''
        return self._torrent_name_str


    @property
    def piece_length(self) -> int:
        '''The piece size in bytes. Settable.'''
        return self._piece_size_int


    @property
    def pieces(self) -> str:
        '''The sha1 hash of pieces. Read-only.'''
        return self._content_sha1


    @property
    def private(self) -> int:
        '''Private torrent or not. Settable.'''
        return 1 if self._private_int else 0


    @property
    def source(self) -> str:
        '''A special message changing torrent hash. Settable.'''
        return self._source_str


    '''-----------------------------------------------------------------------------------------------------------------
    Useful public torrent properties
    -----------------------------------------------------------------------------------------------------------------'''


    @property
    def tracker_list(self) -> list:
        '''Unlike `announce(_list)`, this always returns the full tracker list unconditionally. Settable.'''
        return self._tracker_list


    @property
    def file_list(self) -> list:
        '''Unlike `files` and `length`, this always returns the full file size and paths unconditionally. Read-only'''
        return list([fsize, fpath.parts] for fsize, fpath in zip(self._content_fsize_list, self._content_fpath_list))


    @property
    def torrent_size(self) -> int:
        '''Return the size of the torrent file itself (not content). Read-only.'''
        return len(bencode(self.torrent_dict))


    @property
    def content_size(self) -> int:
        '''Return the total size of content files in the torrent. Read-only.'''
        return sum(self._content_fsize_list)


    @property
    def num_pieces(self) -> int:
        '''The total number of pieces within the torrnet'''
        return len(self._content_sha1) // 20


    @property
    def info_dict(self) -> dict:
        '''Return the `info` dict part of the torrent that affects hash. Read-only.'''
        info_dict = {}
        if self.length:
            info_dict[b'length'] = self.length
        if self.files:
            info_dict[b'files'] = []
            for fsize, fpath_parts in self.files:
                info_dict[b'files'].append({b'length': fsize, b'path': fpath_parts})
        if self.name:
            info_dict[b'name'] = self.name
        if self.piece_length:
            info_dict[b'piece length'] = self.piece_length
        if self.pieces:
            info_dict[b'pieces'] = self.pieces
        if self.private:
            info_dict[b'private'] = self.private
        if self.source:
            info_dict[b'source'] = self.source
        return info_dict


    @property
    def torrent_dict(self) -> bytes:
        '''Everthing of the torrent as a dict ready to be bencoded. Read-only.'''
        torrent_dict = {b'info':{}}

        # keys that not impact torrent hash
        if self.announce:
            torrent_dict[b'announce'] = self.announce
        if self.announce_list:
            torrent_dict[b'announce-list'] = list([url] for url in self.announce_list)
        if self.comment:
            torrent_dict[b'comment'] = self.comment
        if self.creation_date:
            torrent_dict[b'creation date'] = self.creation_date
        if self.created_by:
            torrent_dict[b'created by'] = self.created_by
        if self.encoding:
            torrent_dict[b'encoding'] = self.encoding

        # keys that impact torrent hash
        torrent_dict[b'info'] = self.info_dict

        # additional key to store the original hash
        torrent_dict[b'hash'] = self.hash

        return torrent_dict


    @property
    def hash(self) -> str:
        '''Return the torrent hash at the moment. Read-only.'''
        return hash(bencode(self.info_dict)).hex()


    @property
    def magnet(self) -> str:
        '''Return the magnet string of the torrent. Read-only.'''
        ret = f"magnet:?xt=urn:btih:{self.hash}"
        if self.name:
            ret += f"&dn={urllib.parse.quote(self.name)}"
        if self.content_size:
            ret += f"&xl={self.content_size}"
        for url in self.tracker_list:
            ret += f"&tr={urllib.parse.quote(url)}"
        return ret


    '''-----------------------------------------------------------------------------------------------------------------
    Public member functions for manipulation, providing basic operations
    -----------------------------------------------------------------------------------------------------------------'''


    def addTracker(self, urls, /, top=True):
        '''Add trackers

        Arguments:
        urls: the tracker urls, can be a single string or an iterable of strings
            Note that duplicated tracker will be automatically removed.
        top: place added trackers to the top if True, otherwise bottom (default=True)
        '''
        urls = [urls] if isinstance(urls, str) else list(urls)
        if top:
            for url in urls[::-1]:
                try:
                    idx = self._tracker_list.index(url)
                except ValueError: # not found, add it
                    self._tracker_list.insert(0, url)
                else: # found, remove existing and push to top
                    self._tracker_list.pop(idx)
                    self._tracker_list.insert(0, url)
        else:
            for url in urls:
                try:
                    idx = self._tracker_list.index(url)
                except ValueError: # not found, add it
                    self.append(url)
                else: # found, no need to update its position
                    continue


    def setTracker(self, urls, /):
        '''Set tracker list with the given urls, dropping all existings ones.


        Argument:
        urls: the tracker urls, can be a single string or an iterable of strings.
            Note that duplicated tracker will be automatically removed.
        '''
        urls = [urls] if isinstance(urls, str) else list(urls)
        self._tracker_list.clear()
        self.addTracker(urls) # `addTracker() can deduplicate`

    @announce.setter
    def announce(self, url):
        assert isinstance(url, str), f"expect str, not {url.__class__.__name__}"
        self.setTracker([url] + self.announce_list)

    @announce_list.setter
    def announce_list(self, urls):
        self.setTracker(urls)

    @tracker_list.setter
    def tracker_list(self, urls):
        self.setTracker(urls)


    def rmTracker(self, urls, /):
        '''Remove tracker from current tracker list

        Arguments:
        urls: the tracker urls, can be a single string or an iterable of strings
        '''
        urls = {urls} if isinstance(urls, str) else set(urls)
        for url in urls:
            try:
                idx = self._tracker_list.index(url)
            except ValueError:
                continue # not found, skip
            else:
                self._tracker_list.pop(idx) # found, remove it


    def setComment(self, comment, /):
        '''Set the comment message

        Argument:
        comment: the comment message as str'''
        self._comment_str = str(comment)

    @comment.setter
    def comment(self, chars):
        self.setComment(chars)


    def setCreator(self, creator, /):
        '''Set the creator of the torrent

        Argument:
        creator: the str of the creator'''
        self._creator_str = str(creator)

    @created_by.setter
    def created_by(self, creator):
        self.setCreator(creator)


    def setDate(self, date, /):
        '''Set the time.

        Argument:
        time: second since 1970-1-1 if int or float, `time.strptime()` format if str,
              time tuple or `time.struct_time` otherwise.
        '''
        t = type(date)
        if t in {int, float}:
            self._datesec_int = int(date)
        elif t is str:
            self._datesec_int = int(time.mktime(time.strptime(date)))
        elif t is time.struct_time:
            self._datesec_int = int(time.mktime(date))
        elif len(t) == 9:
            self._datesec_int = int(time.mktime(tuple(date)))
        else:
            raise ValueError('Supplied date is not understood.')

    @creation_date.setter
    def creation_date(self, date):
        self.setDate(date)


    def setEncoding(self, enc, /):
        '''Set the encoding for non-ascii characters

        Argument:
        enc: the encoding, must be a valid encoding for python
        '''
        codecs.lookup(enc) # will raise LookupError if this encoding not exists
        self._encoding_str = enc # respect the encoding str supplied by user


    @encoding.setter
    def encoding(self, enc):
        self.setEncoding(enc)


    def setName(self, name, /):
        name = str(name)
        if not name:
            raise ValueError('Name must not be empty.')
        if not all([False if (char in name) else True for char in r'\/:*?"<>|' ]):
            raise ValueError('Invalid torrent name.')
        self._torrent_name_str = name

    @name.setter
    def name(self, name):
        self.setName(name)


    def setPieceLength(self, size, no_check=False):
        '''Set torrent piece size
        Note that changing piece size to a different value will clear existing torrent piece hash
        Under interactive scenario, it may prompt to ask the user when the new piece size looks strange:
        1. the piece size divided by 16KiB does not obtain a power of 2.
        2. the piece size is beyond the range [256KiB, 32MiB]

        Argument:
        size: int, the piece size in bytes
        no_check: bool=False, whether to allow uncommon piece size
        '''
        size = int(size)
        no_check = bool(no_check)
        if size == self._piece_size_int: # we have nothing to do
            return

        if size < 16384: # piece size must be larger than 16KiB
            raise PieceSizeTooSmall()
        if (not no_check) and ((math.log2(size / 262144) % 1) or (size < 262144) or (size > 33554432)):
            raise PieceSizeUncommon()
        if size != self._piece_size_int: # changing piece size will clear existing hash
            self._content_sha1 = bytes()

        self._piece_size_int = size


    @piece_length.setter
    def piece_length(self, size):
        self.setPieceLength(size)


    def setPrivate(self, private):
        '''Set torrent private or not

        Argument:
        private: any value that can be converted to `bool`; private torrent if `True`
        '''
        self._private_int = int(bool(private))

    @private.setter
    def private(self, private):
        self.setPrivate(private)


    def setSource(self, src, /):
        '''Set the source message

        Argument:
        src: the message text that can be converted to `str`
        '''
        self._source_str = str(src)

    @source.setter
    def source(self, src):
        self.setSource(src)


    def set(self, **metadata):
        '''This function allows setting metadata with more flexible key aliases:

            tracker: t, tr, tracker, trackers, trackerlist, announce, announces, announcelist
            comment: c, comm, comment, comments
            creator: b, by, createdby, creator, tool, creatingtool
            date: d, date, time, second, seconds, creationdate, creationtime, creatingdate, creatingtime
            encoding: e, enc, encoding, codec
            name: n, name, torrentname
            piece size: ps, pl, piecesize, piecelength
            private: p, private, privatetorrent, torrentprivate, pub, public, publictorrent, torrentpublic
            source: s, src, source

        All alias are case-insensitive.
        All whitespaces and underscores will be stripped (e.g. dA_te == date).
        If equivalent keys are supplied multiple times, the last one takes effect.
        Note that the values of keys have the same requirement as each backend function.
        '''
        for key, value in metadata.items():
            key = re.sub(r'[\s_]', '', key).lower()
            if key in ('t', 'tr', 'tracker', 'trackers', 'trackerlist', 'announce', 'announces', 'announcelist'):
                self.setTracker(value)
            elif key in ('c', 'comment', 'comments'):
                self.setComment(value)
            elif key in ('b', 'by', 'createdby', 'creator', 'tool', 'creatingtool'):
                self.setCreator(value)
            elif key in ('d', 'date', 'time', 'second', 'seconds', 'creationdate', 'creationtime', 'creatingdate', 'creatingtime'):
                self.setDate(value)
            elif key in ('e', 'enc', 'encoding', 'codec'):
                self.setEncoding(value)
            elif key in ('n', 'name', 'torrentname'):
                self.setName(value)
            elif key in ('ps', 'pl', 'piecesize', 'piecelength'):
                self.setPieceLength(value)
            elif key in ('p', 'private', 'privatetorrent', 'torrentprivate'):
                self.setPrivate(value)
            elif key in ('pub', 'public', 'publictorrent', 'torrentpublic'):
                self.setPrivate(not value)
            elif key in ('s', 'src', 'source'):
                self.setSource(value)
            else:
                raise ValueError(f"Unknown key: {key}.")


    def read(self, path, /):
        '''Load all information from the template. Note that this function will clear all existing keys.'''
        torrent_dict = bdecode(pathlib.Path(path).read_bytes())

        # we need to know encoding first
        encoding = torrent_dict.get(b'encoding', b'UTF-8').decode()                 # str
        # tracker list requires deduplication
        trackers = [torrent_dict[b'announce']] if torrent_dict.get(b'announce') else []
        trackers += list(chain(*torrent_dict[b'announce-list'])) if torrent_dict.get(b'announce-list') else []
        trackers = list(map(methodcaller('decode', encoding), trackers))   # bytes to str
        trackers = list(dict.fromkeys(trackers))                                    # ordered deduplicate
        # other keys
        comment = torrent_dict.get(b'comment', b'').decode(encoding)                # str
        created_by = torrent_dict.get(b'created by', b'').decode(encoding)          # str
        creation_date = torrent_dict.get(b'creation date', 0)                       # int
        files = torrent_dict.get(b'info').get(b'files', [])                         # list
        length = torrent_dict.get(b'info').get(b'length', 0)                        # int
        name = torrent_dict.get(b'info').get(b'name', b'').decode(encoding)         # str
        piece_length = torrent_dict.get(b'info').get(b'piece length', 0)            # int
        pieces = torrent_dict.get(b'info').get(b'pieces', b'')                      # str
        private = torrent_dict.get(b'info').get(b'private', 0)                      # int
        source = torrent_dict.get(b'info').get(b'source', b'').decode(encoding)     # str

        # everything looks good, now let's write attributes
        self.setTracker(trackers);
        self.setComment(comment);
        self.setCreator(created_by)
        self.setDate(creation_date)
        self.setEncoding(encoding)
        self.setName(name)
        self.setPieceLength(piece_length, no_check=True)
        self.setPrivate(private)
        self.setSource(source)

        self._content_sha1 = pieces
        if length and not files:
            self._content_fpath_list = [pathlib.Path('.')]
            self._content_fsize_list = [length]
        elif not length and files:
            fsize_list = []
            fpath_list = []
            for file in files:
                fsize_list.append(file[b'length'])
                fpath_list.append(pathlib.Path().joinpath(*map(methodcaller('decode', encoding), file[b'path'])))
            self._content_fsize_list = fsize_list
            self._content_fpath_list = fpath_list
        else:
            raise ValueError('Unexpected error in reading torrent.')


    def readMetadata(self, path, /, include_key={}, exclude_key={'source'}):
        '''Unlike `read()`, this only load and overwrite torrent metadata:
            trackers, comment, created_by, creation_date, encoding, source

        Arguments:
        path: the path to the template torrent
        `include_key`: str or set of str, only these keys will be copied
            keys: {trackers, comment, created_by, creation_date, encoding, source} (default=all)
        `exclude_key`: str or set of str, these keys will not be copied (override `include_key`)
            keys: {trackers, comment, created_by, creation_date, encoding, source} (default='source')
        '''
        key_set = {'tracker', 'comment', 'created_by', 'creation_date', 'encoding', 'source'}

        path = pathlib.Path(path)
        include_key = {include_key} if isinstance(include_key, str) else include_key
        include_key = set(include_key) if include_key else key_set
        exclude_key = {exclude_key} if isinstance(exclude_key, str) else exclude_key
        exclude_key = set(exclude_key)

        assert path.isfile()
        assert include_key.issubset(key_set)
        assert include_key.issubset(key_set)

        template.read(path)
        for key in include_key.difference(exclude_key):
            if key == 'tracker':
                self._tracker_list.addTracker(template.trackers)
                continue
            if key == 'comment' and template.comment:
                self._comment_str = template.comment
                continue
            if key == 'created_by' and template.created_by:
                self._creator_str = template.created_by
                continue
            if key == 'creation_date' and template.creation_date:
                self._datesec_int = template.creation_date
                continue
            if key == 'encoding' and template.encoding:
                self._encoding_str = template.encoding
                continue
            if key == 'source' and template.source:
                self._source_str = template.source
                continue


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
        keep_name = bool(keep_name)
        show_progress = bool(show_progress)

        fpaths = [spath] if spath.is_file() else sorted(filter(methodcaller('is_file'), spath.rglob('*')))
        fpath_list = [fpath.relative_to(spath) for fpath in fpaths]
        fsize_list = [fpath.stat().st_size for fpath in fpaths]
        if sum(fsize_list):
            if show_progress: # TODO: stdout is dirty in core class method and should be moved out
                sha1 = b''
                piece_bytes = bytes()
                pbar = tqdm.tqdm(total=sum(fsize_list), unit='B', unit_scale=True)
                for fpath in fpaths:
                    with fpath.open('rb') as fobj:
                        while (read_bytes := fobj.read(self.piece_length - len(piece_bytes))):
                            piece_bytes += read_bytes
                            if len(piece_bytes) == self.piece_length:
                                sha1 += hash(piece_bytes)
                                piece_bytes = bytes()
                            pbar.update(len(read_bytes))
                sha1 += hash(piece_bytes) if piece_bytes else b''
                pbar.close()
            else: # not show progress bar
                sha1 = b''
                piece_bytes = bytes()
                for fpath in fpaths:
                    with fpath.open('rb') as fobj:
                        while (read_bytes := fobj.read(self.piece_length - len(piece_bytes))):
                            piece_bytes += read_bytes
                            if len(piece_bytes) == self.piece_length:
                                sha1 += hash(piece_bytes)
                                piece_bytes = bytes()
                sha1 += hash(piece_bytes) if piece_bytes else b''
        else:
            raise ValueError(f"The source path '{spath.absolute()}' has a total size of 0.")

        # Everything looks good, let's update internal parameters
        self.name = self.name if keep_name else spath.name
        self._content_fpath_list = fpath_list
        self._content_fsize_list = fsize_list
        self._content_sha1 = sha1




    def write(self, tpath, overwrite=False):
        '''Save the torrent to file.

        Arguments:
        tpath: path-like object, the path to save the torrent.
            If supplied an existing dir, it will be saved under that dir.
        overwrite: bool=False, whether to overwrite if the target file already exists.
        '''
        tpath = pathlib.Path(tpath)
        overwrite = bool(overwrite)
        assert self.isValid(), f"the torrent is not ready to be saved: {self.whyInvalid()}"

        fpath = tpath.joinpath(f"{self.name}.torrent") if tpath.is_dir() else tpath
        if fpath.is_file() and not overwrite:
            raise FileExistsError(f"The target '{fpath}' already exists.")
        else:
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_bytes(bencode(self.torrent_dict))




    def whyInvalid(self):
        '''Return the reason why the torrent is not ready to be saved'''
        ret = []
        if not self.name:
            ret.append('Torrent name has not been set.')
        if not self.file_list:
            ret.append('There is no content file in the torrent.')
        if not self.piece_length:
            ret.append('Piece size cannot be 0.')
        if self.piece_length * (self.num_pieces - 1) > self.content_size:
            ret.append('Too many pieces for content size.')
        if self.piece_length * self.num_pieces < self.content_size:
            ret.append('Too less pieces for content size.')
        try:
            bencode(self.torrent_dict)
        except Exception as e:
            ret.append(f"Torrent bencoding failed ({e}).")
        return ret


    def isValid(self):
        '''check if current internal status is compatible as a torrent'''
        return False if self.whyInvalid() else True


    def whichPieceB(self, path, start=None, end=None):
        '''Return the bytes shift and size for the first found file that matches the filename.

        Arguments:
        filename: the filename to find. Can be a single path or
            Parts of the filename are matched backward. e.g. 'b/c' will match 'a/b/c' instead of 'b/c/a'.
        start: optional, the shift in bytes to start search, default=0
        end: optional, the shift in bytes to stop search, default=self.content_size
            Note that once the file has an intersection with the interval (start, end), the file will be found
        '''
        assert self.isValid(), 'torrent is not ready for file/piece locating'
        st = int(start) if start else 0
        ed = int(end) if end else self.content_size
        assert 0 <= st < ed <= self.content_size, f"invalid interval"

        fparts = pathlib.Path(path).parts
        fst = fed = 0
        for fsize, fpath in self.file_list:
            fst, fed = fed, fed + fsize
            if fed <= st: # the file has not enter the interval
                continue
            if fed > st and fst < ed and fpath[-len(fparts):] == fparts:
                return fst, fed
            if fst >= ed: # the file has left the interval
                break
        raise ValueError('File not found.')


    def whichPieceP(self, path, start=None, end=None):
        '''Return the piece shift and size for the first found file that matches the filename.

        Arguments:
        filename: the filename to find. Can be a single path or
            Parts of the filename are matched backward. e.g. 'b/c' will match 'a/b/c' instead of 'b/c/a'.
        start: optional, the shift in bytes to start search, default=0
        end: optional, the shift in bytes to stop search, default=self.num_piece
            Note that once the file has an intersection with the interval (start, end), the file will be found
        '''
        assert self.isValid(), 'torrent is not ready for file/piece locating'
        st = int(start) if start else 0
        ed = int(end) if end else self.num_pieces
        assert 0 <= st < ed <= self.num_pieces, 'invalid interval'

        return list(s // self.piece_length for s in self.whichPieceB(path, st * self.piece_length, ed * self.piece_length))


    def whichFileB(self, start, end) -> list:
        '''Return the file list between bytes shift [start, end], indexed from 0

        Argument:
        start: the size shift in bytes to start search
        end: optional, the size shift in bytes to end search, default=start+1
        '''
        assert self.isValid(), 'torrent is not ready for file/piece locating'
        st = int(start)
        ed = int(end) + 1
        assert 0 <= st < ed <= self.content_size, 'invalid interval'

        ret = []
        fst = fed = 0
        for fsize, fpath in self.file_list:
            fst, fed = fed, fed + fsize
            if fed <= st: # the file has not enter the interval
                continue
            if fed > st and fst < ed: # the file has intersection with the interval
                ret.append(fpath)
            if fst >= ed: # the file has left the interval
                break

        return ret


    def whichFileP(self, start, end=None) -> list:
        '''Return the file list between piece shift [start, end], indexed from 0

        Argument:
        start: the size shift in pieces to start search
        end: optional, the size shift in pieces to end search, default=start+1
        '''
        assert self.isValid(), 'torrent is not ready for file/piece locating'
        st = int(start)
        ed = int(end) if end else st + 1
        assert 0 <= st < ed <= self.num_pieces, 'invalid interval'

        return self.whichFileB(st * self.piece_length, ed * self.piece_length)


    def verify(self, dest):
        '''Verify if the actual files match existing hash list

        Argument:
        dest: the path to actual files

        Return:
        The piece index from 0 that failed to hash
        '''
        dest = pathlib.Path(dest)
        assert self.isValid(), 'internal status is not ready to be verified'
        assert dest.exists(), 'the verification target does not exists'

        piece_bytes = bytes()
        piece_idx = 0
        piece_error_list = []
        for fsize, fpath in self.file_list:
            dest_fpath = dest.joinpath(*fpath)
            if dest_fpath.is_file():
                read_quota = min(fsize, dest_fpath.stat().st_size) # we only need to load the smaller file size
                with dest_fpath.open('rb') as dest_fobj:
                    while (read_bytes := dest_fobj.read(min(self.piece_length - len(piece_bytes), read_quota))):
                        piece_bytes += read_bytes
                        if len(piece_bytes) == self.piece_length: # whole piece loaded
                            if hash(piece_bytes) != self.pieces[20 * piece_idx : 20 * piece_idx + 20]: # sha1 mismatch
                                piece_error_list.append(piece_idx)
                            piece_idx += 1          # whole piece loaded, piece index increase
                            piece_bytes = bytes()   # whole piece loaded, clear existing bytes
                        if (read_quota := read_quota - len(read_bytes)) == 0: # smaller file read
                            # we need to fill remaining bytes
                            piece_bytes += b'\0' * diff if (diff := fsize - dest_fpath.stat().st_size) > 0 else b''
                            break
            else: # the file does not exist
                size = len(piece_bytes) + fsize
                n_empty_piece, piece_empty_shift = divmod(size, self.piece_length)
                piece_bytes = (b'' if size >= self.piece_length else piece_bytes) + b'\0' * piece_empty_shift
                for _ in range(n_empty_piece):
                    piece_error_list.append(piece_idx)
                    piece_idx += 1
        if piece_bytes and hash(piece_bytes) != self.pieces[piece_idx]: # remainder
            piece_error_list.append(piece_idx)

        return piece_error_list






'''=====================================================================================================================
CLI Class
====================================================================================================================='''


class Main():


    def __init__(self, args):
        self.torrent = Torrent()

        # extract cli config from cli arguments
        self.cfg = self.__pickCliCfg(args)
        # if mode is not specified, infer it from the number of supplied paths
        self.mode = self.__inferMode(args)
        # based on the working mode, pick the most likely torrent and content paths
        self.tpath, self.spath = self.__sortPath(args, self.mode)
        # load json defaults
        self.metadata = self.__loadJson(args, self.mode)
        # extract metadata from cli arguments
        self.metadata = self.__pickMetadata(args, self.mode, self.metadata)


    @staticmethod
    def __pickCliCfg(args):
        cfg = namedtuple('CFG', '     show_prompt       show_progress       with_time_suffix')(
                                 args.show_prompt, args.show_progress, args.with_time_suffix)
        if cfg.show_progress:
            try:
                import tqdm
                global tqdm
            except ImportError:
                print('I: Progress bar won\'t show as it\'s not installed, consider `pip3.8 install tqdm`.')
                cfg._replace(show_progress=False) # tqdm is not installed, so don't use progress bar anyway
        return cfg


    @staticmethod
    def __inferMode(args):
        '''Inferring working mode from the number of paths is limited: some modes cannot be inferred'''
        if args.mode:
            ret = args.mode
        else:
            fpaths = args.fpaths
            if len(fpaths) == 1 and fpaths[0].is_dir():
                ret = 'create'
            elif len(fpaths) == 1 and fpaths[0].is_file() and fpaths[0].suffix.lower() != '.torrent':
                ret = 'create'
            elif len(fpaths) == 1 and fpaths[0].is_file() and fpaths[0].suffix.lower() == '.torrent':
                ret = 'print'
            elif len(fpaths) == 2 and fpaths[0].is_file() and fpaths[0].suffix.lower() == '.torrent':
                ret = 'verify'
            elif len(fpaths) == 2 and fpaths[1].is_file() and fpaths[1].suffix.lower() == '.torrent':
                ret = 'verify'
            else:
                raise ValueError('Failed to infer working mode.')
        return ret


    @staticmethod
    def __sortPath(args, mode):
        '''Based on the working mode, sort out the most proper paths for torrent and content.'''
        fpaths = args.fpaths
        spath = None # Source PATH is the path to the files specified by a torrent
        tpath = None # Torrent PATH is the path to the torrent itself

        # `create` mode requires 1 or 2 paths
        # the first path must be an existing spath
        # the second path is optional and must be tpath if supplied
        if mode == 'create':
            if 1 <= len(fpaths) <= 2:
                if fpaths[0].exists():
                    spath = fpaths[0]
                    tpath = spath.parent.joinpath(f"{spath.name}.torrent") if not fpaths[1:] else (
                            fpaths[1].joinpath(f"{spath.name}.torrent") if fpaths[1].is_dir() else (
                            fpaths[1] if fpaths[1].suffix == '.torrent' else \
                            fpaths[1].parent.joinpath(f"{fpaths[1].name}.torrent")))
                    if spath.is_file() and spath.suffix == '.torrent':
                        print('W: You are likely to create torrent from torrent, which may be unexpected.')
                    if spath == tpath:
                        raise ValueError('Source and torrent path cannot be same.')
                else:
                    raise FileNotFoundError(f"The source '{fpaths[0]}' does not exist.")
            else:
                raise ValueError(f"`create` mode expects 1 or 2 paths, not {len(fpaths)}.")

        # `print` mode requires exactly 1 path
        # the path must be an existing tpath
        elif mode == 'print':
            if len(fpaths) == 1:
                if fpaths[0].is_file() and fpaths[0].suffix == '.torrent':
                    tpath = fpaths[0]
                else:
                    raise FileNotFoundError(f"`print` mode expects a valid torrent path, not {fpaths[0]}.")
            else:
                raise ValueError(f"`print` mode expects exactly 1 path, not {len(fpaths)}.")

        # `verify` mode requires exactly 2 paths
        # the first path must be an existing spath
        # the second path must be an existing tpath
        # the logic goes like "verify spath with tpath", so spath first tpath second
        elif mode == 'verify':
            if len(fpaths) == 2:
                if fpaths[0].exists() and fpaths[1].is_file() and fpaths[1].suffix == '.torrent':
                    spath = fpaths[0]
                    tpath = fpaths[1]
                elif fpaths[1].exists() and fpaths[0].is_file() and fpaths[0].suffix == '.torrent':
                    spath = fpaths[1]
                    tpath = fpaths[0]
                else:
                    raise ValueError('`verify` mode expects a pair of valid source and torrent paths, but not found.')
            else:
                raise ValueError(f"`verify` mode expects exactly 2 paths, not {len(fpaths)}.")

        # `modify` mode requires 1 or 2 paths
        # the first path must be an existing path to the torrent you'd like to edit, denoted as spath
        # the second path is optional, which is the alternative path to save the manipulated torrent
        elif mode == 'modify':
            if 1 <= len(fpaths) <= 2:
                if fpaths[0].is_file() and fpaths[0].suffix == '.torrent':
                    spath = fpaths[0]
                    tpath = spath if not fpaths[1:] else (
                            fpaths[1].joinpath(spath.name) if fpaths[1].is_dir() else (
                            fpaths[1] if fpaths[1].suffix == '.torrent' else \
                            fpaths[1].parent.joinpath(f"{fpaths[1].name}.torrent")))
                    if spath == tpath:
                        print('W: You are likely to overwrite the source torrent, which may be unexpected.')
                else:
                    raise ValueError(f"`modify` mode expects a valid torrent path, not {fpaths[0]}.")
            else:
                raise ValueError(f"`modify` mode expects 1 or 2 paths, not {len(fpaths)}.")

        else:
            raise ValueError('Failed to sort paths for source and torrent.')

        return tpath, spath


    @staticmethod
    def __loadJson(args, mode):
        metadata = dict()

        if mode == 'create':
            fpath = args.json if args.json else (
                    _ if (_ := pathlib.Path(__file__).absolute().with_suffix('.json')).is_file() else None)
            if fpath:
                try:
                    print(f"Loading user presets from '{fpath}'...", end=' ', flush=True)
                    d = json.loads(fpath.read_bytes())
                    if d.get('tracker_list') and \
                    isinstance(d['tracker_list'], list) and all(isinstance(i, str) for i in d['tracker_list']):
                        metadata['tracker_list'] = d['tracker_list']
                    if d.get('comment'): metadata['comment'] = str(d['comment'])
                    if d.get('created_by'): metadata['created_by'] = str(d['created_by'])
                    if d.get('creation_date'): metadata['creation_date'] = int(d['creation_date'])
                    if d.get('encoding'): metadata['encoding'] = str(d['encoding'])
                    if d.get('piece_size'): metadata['piece_size'] = int(d['piece_size']) << 10
                    if d.get('private'): metadata['private'] = int(d['private'])
                    if d.get('source'): metadata['source'] = str(d['source'])
                except FileNotFoundError:
                    print('failed (file not found)\nTerminated.')
                    sys.exit()
                except UnicodeDecodeError:
                    print('failed (invalid file)\nTerminated.')
                    sys.exit()
                except json.decoder.JSONDecodeError:
                    print('failed (invalid json)\nTerminated.')
                    sys.exit()
                except KeyError:
                    print('failed (missing key)\nTerminated.')
                    sys.exit()
                else:
                    print('succeeded')

        return metadata


    @staticmethod
    def __pickMetadata(args, mode, metadata):

        if mode == 'create':
            metadata['tracker_list'] = args.tracker_list if args.tracker_list else (
                                       _ if (_ := metadata.get('tracker_list')) else [])
            metadata['comment'] = args.comment if args.comment else (
                                       _ if (_ := metadata.get('comment')) else '')
            metadata['created_by'] = args.created_by if args.created_by else (
                                       _ if (_ := metadata.get('created_by')) else 'TorrentUtils')
            metadata['creation_date'] = args.creation_date if args.creation_date else (
                                       _ if (_ := metadata.get('creation_date')) else int(time.time()))
            metadata['encoding'] = args.encoding if args.encoding else (
                                       _ if (_ := metadata.get('encoding')) else 'UTF-8')
            metadata['piece_size'] = args.piece_size << 10 if args.piece_size else (
                                       _ if (_ := metadata.get('piece_size')) else 4096 << 10) # B -> KiB
            metadata['private'] = args.private if args.private else (
                                       _ if (_ := metadata.get('private')) else 0)
            metadata['source'] = args.source if args.source else (
                                       _ if (_ := metadata.get('source')) else '')

        elif mode == 'modify':
            if not (args.tracker_list is None): metadata['tracker_list'] = args.tracker_list
            if not (args.comment is None): metadata['comment'] = args.comment
            if not (args.created_by is None): metadata['created_by'] = args.created_by
            if not (args.creation_date is None): metadata['creation_date'] = args.creation_date
            if not (args.encoding is None): metadata['encoding'] = args.encoding
            if not (args.piece_size is None):
                print('W: supplied piece size has no effect in `modify` mode.')
                if 'piece_size' in metadata.keys(): # if piece_size is loaded from json, remove it
                    metadata.pop('piece_size')
            if not (args.private is None): metadata['private'] = args.private
            if not (args.source is None): metadata['source'] = args.source

        else: # `print` or `verify`
            if not (args.tracker_list is None): print(f"W: supplied tracker has not effect in {mode} mode.")
            if not (args.comment is None): print(f"W: supplied comment has not effect in {mode} mode.")
            if not (args.created_by is None): print(f"W: supplied creator has not effect in {mode} mode.")
            if not (args.creation_date is None): print(f"W: supplied time has not effect in {mode} mode.")
            if not (args.encoding is None): print(f"W: supplied encoding has not effect in {mode} mode.")
            if not (args.piece_size is None): print(f"W: supplied piece size has not effect in {mode} mode.")
            if not (args.private is None): print(f"W: supplied private attribute has not effect in {mode} mode.")
            if not (args.source is None): print(f"W: supplied source has not effect in {mode} mode.")

        return metadata


    def __call__(self):
        if self.mode == 'create':
            print(f"Creating torrent from '{self.spath}'.")
            self._set()
            self._load()
            self._write()
        elif self.mode == 'print':
            self._read()
            self._print()
        elif self.mode == 'verify':
            print('Verifying Source files with Torrent files.')
            print(f"S: '{self.spath}'")
            print(f"T: '{self.tpath}'")
            self._read()
            self._verify()
        elif self.mode == 'modify':
            print(f"Modifying torrent '{self.spath}'.")
            self._read()
            self._set()
            self._write()
        else:
            raise ValueError(f"Invalid mode: {mode}.")


    def _print(self):
        tname = self.torrent.name
        tsize = f"{self.torrent.torrent_size:,} Bytes"
        tencd = self.torrent.encoding
        thash = self.torrent.hash
        fsize = f"{self.torrent.content_size:,} Bytes"
        fnum = f"{len(self.torrent.file_list)} File" + 's' if len(self.torrent.file_list) > 1 else ''
        psize = self.torrent.piece_length >> 10
        pnum = self.torrent.num_pieces
        tdate = time.strftime('%Y/%m/%d %H:%M:%S', time.localtime(self.torrent.creation_date)) if self.torrent.creation_date \
                else '----/--/-- --:--:--'
        tfrom = self.torrent.created_by if self.torrent.created_by else '------------'
        tpriv = 'Private' if self.torrent.private else 'Public'
        tsour = f"from {self.torrent.source}" if self.torrent.source else ''
        tcomm = self.torrent.comment

        width = shutil.get_terminal_size()[0]

        print(f'Info ' + '-' * (width - 6))
        print(f"Name: {tname}")
        print(f"File: {tsize}, {tencd}")
        print(f"Hash: {thash}")
        print(f"Size: {fsize}, {fnum}, {psize} KiB x {pnum} Pieces")
        print(f"Time: {tdate} by {tfrom}")
        print(f"Else: {tpriv} torrent {tsour}")
        for i in range(0, math.ceil(len(tcomm) / width)):
            print(f"Comm: {tcomm[i * width : (i + 1) * width]} ")
        print(f'Tracker ' + '-' * (width - 9))
        for i, url in enumerate(self.torrent.tracker_list):
            print(eval("f'{i:0" + str(len(self.torrent.tracker_list) // 10 + 1) + "}: {url}'"))
        # TODO: add the tree-view of files


    def _load(self):
        self.torrent.load(self.spath, False, self.cfg.show_progress)


    def _read(self):
        if self.mode == 'verify':
            self.torrent.read(self.tpath)
        elif self.mode == 'modify':
            self.torrent.read(self.spath)
        else:
            print(f"Unexpected {self.mode} mode for read operation.\nTerminated.")
            sys.exit()


    def _verify(self):
        self.torrent.verify(self.spath)


    def _set(self):
        try:
            self.torrent.set(**self.metadata)
        except PieceSizeTooSmall as e:
            raise ValueError(f"Piece size must be larger than 16KiB, not {self.metadata['piece_size'] >> 10} bytes.")
        except PieceSizeUncommon as e:
            if (not self.cfg.show_prompt) or \
               input(f"Uncommon piece size {self.metadata['piece_size'] << 10} KiB. Confirm? (y/N): ").lower() == 'y':
                self.torrent.setPieceLength(self.metadata['piece_size'], no_check=True)
                self.metadata.pop('piece_size')
                self.torrent.set(**self.metadata)
            else:
                print('Terminated.')
                sys.exit()


    def _write(self):
        fpath = self.tpath.with_suffix(f"{'.' + time.strftime('%y%m%d-%H%M%S') if self.cfg.with_time_suffix else ''}.torrent")
        try:
            self.torrent.write(fpath, overwrite=False)
            print(f"Torrent saved to '{fpath}'.")
        except FileExistsError as e:
            if (not self.cfg.show_prompt) or \
               input(f"The target '{fpath}' already exists. Overwrite? (y/N): ").lower() == 'y':
                    self.torrent.write(fpath, overwrite=True)
                    print(f"Torrent saved to '{fpath}' (overwritten).")
            else:
                print('Terminated.')
                sys.exit()




'''=====================================================================================================================
CLI Interface
====================================================================================================================='''


class _CustomHelpFormatter(argparse.HelpFormatter):

    def __init__(self, prog):
        super().__init__(prog, max_help_position=50, width=100)

    def _format_action_invocation(self, action):
        if not action.option_strings or action.nargs == 0:
            return super()._format_action_invocation(action)
        default = self._get_default_metavar_for_optional(action)
        args_string = self._format_args(action, default)
        return ', '.join(action.option_strings) + ' ' + args_string


if __name__ == '__main__':

    parser = argparse.ArgumentParser(prog='TorrentUtils', formatter_class=lambda prog: _CustomHelpFormatter(prog))

    parser.add_argument('fpaths', type=pathlib.Path, nargs='*',
                        help='1 or 2 paths depending on mode', metavar='path')
    parser.add_argument('-m', '--mode', dest='mode', choices=('create', 'print', 'verify', 'modify'),
                        help='will be guessed from paths if not specified')
    parser.add_argument('-t', '--tracker', dest='tracker_list', type=str, action='extend', nargs='+',
                        help='can be specified multiple times', metavar='url')
    parser.add_argument('-s', '--piece-size', dest='piece_size', type=int,
                        help='piece size in KiB (default: 4096)', metavar='number')
    parser.add_argument('-c', '--comment', dest='comment', type=str,
                        help='the message displayed in various clients', metavar='text')
    parser.add_argument('-p', '--private', dest='private', type=int, choices={0, 1},
                        help='private torrent if 1 (default: 0)')
    parser.add_argument('--by', dest='created_by', type=str,
                        help='customise `created by` message (default: TorrentUtils)', metavar='text')
    parser.add_argument('--time', dest='creation_date', type=int,
                        help='customise the second since 19700101 (default: now)', metavar='number')
    parser.add_argument('--source', dest='source', type=str,
                        help='customise `source` message (will change torrent hash)', metavar='text')
    parser.add_argument('--encoding', dest='encoding', type=str,
                        help='customise encoding for filenames (default: UTF-8)', metavar='text')
    parser.add_argument('--json', dest='json', type=pathlib.Path,
                        help='user-defined json providing metadata presets', metavar='path')
    parser.add_argument('--time-suffix', dest='with_time_suffix', action='store_true',
                        help='insert time between torrent filename and extension')
    parser.add_argument('--progress', dest='show_progress', action='store_true',
                        help='show progress bar during creating torrent')
    parser.add_argument('-y', '--yes', dest='show_prompt', action='store_false',
                        help='just say yes - don\'t ask any question')

    Main(parser.parse_args())()
