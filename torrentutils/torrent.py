from __future__ import annotations


__all__ = ['Torrent', 'fromTorrent', 'fromFiles']

import re
import os
import math
import time
import codecs
import warnings
import urllib.parse
from pathlib import Path, PurePath
from threading import Thread, Lock, Event
from dataclasses import dataclass, field
from operator import methodcaller
from typing import Iterable, Optional, Any

from torrentutils.hasher import toSHA1
from torrentutils.bencode import bencode
from torrentutils.bencode import bdecode4torrent as bdecode
from torrentutils.tracker import Trackers
import torrentutils.job as trtjob
from torrentutils.type import strs

from collections.abc import Sequence
from typing import Optional

try:
    import dateutil.parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False

_ENCODING = 'utf-8'
_PIECE_SIZE = 4096 << 10
_ASCII_CHAR_REGEX = re.compile(r'[a-z0-9]+', re.IGNORECASE)
_INVALID_CHAR_REGEX = re.compile(r'(\s|[\/:*?"<>|])')


def fromTorrent(path):
    '''Wrapper function to read a torrent file and return it.'''
    torrent = Torrent()
    torrent.read(Path(path))
    return torrent


def fromFiles(path):
    '''Wrapper function to load files as a torrent and return it.'''
    torrent = Torrent()
    torrent.load(Path(path))
    return torrent


@dataclass
class _TorrentMeta():

    '''The basic yet most common metadata of a torrent'''

    trackers: Trackers = Trackers()  # a `Trackers` instance that actually manages the tracker list
    comment: str = ''  # the comment message
    creator: str = ''  # the creator of the torrent
    date: int = 0  # the creation time
    encoding: str = _ENCODING  # the encoding for text
    hash: str = ''  # the hash of the torrent


@dataclass
class _TorrentInfo():

    '''The required and most common metadata in torrent's info dict.'''

    # the list of tuple of path parts and file size
    files: list[tuple[tuple[str, ...], int]] = field(default_factory=list)
    name: str = ''  # the root name of the torrent
    piece_length: int = _PIECE_SIZE  # the piece size in bytes
    pieces: bytes = b''  # the long raw bytes of pieces' sha1
    private: bool = False  # whether the torrent is private
    source: str = ''  # the special message particularly used by private trackers


@dataclass
class _FileInfo():
    path: tuple[str, ...]
    size: int

    @property
    def info(self) -> tuple[tuple[str, ...], int]:
        return (self.path, self.size)


