import re
import math
import time
import codecs
import urllib
import shutil
import string
import hashlib
import pathlib
import warnings
import argparse
import operator
import itertools
import functools


# by default, we are in lib usage scenario, so disable stdio and raise exception on incorrect usage
INTERACTIVE = False # whether to enable all stdio inc. print and input, this is the global master switch
SHOW_PROMPT = True # whether to enable prompt to ask user e.g. whether to overwrite, ruled by `INTERACTIVE`




'''=====================================================================================================================
private helper functions
====================================================================================================================='''


def _print(*args, **kwargs):
    '''scenario dependent `print`'''
    global INTERACTIVE
    if INTERACTIVE:
        print(*args, **kwargs)


def _input(*args, **kwargs):
    '''scenario dependent `input`'''
    global INTERACTIVE, SHOW_PROMPT
    if INTERACTIVE:
        if SHOW_PROMPT:
            return input(*args, **kwargs)
        else: # just assume the user is god and right
            return True




'''=====================================================================================================================
public helper functions
====================================================================================================================='''


def bencode(obj, enc:str='utf-8') -> bytes:
    '''Bencode objects. Modified from <https://github.com/utdemir/bencoder>'''
    tobj = type(obj)
    if tobj is bytes:
        ret = str(len(obj)).encode(enc) + b":" + obj
    elif tobj is str:
        ret = bencode(obj.encode(enc))
    elif tobj is int:
        ret = b"i" + str(obj).encode(enc) + b"e"
    elif tobj in (list, tuple):
        ret = b"l" + b"".join(map(functools.partial(bencode, enc=enc), obj)) + b"e"
    elif tobj is dict:
        ret = b'd'
        for key, val in sorted(obj.items()):
            if type(key) in (bytes, str):
                ret += bencode(key, enc) + bencode(val, enc)
            else:
                raise ValueError(f"expect str or bytes, not {key}:{type(key)}")
        ret += b'e'
    else:
        raise ValueError(f'expect int, bytes, list or dict; not {obj}:{tobj}')
    return ret


def bdecode(s:(bytes, str), encoding='ascii'):
    '''Bdecode bytes. Modified from <https://github.com/utdemir/bencoder>'''
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


def fromTorrent(path):
    '''wrapper function to create the torrent object from a torrent file'''
    assert pathlib.Path(path).is_file(), f'Expect an existing file, but \'{path}\' not'
    torrent = Torrent()
    torrent.read(path)
    return torrent




'''=====================================================================================================================
Helper Class
====================================================================================================================='''


class Sha1():


    def __init__(self, sha1=None, /):
        if isinstance(sha1, str):
            assert len(sha1) % 40 == 0, f'bad sha1 str length: {len(sha1)}'
        if isinstance(sha1, bytes):
            assert len(sha1) % 20 == 0, f'bad sha1 bytes length: {len(sha1)}'
            sha1 = sha1.hex()
        self._sha1 = sha1 if sha1 else ''
        self._len = 0


    def __repr__(self):
        return self._sha1


    def __str__(self):
        return self._sha1


    def __bool__(self):
        return bool(self._sha1)


    def __len__(self):
        return len(self._sha1) // 40


    def __getitem__(self, key):
        if isinstance(key, int):
            ret = self._sha1[40 * key : 40 * key + 40]
        elif isinstance(key, slice):
            assert key.step == 1, f'Sha1 object only support step=1, not {key.step}'
            ret = self._sha1[40 * key.start : 40 * key.stop]
        return ret


    @property
    def hex(self):
        return self._sha1


    @property
    def hexB(self):
        return bytes.fromhex(self._sha1)


    def append(self, sha1, /):
        if isinstance(sha1, str):
            assert len(sha1) % 40 == 0, f'bad sha1 str length: {len(sha1)}'
        if isinstance(sha1, bytes):
            assert len(sha1) % 20 == 0, f'bad sha1 bytes length: {len(sha1)}'
            sha1 = sha1.hex()
        self._sha1 += sha1


    def clear(self):
        self._sha1 = ''


    @staticmethod
    def hash(bchars:bytes, /) -> str:
        '''Return the sha1 hash in hex str for the given bytes'''
        assert isinstance(bchars, bytes), f'expect bytes, not {bchars.__class__.__name__}'
        sha1_hasher = hashlib.sha1()
        sha1_hasher.update(bchars)
        return sha1_hasher.hexdigest()


    @staticmethod
    def hashB(bchars:bytes, /) -> bytes:
        '''Return the sha1 hash in hex bytes for the given bytes'''
        return bytes.fromhex(Sha1.hash(bchars))




'''=====================================================================================================================
Core Class
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
        self._content_sha1 = Sha1()                 # for `pieces`
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
        return self._content_sha1.hex


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
        return self.content_size // self.piece_length + 1


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
            info_dict[b'pieces'] = bytes.fromhex(self.pieces)
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
        torrent_dict[b'hash'] = Sha1.hash(bencode(torrent_dict[b'info']))

        return torrent_dict


    @property
    def hash(self) -> str:
        '''Return the torrent hash at the moment. Read-only.'''
        return Sha1.hash(bencode(self.info_dict))


    @property
    def magnet(self) -> str:
        '''Return the magnet string of the torrent. Read-only.'''
        ret = f'magnet:?xt=urn:btih:{self.hash}'
        if self.name:
            ret += f'&dn={urllib.parse.quote(self.name)}'
        if self.content_size:
            ret += f'&xl={self.content_size}'
        for url in self.tracker_list:
            ret += f'&tr={urllib.parse.quote(url)}'
        return ret


    '''---------------------------------------------------------------------------------------------
    Public member functions for manipulation, providing basic operations
    ---------------------------------------------------------------------------------------------'''


    def addTracker(self, urls, /, top=True):
        '''Add trackers

        Arguments:
        urls: the tracker urls, can be a single string or an iterable of strings
            Note that duplicated tracker will be automatically removed.
        top: place added trackers to the top if True, otherwise bottom (default=True)
        '''
        urls = [urls] if isinstance(urls, str) else list(urls)
        if top:
            for url in urls.reverse():
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
        assert isinstance(url, str), f'expect str, not {url.__class__.__name__}'
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
            raise ValueError('supplied date is not understood')

    @creation_date.setter
    def creation_date(self, date):
        self.setDate(date)


    def setEncoding(self, enc, /):
        '''Set the encoding for non-ascii characters

        Argument:
        enc: the encoding, must be a valid encoding for python
        '''
        try:
            codecs.lookup(enc)
        except LookupError:
            raise LookupError(f'unknown encoding: {enc}')
        else:
            self._encoding_str = enc # respect the encoding str supplied by user

    @encoding.setter
    def encoding(self, enc):
        self.setEncoding(enc)


    def setName(self, name, /):
        name = str(name)
        if not name:
            raise ValueError('name must not be empty')
        if not all([False if (char in name) else True for char in r'\/:*?"<>|' ]):
            raise ValueError('invalid torrent name')
        self._torrent_name_str = name

    @name.setter
    def name(self, name):
        self.setName(name)


    def setPieceLength(self, size, /):
        '''Set torrent piece size
        Note that changing piece size to a different value will clear existing torrent piece hash
        Under interactive scenario, it may prompt to ask the user when the new piece size looks strange:
        1. the piece size divided by 16KiB does not obtain a power of 2.
        2. the piece size is beyond the range [256KiB, 32MiB]

        Argument:
        size: the new piece size, that can be converted to `int`
        '''
        size = int(size)
        if size == self._piece_size_int:
            return None # we have nothing to do

        if size < 16384: # piece size must be larger than 16KiB
            if INTERACTIVE:
                _print('piece size smaller than 16KiB is not allowed')
                _print(f'Piece size not changed, still {self._piece_size_int>>10} KiB')
            else: # raise error when used as lib
                raise ValueError('piece size must be larger than 16KiB')

        if (math.log2(size / 262144) % 1) or (size < 262144) or (size > 33554432) and INTERACTIVE:
            if 'y' != _input(f'The piece size {size >> 10} KiB is UNCOMMON.\n'
                            'Confirm? (enter y to CONFIRM or anything else to cancel): '):
                _print(f'Piece size not changed, still {self._piece_size_int>>10} KiB')
                return None

        if size != self._piece_size_int:
            if self._content_sha1.hex:
                print('Piece hash cleared')
            self._content_sha1.clear() # changing piece size will clear existing hash


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
            date: d, date, time, second, seconds
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
            elif key in ('d', 'date', 'time', 'second', 'seconds'):
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
                if INTERACTIVE:
                    _print('ignored unknown key: {key}')
                else:
                    raise ValueError('unknown key: {key}')


    def read(self, path, /):
        '''Load all information from the template. Note that this function will clear all existing keys.'''
        torrent_dict = bdecode(pathlib.Path(path).read_bytes())

        # we need to know encoding first
        encoding = torrent_dict.get(b'encoding', b'utf-8').decode()                 # str
        # tracker list requires deduplication
        trackers = [torrent_dict[b'announce']] if torrent_dict.get(b'announce') else []
        trackers += list(itertools.chain(*torrent_dict[b'announce-list'])) if torrent_dict.get(b'announce-list') else []
        trackers = list(map(operator.methodcaller('decode', encoding), trackers))   # bytes to str
        trackers = list(dict.fromkeys(trackers))                                    # ordered deduplicate
        # other keys
        comment = torrent_dict.get(b'comment', b'').decode(encoding)                # str
        created_by = torrent_dict.get(b'created by', b'').decode(encoding)          # str
        creation_date = torrent_dict.get(b'creation date', 0)                       # int
        files = torrent_dict.get(b'info').get(b'files', [])                         # list
        length = torrent_dict.get(b'info').get(b'length', 0)                        # int
        name = torrent_dict.get(b'info').get(b'name', b'').decode(encoding)         # str
        piece_length = torrent_dict.get(b'info').get(b'piece length', 0)            # int
        pieces = torrent_dict.get(b'info').get(b'pieces', b'').hex()                # str
        private = torrent_dict.get(b'info').get(b'private', 0)                      # int
        source = torrent_dict.get(b'info').get(b'source', b'').decode(encoding)     # str

        # everything looks good, now let's write attributes
        self._tracker_list = trackers
        self._comment_str = comment
        self._creator_str = created_by
        self._datesec_int = creation_date
        self._encoding_str = encoding
        if length and not files:
            self._content_fpath_list = [pathlib.Path('.')]
            self._content_fsize_list = [length]
        elif not length and files:
            fsize_list = []
            fpath_list = []
            for file in files:
                fsize_list.append(file[b'length'])
                fpath_list.append(pathlib.Path().joinpath(*map(operator.methodcaller('decode', encoding), file[b'path'])))
            self._content_fsize_list = fsize_list
            self._content_fpath_list = fpath_list
        else:
            raise ValueError('')
        self._torrent_name_str = name
        self._piece_size_int = piece_length
        self._private_int = private
        self._content_sha1 = Sha1(pieces)
        self._source_str = source


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


    def load(self, content_fpath, piece_size=0, preserve_name=False):
        '''This member function refreshes the core info of a torrent: file list/size and piece hash.
        By default, it loads files from internal file path with internal piece size.
        Optionally, you can supply alternative file path and piece size, and choose whether to preserve torrent name.

        The following public attributes will be overwritten on success:
            self.files
            self.length
            self.name (may be preserved by `preserve_name=True`)
            self.piece_length
            self.pieces
        '''
        # first handle arguments
        assert type(content_fpath) in (pathlib.Path, str)
        assert type(piece_size) in (int,)
        assert type(preserve_name) in (bool,)
        content_fpath = pathlib.Path(content_fpath)
        piece_size = piece_size if piece_size else self._piece_size_int
        self._chkParams(content_fpath_to_load=content_fpath, piece_size=piece_size)

        # try update
        fpaths = [content_fpath] if content_fpath.is_file() else \
                 sorted(filter(operator.methodcaller('is_file'), content_fpath.rglob('*')))
        fpath_list = [fpath.relative_to(content_fpath) for fpath in fpaths]
        fsize_list = [fpath.stat().st_size for fpath in fpaths]
        if sum(fsize_list):
            sha1_str = str()
            piece_bytes = bytes()
            if SHOW_PROGRESS: pbar = tqdm.tqdm(total=sum(fsize_list), unit='B', unit_scale=True)
            desc_width = shutil.get_terminal_size()[0] // 3
            for fpath in fpaths:
                fobj = fpath.open('rb')
                if SHOW_PROGRESS: pbar.set_description(str(fpath)[-desc_width:], refresh=True)
                while (read_bytes := fobj.read(piece_size - len(piece_bytes))):
                    piece_bytes += read_bytes
                    if len(piece_bytes) == piece_size:
                        sha1_str += Sha1.hash(piece_bytes)
                        piece_bytes = bytes()
                    if SHOW_PROGRESS: pbar.update(len(read_bytes))
                fobj.close()
            sha1_str += Sha1.hash(piece_bytes) if piece_bytes else b''
            if SHOW_PROGRESS: pbar.close()

            # Everything looks good, let's update internal parameters
            self._torrent_name_str = self.name if preserve_name else content_fpath.name
            self._piece_size_int = piece_size
            self._content_fpath_list = fpath_list
            self._content_fsize_list = fsize_list
            self._content_sha1 = Sha1(sha1_str)

        else:
            print('Nothing was updated as the content size is 0.')


    def write(self, fpath, /, handle_existing='skip', with_time_suffix=True):
        '''Save the torrent to a file

        Arguments:
        fpath: an alternative path to save the torrent, otherwise it's written to the internal torrent path.
            value: path-like object (required, positional-only)
        handle_existing: what to do if the target path exists; will always skip if an existing dir is present.
            value: {skip, overwrite, prompt} (default=skip)
        with_time_suffix: whether to insert YYMMDD-HHmmss in the filename.
            value: bool (default=True)

        Return: return the reason why it was not successfully saved
        '''

        assert handle_existing in {'skip', 'overwrite', 'prompt'}, 'expect {skip, overwrite, prompt};' \
                                                                   f"not '{handle_existing}'"
        assert self.isValid(), f'the torrent is not ready to be saved: {self.whyInvalid()}'

        with_time_suffix = bool(with_time_suffix)
        fpath = pathlib.Path(fpath).absolute()
        fpath = fpath.with_suffix(f'{"." + time.strftime("%y%m%d-%H%M%S") if with_time_suffix else ""}.torrent')

        ret = True
        if fpath.is_dir():
            raise IsADirectoryError(f'a directory exists at {fpath}; '
                                    f'please remove it before writing torrent')
        elif fpath.is_file():
            if handle_existing == 'skip':
                print(f"A file already exists at '{fpath}'; skipped")
                ret = False
            if handle_existing == 'overwrite':
                fpath.unlink()
                fpath.write_bytes(bencode(self.torrent_dict))
                print(f"Torrent saved to '{fpath}' (overwritten)")
            if handle_existing == 'prompt':
                if input(f"A file already exists at '{fpath}'\n"
                         f"Overwrite? (Y/y to OVERWRITE, or anything else to cancel): ").lower() == 'y':
                    fpath.unlink()
                    fpath.write_bytes(bencode(self.torrent_dict))
                    print(f'Torrent saved to \'{fpath} (overwritten)\'')
                else:
                    print('Cancelled')
                    ret = f"A file already exists at '{fpath}"
        else: #
            fpath.write_bytes(bencode(self.torrent_dict))
            print(f'Torrent saved to \'{fpath}\'')
        return ret


    def whyInvalid(self):
        '''Return the reason why the torrent is not ready to be saved'''
        ret = []
        if not self.name:
            ret.append('torrent name has not been set')
        if not self.file_list:
            ret.append('there is no content file in the torrent')
        if not self.piece_length:
            ret.append('piece size cannot be 0')
        if self.piece_length * (len(self.pieces) - 1) >= self.content_size:
            ret.append('torrent size smaller than expected')
        if self.piece_length * (len(self.pieces)) < self.content_size:
            ret.append('torrent size larger than expected')
        try:
            bencode(self.torrent_dict)
        except Exception as e:
            ret.append(f'torrent bencoding failed ({e})')
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
        assert 0 <= st < ed <= self.content_size, f'invalid interval'

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
        raise ValueError('file not found')


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
        assert 0 <= st < ed <= self.num_pieces, f'invalid interval'

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
        assert 0 <= st < ed <= self.content_size, f'invalid interval'

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
        assert 0 <= st < ed <= self.num_pieces, f'invalid interval'

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
                            if Sha1.hash(piece_bytes) != self.pieces[piece_idx]: # sha1 mismatch
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
        if piece_bytes and Sha1.hash(piece_bytes) != self.pieces[piece_idx]: # remainder
            piece_error_list.append(piece_idx)

        return piece_error_list


    def print(self):
        raise NotImplementedError




'''=====================================================================================================================
CLI functions
====================================================================================================================='''


def _resolveArgs(args):


    def __inferMode(fpaths):
        '''Inferring working mode from the number of paths is limited: some modes cannot be inferred'''
        ret = None

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
            raise ValueError('Failed to infer working mode')

        return ret


    def __sortPath(fpaths, mode):
        '''Based on the working mode, sort out the most proper paths for torrent and content.'''
        content_fpath = torrent_fpath = None

        # `create` mode requires 1 or 2 paths
        # the first path of non-torrent file/dir will be selected as the content path
        # if both are torrent files, the first path is selected as the content path
        # the other path is the optional torrent path to save to
        # if the torrent path is not specified, the torrent is saved along with the content path
        if mode == 'create':
            if len(fpaths) == 1: # only 1 path, which must be the content path
                if fpaths[0].is_file() and fpaths[0].name == '.torrent':
                    print('W: Torrent is being created from a torrent, which is generally not expected.')
                content_fpath = fpaths[0]
                torrent_fpath = content_fpath.parent.joinpath(content_fpath.name + '.torrent')
            elif len(fpaths) == 2:
                # path 0 is a non-torrent file/dir
                if fpaths[0].is_dir() or (paths[0].is_file() and paths[0].suffix != '.torrent'):
                    content_fpath = fpaths[0]
                    torrent_fpath = fpaths[1].with_suffix('.torrent') if fpaths[1].is_file() else \
                                    fpaths[1].joinpath(content_fpath.name + '.torrent')
                # path 1 is a non-torrent file/dir
                elif fpaths[1].is_dir() or (paths[1].is_file() and paths[1].suffix != '.torrent'):
                    content_fpath = fpaths[1]
                    torrent_fpath = fpaths[0].with_suffix('.torrent') if fpaths[0].is_file() else \
                                    fpaths[0].joinpath(content_fpath.name + '.torrent')
                # both are torrent files
                else:
                    print('W: You are creating from a torrent, which is generally not expected.')
                    content_fpath = fpaths[0]
                    torrent_fpath = fpaths[1].with_suffix('.torrent') if fpaths[1].is_file() else \
                                    fpaths[1].joinpath(content_fpath.name + '.torrent')
            else:
                raise ValueError(f'`create` mode expects 1 or 2 paths, not {len(fpaths)}')

        # `print` mode requires exactly 1 path, which must be a torrent file
        elif mode == 'print':
            if len(fpaths) == 1:
                if fpaths[0].is_file() and fpaths[0].suffix == '.torrent':
                    torrent_fpath = fpaths[0]
                else:
                    raise ValueError(f'`print` mode expects a torrent path, not {fpaths[0]}')
            else:
                raise ValueError(f'`print` mode expects exactly 1 paths, not {len(fpaths)}')

        # `verify` mode requires exactly 2 paths
        # the first path of a torrent file is selected as the torrent file
        # the other path is left as the content path
        elif mode == 'verify':
            if len(fpaths) == 2:
                if fpaths[0].is_file() and fpaths[0].suffix == '.torrent':
                    torrent_fpath = fpaths[0]
                    content_fpath = fpaths[1]
                elif fpaths[1].is_file() and fpaths[1].suffix == '.torrent':
                    torrent_fpath = fpaths[1]
                    content_fpath = fpaths[0]
                else:
                    raise ValueError(f'`verify` mode expects a torrent path, but not found')
            else:
                raise ValueError(f'`verify` mode expects exactly 2 paths, not {len(fpaths)}')

        # `modify` mode requires 1 or 2 paths
        # the first path is always the torrent file to load from
        # the second path is an optional alternative path to save the manipulated torrent
        # `content_fpath` is the torrent to load from, `torrent_fpath` is the path to save to
        elif mode == 'modify':
            if len(fpaths) == 1:
                if fpaths[0].is_file() and fpaths[0].suffix == '.torrent':
                    content_fpath = fpaths[0]
                    torrent_fpath = content_fpath.parent.joinpath(content_fpath.name + '.torrent')
                else:
                    raise ValueError(f'`modify` mode expects a torrent path, not {fpaths[0]}')
            elif len(fpaths) == 2:
                if fpaths[0].is_file() and fpaths[0].suffix == '.torrent':
                    content_fpath = fpath[0]
                    torrent_fpath = fpaths[1].with_suffix('.torrent') if fpaths[1].is_file() else \
                                    fpaths[1].joinpath(content_fpath.name + '.torrent')
                else:
                    raise ValueError(f'`modify` mode expects a torrent path, but not found')
            else:
                raise ValueError(f'`modify` mode expects exactly 1 or 2 paths, not {len(fpaths)}')

        else:
            raise ValueError('Failed to sort paths for torrent and content')

        return torrent_fpath, content_fpath


    def __pickMetadata(args, mode):
        metadata = dict()

        if mode in ('create', 'modify'):
            if args.tracker_list: metadata['tracker_list'] = args.tracker_list
            if args.comment: metadata['comment'] = args.comment
            if args.creation_tool: metadata['creator'] = args.creation_tool
            if args.creation_time: metadata['date'] = args.creation_time
            if args.encoding: metadata['encoding'] = args.encoding
            if args.piece_size: metadata['piece_size'] = args.piece_size << 10 # cli input is in KiB, we need Bytes
            if args.private: metadata['private'] = args.private
            if args.source: metadata['source'] = args.source
        else:
            print(f'W: Supplied metadata was ignored in `{mode}` mode')

        return metadata


    def __pickCliCfg(args):
        cfg = dict()

        cfg['show_prompt'] = args.show_prompt
        cfg['with_time_suffix'] = args.with_time_suffix
        try:
            import tqdm
        except ImportError:
            if cfg['show_prompt']:
                print('I: Progress bar won\'t show as it\'s not installed, consider `pip3.8 install tqdm`.')
            cfg['show_progress'] = False # tqdm is not installed, so don't use progress bar
        else:
            cfg['show_progress'] = args.show_progress # it's still controlled by `INTERACTIVE`

        return cfg


    # if mode is not specified, infer it from the number of supplied paths
    mode = args.mode if args.mode else __inferMode(args.fpaths)
    # based on the working mode, pick the most likely torrent and content paths
    torrent_fpath, content_fpath = __sortPath(args.fpaths, mode)
    # extract metadata from cli arguments
    metadata = __pickMetadata(args, mode)
    # extract cli config from cli arguments
    cfg = __pickCliCfg(args)

    # we are now in cli usage scenario
    global INTERACTIVE, SHOW_PROMPT
    INTERACTIVE = True
    SHOW_PROMPT = cfg['show_prompt']

    return mode, torrent_fpath, content_fpath, metadata, cfg




def _main(args):
    mode, torrent_fpath, content_fpath, metadata, cfg = _resolveArgs(args)
    torrent = Torrent()
    if mode == 'create':
        print(f"Creating a new torrent")
        print(f"S: '{content_fpath}'")
        torrent.load(content_fpath)
        torrent.set(**metadata)
        torrent.write(torrent_fpath, 'prompt' if cfg.show_prompt else 'overwrite', cfg.with_time_suffix)
    elif mode == 'print':
        torrent.read(torrent_fpath)
        torrent.print()
    elif mode == 'verify':
        print(f"Verifying torrent against files")
        print(f"T: '{torrent_fpath}'")
        print(f"F: '{content_fpath}'")
        torrent.read(torrent_fpath)
        torrent.verify(content_fpath)
    elif mode == 'modify':
        print(f"Modifying torrent metadata")
        torrent.read(content_fpath)
        torrent.set(**metadata)
        torrent.write(torrent_fpath, 'prompt' if cfg.show_prompt else 'overwrite', cfg.with_time_suffix)
    else:
        raise ValueError(f'Invalid mode: {mode}')




'''=====================================================================================================================
cli interface
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

    parser.add_argument('fpaths', nargs='+', type=pathlib.Path,
                        help='1 or 2 paths depending on mode', metavar='path')
    parser.add_argument('-m', '--mode', choices=('create', 'print', 'verify', 'modify'), default='',
                        help='will be guessed from paths if not specified')
    parser.add_argument('-t', '--tracker', action='extend', nargs='+', dest='tracker_list', type=str,
                        help='can be specified multiple times', metavar='url')
    parser.add_argument('-s', '--piece-size', dest='piece_size', default=4096, type=int,
                        help='piece size in KiB (default: 16384)', metavar='number')
    parser.add_argument('-c', '--comment', dest='comment', type=str,
                        help='the message displayed in various clients', metavar='text')
    parser.add_argument('-p', '--private', choices={0, 1}, type=int,
                        help='private torrent if 1 (default: 0)')
    parser.add_argument('--tool', dest='creation_tool', default='TorrentUtils', type=str,
                        help='customise `created by` message (default: TorrentUtils)', metavar='text')
    parser.add_argument('--time', dest='creation_time', default=int(time.time()), type=int,
                        help='customise the second since 19700101 (default: now)', metavar='number')
    parser.add_argument('--source', dest='source', type=str,
                        help='customise `source` message (will change torrent hash)', metavar='text')
    parser.add_argument('--encoding', dest='encoding', default='UTF-8', type=str,
                        help='customise encoding for filenames (default: UTF-8)', metavar='text')
    parser.add_argument('-y', '--yes', '--no-prompt', action='store_false', dest='show_prompt',
                        help='don\'t prompt the user with any interactive question')
    parser.add_argument('--no-time-suffix', action='store_false', dest='with_time_suffix',
                        help='don\'t include the current time in new torrent\'s name')
    parser.add_argument('--no-progress', action='store_false', dest='show_progress',
                        help='don\'t display the progress bar in creating torrent')
    parser.add_argument('--version', action='version', version='%(prog)s 0.9')

    _main(parser.parse_args())