class Torrent():

    def __init__(self, **torrent_set_kwargs):
        '''
        Instantiate a blank torrent, optionally with runtime parameters as well as any arguments acceptable by Torrent.set() to override the default metadata.
        '''
        self._meta: _TorrentMeta = _TorrentMeta()
        self._info: _TorrentInfo = _TorrentInfo()
        self._misc: dict[str, Any] = {}  # this is used to save other non-standard metadata
        self.set(**torrent_set_kwargs)

        self._write_lock: Lock = Lock()  #! only one call can modify the torrent at a time

        self._job_queue: list[trtjob.TorrentJob] = []
        self._job_index: int = 0
        self._job_added: Event = Event()
        self._job_doing: Event = Event()

        self._job_thread = Thread(target=self._executeJobs)
        self._job_thread.start()

    #* -----------------------------------------------------------------------------------------------------------------
    #* methods to operate background writing jobs
    #* -----------------------------------------------------------------------------------------------------------------

    def _executeJobs(self):
        while True:
            self._job_added.wait()
            self._job_added.clear()
            with self._write_lock:
                while len(self._job_queue) >= self._job_index:
                    self._job_doing.set()
                    self._job_queue[self._job_index].start()
                    self._job_index += 1
                self._job_doing.clear()

    def _addJob(self, job: trtjob.TorrentJob):
        self._job_queue.append(job)
        self._job_added.set()

    def wait(self):
        '''Wait for all background writing jobs to finish.'''
        self._job_doing.wait()

    @property
    def is_locked(self) -> bool:
        '''Return whether the torrent is locked by any writing call or job.'''
        return self._write_lock.locked()

    @property
    def is_running(self) -> bool:
        '''Return whether there is any background writing job running.'''
        return self._job_doing.is_set()

    @property
    def running_job(self) -> Optional[trtjob.TorrentJob]:
        '''Return the current running job.'''
        if self.is_running and self._job_index < len(self._job_queue):
            return self._job_queue[self._job_index]
        return None

    @property
    def jobs(self) -> list[trtjob.TorrentJob]:
        '''Return a copy of the job queue.'''
        return self._job_queue[:]

    #* -----------------------------------------------------------------------------------------------------------------
    #* properties imitating keys existing in an actual torrent
    #* -----------------------------------------------------------------------------------------------------------------

    @property
    def announce(self) -> Optional[str]:
        '''
        Return the `announce` entry of the torrent.
        In practice, this means the first tracker url of the torrent.
        '''
        return self._meta.trackers.announce

    @announce.setter
    def announce(self, url: str):
        '''
        Modify the `announce` entry of the torrent.
        In practice, this means the first tracker url of the torrent.
        '''
        self._meta.trackers.announce = url

    @property
    def announce_list(self) -> Optional[list[list[str]]]:
        '''Return all trackers if total trackers >=2.'''
        return self._meta.trackers.announce_list

    @announce_list.setter
    def announce_list(self, urls: strs|Sequence[strs]):
        '''Overwrite the whole tracker list with at least 2 trackers.'''
        self._meta.trackers.announce_list = urls

    @property
    def comment(self) -> Optional[str]:
        '''Return the comment message displayable in various clients.'''
        return _ if (_ := self._meta.comment[:]) else None

    @comment.setter
    def comment(self, chars: str):
        '''Set the comment message.'''
        self.setComment(chars)

    @property
    def created_by(self) -> Optional[str]:
        '''Return the creator of the torrent.'''
        return _ if (_ := self._meta.creator[:]) else None

    @created_by.setter
    def created_by(self, creator: str):
        '''Set the creator of the torrent.'''
        self.setCreator(creator)

    @property
    def creation_date(self) -> Optional[int]:
        '''Return torrent creation time as the number of second since 1970-01-01.'''
        return _ if (_ := self._meta.date) > 0 else None

    @creation_date.setter
    def creation_date(self, date: int):
        '''Set torrent creation time.'''
        self.setDate(date)

    @property
    def encoding(self) -> Optional[str]:
        '''Return the encoding for text.'''
        return _ if (_ := self._meta.encoding[:]) else None

    @encoding.setter
    def encoding(self, enc: str):
        '''Set the encoding for text.'''
        self.setEncoding(enc)

    @property
    def hash(self) -> str:
        '''
        Return the torrent hash at the moment. Read-only.
        Note that if no encoding was set, the hash is calcualted using `utf-8` benconded data.
        '''
        return toSHA1(bencode(self.info_dict, self.encoding or _ENCODING)).hex()

    @property
    def files(self) -> Optional[list[dict[str, int|tuple[str, ...]]]]:
        '''
        Return a list of dict of file size and path parts if files number >=2. Read-only.
        Corresponding to torrent['info']['files'] in an actual torrent.
        '''
        return list({
            'path': fparts, 'length': fsize
            } for (fparts, fsize) in self._info.files) if len(self._info.files) > 1 else None

    @property
    def length(self) -> Optional[int]:
        '''
        Return the size of single file torrent. Read-only.
        Corresponding to torrent['info']['length'] in an actual torrent.
        '''
        return self._info.files[0][1] if len(self._info.files) == 1 else None

    @property
    def name(self) -> Optional[str]:
        '''
        Return the root name of the torrent.
        Corresponding to torrent['info']['name'] in an actual torrent.
        '''
        return _ if (_ := self._info.name[:]) else None

    @name.setter
    def name(self, name: str):
        '''Set the root name of the torrent.'''
        self.setName(name)

    @property
    def piece_length(self) -> Optional[int]:
        '''
        Return the piece size in bytes.
        Corresponding to torrent['info']['piece length'] in an actual torrent.
        '''
        return _ if (_ := self._info.piece_length) > 0 else None

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
    def private(self) -> Optional[int]:
        '''
        Return 1 if the torrent is private, otherwise 0.
        Corresponding to torrent['info']['private'] in an actual torrent.
        '''
        return 1 if self._info.private else None

    @private.setter
    def private(self, private: int|bool):
        '''Set torrent private or not.'''
        self.setPrivate(private)

    @property
    def source(self) -> Optional[str]:
        '''
        Return a special message typically used in private torrent to alter hash.
        Corresponding to torrent['info']['source'] in an actual torrent.
        '''
        return _ if (_ := self._info.source[:]) else None

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
    def trackers(self) -> Trackers:
        '''
        Return the internal `TrackerList` instance which provides more tracker-related methods.
        Note that modifying the tracker list instance will not trigger any queued writing job.
        '''
        return self._meta.trackers

    @property
    def tracker_list(self) -> list[list[str]]:
        '''Unlike `announce` and `announce_list`, this function always returns the full tracker list.'''
        return [tier[:] for tier in self._meta.trackers]

    @tracker_list.setter
    def tracker_list(self, urls: str|strs):
        '''Set the whole list of tracker urls.'''
        self.setTracker(urls)

    @property
    def tracker_urls(self) -> list[str]:
        '''Return the list of tracker urls.'''
        return self._meta.trackers.urls

    @property
    def num_tracker(self) -> int:
        '''Return the number of trackers. Read-only.'''
        return len(self._meta.trackers)

    @property
    def num_tracker_tier(self) -> int:
        '''Return the number of tracker tiers. Read-only.'''
        return len(self._meta.trackers)

    @property
    def file_list(self) -> list[_FileInfo]:
        '''Unlike `length` and `files`, this function always returns the full list of dict of file parts and size. Read-only.'''
        return list(_FileInfo(path=parts, size=fsize) for (parts, fsize) in self._info.files)

    @property
    def size(self) -> int:
        '''Return the total size of all source files recorded in the torrent. Read-only.'''
        return sum(fsize for (_, fsize) in self._info.files)

    @property
    def torrent_size(self) -> int:
        '''Return the file size of the torrent file itself. Read-only.'''
        return len(bencode(self.torrent_dict, self.encoding or _ENCODING))

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
        for url in self.tracker_urls:
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
        key = _ASCII_CHAR_REGEX.sub('', key).lower()

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
    def pieces_hashes(self) -> list[bytes]:
        '''Return the list of piece hashes. Read-only.'''
        pieces = self._info.pieces[:]
        return [pieces[i:i + 20] for i in range(0, len(pieces), 20)]

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
    #! All methods that modifies the torrent info (= write) will only do an input check and add a job to the queue.
    #! Check the returned `TorrentJob` instance to monitor the result.
    #* -----------------------------------------------------------------------------------------------------------------

    def addTracker(self, urls: str|strs, top=True) -> trtjob.AddTrackerJob:
        '''
        Add one or more trackers.

        Arguments:
        urls: one tracker url in one string or multiple trackers from an iterable of strings.
            The function will deduplicate the input urls.
        top: whether to put the added tracker(s) to the top (default=True).

        Returns:
        A `TorrentAddTrackerJob` instance.
        '''
        urls = [urls] if isinstance(urls, str) else list(urls)
        torrent_job = trtjob.AddTrackerJob(self, urls, top)
        self._addJob(torrent_job)
        return torrent_job

    def setTracker(self, urls: str|strs) -> trtjob.SetTrackerJob:
        '''
        Overwrite the tracker list with the given one or more urls, dropping all existing ones.

        Arguments:
        urls: one tracker url in one string or multiple trackers from an iterable of strings.
            The function will deduplicate the input urls.

        Returns:
        A `TorrentSetTrackerJob` instance.
        '''
        urls = [urls] if isinstance(urls, str) else list(urls)
        torrent_job = trtjob.SetTrackerJob(self, urls)
        self._addJob(torrent_job)
        return torrent_job

    def rmTracker(self, urls: str|strs) -> trtjob.RemoveTrackerJob:
        '''
        Remove one or more trackers from the tracker list.

        Arguments:
        urls: one or more trackers in one string or an iterable of strings.

        Returns:
        A `TorrentRemoveTrackerJob` instance.
        '''
        urls = [urls] if isinstance(urls, str) else list(urls)
        torrent_job = trtjob.RemoveTrackerJob(self, urls)
        self._addJob(torrent_job)
        return torrent_job

    def setComment(self, comment: str) -> trtjob.SetCommentJob:
        '''
        Set the comment message.

        Arguments:
        comment: a string.

        Returns:
        A `TorrentSetCommentJob` instance.
        '''
        if not isinstance(comment, str): raise TypeError('Comment must be str.')
        torrent_job = trtjob.SetCommentJob(self, comment)
        self._addJob(torrent_job)
        return torrent_job

    def setCreator(self, creator) -> trtjob.SetCreatorJob:
        '''
        Set the creator of the torrent.

        Arguments:
        creator: a string.

        Returns:
        A `TorrentSetCreatorJob` instance.
        '''
        if not isinstance(creator, str): raise TypeError('Creator must be str.')
        torrent_job = trtjob.SetCreatorJob(self, creator)
        self._addJob(torrent_job)
        return torrent_job

    def setDate(
        self, date: int|float|str|time.struct_time|Iterable[int], format: Optional[str] = None
        ) -> trtjob.SetDateJob:
        '''
        Set the torrent creation time.

        Arguments:
        date: accepts multiple formats:
            int|float -> the elapsed seconds since 1970-01-01, by calendar.timegm() or time.mktime();
            time.struct_time -> the time tuple returned by `time.localtime()` or `time.gmtime()`;
            Iterable[int] -> a time tuple acceptable by `time.struct_time()`;
            str -> a valid date string that can be parsed by `time.strptime()` or `dateutil.parser.parse()`:
        format: only required if `date` is str and dateutil is not installed.
            if you specify a format, the function will always use `time.strptime()` to parse the date string.

        Returns:
        A `TorrentSetDateJob` instance.
        '''
        if isinstance(date, (int, float)):
            date = int(date)
        elif isinstance(date, str):
            if format:
                date = int(time.mktime(time.strptime(date, format)))
            elif HAS_DATEUTIL:
                date = int(dateutil.parser.parse(date).timestamp())
            else:
                raise ValueError('You must install `python-dateutil` or specify a date format for str date.')
        elif isinstance(date, time.struct_time):
            date = int(time.mktime(date))
        elif isinstance(date, Iterable) and (_date := list(date)) and all(isinstance(i, int) for i in _date):
            date = int(time.mktime(time.struct_time(_date)))
        else:
            raise ValueError('The specified date format is not understood.')
        torrent_job = trtjob.SetDateJob(self, date)
        self._addJob(torrent_job)
        return torrent_job

    def setEncoding(self, encoding: str) -> trtjob.SetEncodingJob:
        '''
        Set the encoding for text.

        Arguments:
        encoding: a string listed in Python built-in codecs.

        Returns:
        A `TorrentSetEncodingJob` instance.
        '''
        if not isinstance(encoding, str): raise TypeError('Encoding must be str.')
        codecs.lookup(encoding)  # will raise LookupError if this encoding not exists
        torrent_job = trtjob.SetEncodingJob(self, encoding)
        self._addJob(torrent_job)
        return torrent_job

    def setName(self, name: str) -> trtjob.SetNameJob:
        '''
        Set a new root name.

        Arguments:
        name: The new root name.

        Returns:
        A `TorrentSetNameJob` instance.
        '''
        if not isinstance(name, str): raise TypeError('Torrent name must be str.')
        if not name: raise ValueError('Torrent name cannot be empty.')
        if _INVALID_CHAR_REGEX.search(name): raise ValueError('Torrent name contains invalid character.')
        torrent_job = trtjob.SetNameJob(self, name)
        self._addJob(torrent_job)
        return torrent_job

    def setPieceLength(self, size: int, strict: bool = True) -> trtjob.SetPieceLengthJob:
        '''
        Set torrent piece size.
        Note that changing piece size to a different value will clear the existing torrent piece hash.

        Arguments:
        size: the piece size in number of bytes
        strict: whether to allow uncommon piece size and bypass exceptions (default=True)
            use `strict=False` to allow the following uncommon piece size:
            1. the piece size divided by 16KiB does not obtain a power of 2.
            2. the piece size is beyond the normal range [256KiB, 32MiB].
            Note that piece size <16KiB is never allowed.

        Returns:
        A `TorrentSetPieceLengthJob` instance.
        '''
        if not isinstance(size, int): raise TypeError('Piece size must be int.')
        if not isinstance(strict, bool): raise TypeError('Check strictly or not must be bool.')
        if size < 16384: raise ValueError('Piece size must be at least 16KiB.')
        if strict and size < 262144: raise ValueError('Piece size should be at least 256KiB.')
        if strict and size > 33554432: raise ValueError('Piece size should be at most 32MiB.')
        if strict and math.log2(size / 262144) % 1: raise ValueError('Piece size must be a power of 2.')
        torrent_job = trtjob.SetPieceLengthJob(self, size)
        self._addJob(torrent_job)
        return torrent_job

    def setPrivate(self, private: bool|int) -> trtjob.SetPrivateJob:
        '''
        Set torrent to private or not.

        Arguments:
        private: Any value that can be converted to `bool` and then set to private torrent if `True`.

        Returns:
        A `TorrentSetPrivateJob` instance.
        '''
        torrent_job = trtjob.SetPrivateJob(self, bool(private))
        self._addJob(torrent_job)
        return torrent_job

    def setSource(self, src: str):
        '''
        Set the source message.

        Argument:
        src: The message text that can be converted to `str`.

        Returns:
        A `TorrentSetSourceJob` instance.
        '''
        if not isinstance(src, str): raise TypeError('Source must be str.')
        torrent_job = trtjob.SetSourceJob(self, src)
        self._addJob(torrent_job)
        return torrent_job

    def set(self, **metadata: Any) -> trtjob.TorrentJob:
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

        Returns:
        A `TorrentJob` instance.
        '''
        for key, value in metadata.items():
            match key:
                case 't'|'tracker'|'trackers'|'tl'|'tlist'|'trackerlist'|'announce'|'announces'|'announcelist'|'alist':
                    return self.setTracker(value)
                case 'comment'|'c'|'comm'|'comments':
                    return self.setComment(value)
                case 'creator'|'b'|'by'|'createdby'|'creator'|'tool'|'creatingtool'|'maker'|'madeby':
                    return self.setCreator(value)
                case 'date'|'time'|'second'|'seconds'|'creationdate'|'creationtime'|'creatingdate'|'creatingtime':
                    return self.setDate(value)
                case 'encoding'|'e'|'enc'|'encoding'|'codec':
                    return self.setEncoding(value)
                case 'name'|'n'|'name'|'torrentname':
                    return self.setName(value)
                case 'ps'|'pl'|'psz'|'psize'|'piecesize'|'piecelength':
                    return self.setPieceLength(value)
                case 'private'|'p'|'priv'|'pt'|'pub'|'public':
                    return self.setPrivate(value)
                case 'source'|'s'|'src':
                    return self.setSource(value)
                case _:
                    raise KeyError(f'Unknown key: {key}')
        raise ValueError('No key specified for set().')

    #* -----------------------------------------------------------------------------------------------------------------
    #* Input/output operations
    #* -----------------------------------------------------------------------------------------------------------------

    def read(self, tpath: str|Path):
        '''Read everything from the template, i.e. copy the torrent file.
        Note that this function will clear all existing properties.

        Argument:
        tpath: the path to the torrent.'''

        tpath = Path(tpath)
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
            self._srcpath_lst = [Path('.')]
            self._srcsize_lst = [length]
        elif not length and files:
            fsize_list = []
            fpath_list = []
            for file in files:
                fsize_list.append(file[b'length'])
                fpath_list.append(Path().joinpath(*map(methodcaller('decode', encoding), file[b'path'])))
            self._srcsize_lst = fsize_list
            self._srcpath_lst = fpath_list
        else:
            raise ValueError('Unexpected error in handling source files structure.')

    def readMetadata(
        self,
        tpath: str|Path,
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
        if not (tpath := Path(tpath)).is_file():
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
                self.addTracker(template.trackers)
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

    def load(self, spath: os.PathLike, keep_name: bool = False) -> trtjob.TorrentLoadSourceFilesJob:
        '''
        Load a new file list and piece hashes from the source path.

        Arguments:
        spath: path-like objects, the source path to be loaded, either a single file or a directory.
        keep_name: whether to keep the old torrent name (default=False).

        Returns:
        A `TorrentLoadSourceFilesJob` instance.
        '''
        spath = Path(spath)
        keep_name = bool(keep_name)
        if not spath.exists(): raise FileNotFoundError(f'The specified source path "{spath}" does not exist.')
        torrent_job = trtjob.TorrentLoadSourceFilesJob(self, spath, keep_name)
        self._addJob(torrent_job)
        return torrent_job

    def write(self, tpath: os.PathLike, overwrite: bool = False):
        '''
        Save the torrent info to a torrent file.

        Arguments:
        tpath: path-like object, the path to save the torrent.
            if it's a directory, the torrent will be saved under it.
        overwrite: whether to overwrite the existing file (default=False).
        '''
        tpath = Path(tpath)
        overwrite = bool(overwrite)
        tpath = tpath / f'{self.name}.torrent' if tpath.is_dir() else tpath
        if tpath.is_file() and not overwrite:
            raise FileExistsError(f'The target "{tpath}" already exists.')
        else:
            tpath.parent.mkdir(parents=True, exist_ok=True)
            tpath.write_bytes(bencode(self.torrent_dict, self.encoding or _ENCODING))

    def verify(self, spath) -> trtjob.TorrentVerifyJob:
        '''
        Verify source files against the torrent info.

        Arguments:
        spath: the path to source files.

        Return:
        An `TorrentVerifyJob` instance.
        '''
        spath = Path(spath)
        if not spath.exists(): raise FileNotFoundError(f'The source path "{spath}" does not exist.')
        torrent_job = trtjob.TorrentVerifyJob(self, spath)
        self._addJob(torrent_job)
        return torrent_job

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
            codecs.lookup(self.encoding or _ENCODING)
        except LookupError as e:
            ret.append(f"Invalid encoding {self.encoding}.")
        try:
            bencode(self.torrent_dict, self.encoding or _ENCODING)
        except Exception as e:
            ret.append(f"Torrent bencoding failed ({e}).")
        return ret

    def index(self, path: str, case_sensitive: bool = True, num: int = 1) -> list[tuple[str, int, int]]:
        '''Given filename, return its piece index.

        Arguments:
        filename: str, the filename to find.
            Path parts are matched backward. e.g. 'b/c' will match 'a/b/c' instead of 'b/c/a'.
        num: int=1, stop search when this number of files are found (find all when num <= 0).

        Return:
        A list of 3-element tuple of (path, start-index, end-index)
            Indexed in python style, from 0 to len-1, and [m, n+1] for items from m to n
        '''
        if not isinstance(path, str): raise TypeError('Path must be str.')
        if not isinstance(case_sensitive, bool): raise TypeError('Case sensitive must be bool.')
        if not isinstance(num, int): raise TypeError('Number of files must be int.')

        target_parts = PurePath(path).parts
        n = len(target_parts)

        ret: list[tuple[str, int, int]] = []
        loaded_size = 0
        for finfo in self.file_list:
            fsize = finfo.size
            parts = tuple(self.name, *finfo.path)
            if len(parts) >= n and parts[:-n - 1:-1] == target_parts[:-n - 1:-1]:
                ret.append((
                    PurePath(*parts).as_posix(),
                    math.floor(loaded_size / self.piece_length),
                    math.ceil((loaded_size+fsize) / self.piece_length)
                    ))
                if (num := num - 1) <= 0:
                    break
            loaded_size += fsize
        return ret

    def __getitem__(self, key: int|slice) -> list[str]:
        '''Give 0-indexed piece index or slice, return files associated with it.'''

        if not isinstance(key, (int, slice)):
            raise TypeError(f"Expect int, not {key.__class__}.")

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
        for file in self.file_list:
            total_size += file.size
            if total_size > lsize:
                ret.append(os.pathsep.join(file.path))
            if total_size >= hsize:
                return ret

        raise RuntimeError('Unexpected Error. Please file a bug report.')
