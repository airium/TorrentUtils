from __future__ import annotations

import os
import copy
from typing import Optional, Any
from pathlib import Path, PurePath

import torrentutils.torrent as trt
from torrentutils.hasher import toSHA1
from torrentutils.error import TorrentIsEmptyError

try:
    from natsort import os_sorted
    HAS_NATSORT = True
except ImportError:
    HAS_NATSORT = False


class TorrentJob:

    def __init__(self, torrent: trt.Torrent, job_name: str|None = None):
        self._torrent = torrent
        self._job_name = job_name or ''

        self._started: bool = False
        self._done: bool = False
        self._progress: float = 0.0
        self._succeeded: bool = False
        self._failed: bool = False
        self._failed_reason: str = ''
        self._result: Any = None

    def start(self):
        self._started = True
        try:
            self._start()
            self._succeeded = True
        except Exception as e:
            self._failed = True
            self._failed_reason = f'{e.__class__.__name__}: {e}'
        finally:
            self._progress = 1.0
            self._done = True

    def _start(self, *args, **kwargs):
        raise NotImplementedError(f'The torrent job has not been implemented.')

    @property
    def name(self) -> str:
        return self._job_name[:]

    @property
    def started(self) -> bool:
        return self._started

    @property
    def done(self) -> bool:
        return self._done

    @property
    def progress(self) -> float:
        return self._progress

    @property
    def succeeded(self) -> bool:
        return self._succeeded

    @property
    def failed(self) -> bool:
        return self._failed

    @property
    def failed_reason(self) -> str:
        return self._failed_reason[:]

    @property
    def result(self) -> Any:
        return copy.copy(self._result)


class AddTrackerJob(TorrentJob):

    def __init__(
        self,
        torrent: trt.Torrent,
        urls: str|list[str]|list[list[str]],
        top: bool = True,
        job_name: Optional[str] = None,
        ):
        super().__init__(torrent=torrent, job_name=job_name)
        self._urls = urls
        self._top = top

    def _start(self):
        self._torrent.trackers.insert(self._urls, index=(0 if self._top else -1))


class SetTrackerJob(TorrentJob):

    def __init__(
        self,
        torrent: trt.Torrent,
        urls: str|list[str]|list[list[str]],
        job_name: Optional[str] = None,
        ):
        super().__init__(torrent=torrent, job_name=job_name)
        self._trackers = urls

    def _start(self):
        self._torrent._meta.trackers.set(self._trackers)


class RemoveTrackerJob(TorrentJob):

    def __init__(
        self,
        torrent: trt.Torrent,
        urls: list[str],
        job_name: Optional[str] = None,
        ):
        super().__init__(torrent=torrent, job_name=job_name)
        self._tracker = urls

    def _start(self):
        self._torrent._meta.trackers.remove(self._tracker)


class SetCommentJob(TorrentJob):

    def __init__(self, torrent: trt.Torrent, comment: str, job_name: str|None = None):
        super().__init__(torrent=torrent, job_name=job_name)
        self._comment = comment

    def _start(self):
        self._torrent._meta.comment = self._comment


class SetCreatorJob(TorrentJob):

    def __init__(self, torrent: trt.Torrent, creator: str, job_name: str|None = None):
        super().__init__(torrent=torrent, job_name=job_name)
        self._creator = creator

    def _start(self):
        self._torrent._meta.creator = self._creator


class SetDateJob(TorrentJob):

    def __init__(self, torrent: trt.Torrent, date: int, job_name: str|None = None):
        super().__init__(torrent=torrent, job_name=job_name)
        self._date = date

    def _start(self):
        self._torrent._meta.date = self._date


class SetEncodingJob(TorrentJob):

    def __init__(self, torrent: trt.Torrent, encoding: str, job_name: str|None = None):
        super().__init__(torrent=torrent, job_name=job_name)
        self._encoding = encoding

    def _start(self):
        self._torrent._meta.encoding = self._encoding


class SetNameJob(TorrentJob):

    def __init__(self, torrent: trt.Torrent, name: str, job_name: str|None = None):
        super().__init__(torrent=torrent, job_name=job_name)
        self._torrent_name = name

    def _start(self):
        self._torrent._info.name = self._torrent_name


class SetPieceLengthJob(TorrentJob):

    def __init__(self, torrent: trt.Torrent, piece_length: int, job_name: str|None = None):
        super().__init__(torrent=torrent, job_name=job_name)
        self._piece_length = piece_length

    def _start(self):
        if self._piece_length != self._torrent._info.piece_length:
            self._torrent._info.piece_length = self._piece_length
            #! changing piece size will clear existing hash
            self._torrent._info.pieces = b''


class SetPrivateJob(TorrentJob):

    def __init__(self, torrent: trt.Torrent, private: bool, job_name: str|None = None):
        super().__init__(torrent=torrent, job_name=job_name)
        self._private = private

    def _start(self):
        self._torrent._info.private = self._private


class SetSourceJob(TorrentJob):

    def __init__(self, torrent: trt.Torrent, source: str, job_name: str|None = None):
        super().__init__(torrent=torrent, job_name=job_name)
        self._source = source

    def _start(self):
        self._torrent._info.source = self._source


class ReadTorrentJob(TorrentJob):

    def __init__(self, torrent: trt.Torrent, path: Path, job_name: str|None = None):
        super().__init__(torrent=torrent, job_name=job_name)
        self._path = path

    def _start(self):
        pass


class TorrentLoadSourceFilesJob(TorrentJob):

    def __init__(
        self, torrent: trt.Torrent, path: Path, keep_name: bool = False, nproc: int = 1, job_name: str|None = None
        ):
        super().__init__(torrent=torrent, job_name=job_name)
        self._path = path
        self._nproc = nproc
        self._keep_name = keep_name

        self._n_files_read: int = 0
        self._n_total_files: int = 0
        self._read_size: int = 0
        self._total_size: int = 0

    @property
    def file_progress(self) -> float:
        return self._n_files_read / (self._n_total_files or 1)

    @property
    def size_progress(self) -> float:
        return self._read_size / (self._total_size or 1)

    @property
    def progress(self) -> float:
        return min(self.file_progress, self.size_progress)

    def _start(self):

        psize = self._torrent._info.piece_length
        if psize < 16 * 1024: raise ValueError('Piece size must be at least 16 KiB.')

        fpaths = []
        if self._path.is_file():
            fpaths = [self._path]
        elif self._path.is_dir():
            fpaths = list(self._path.rglob('*'))
            fpaths = os_sorted(fpaths) if HAS_NATSORT else sorted(fpaths)

        self._n_total_files = len(fpaths)
        if not self._n_total_files: raise FileNotFoundError('No files found.')

        file_sizes = [fpath.stat().st_size for fpath in fpaths]
        self._total_size = sum(file_sizes)
        if not self._total_size: raise ValueError('All source files are empty.')

        piece_sha1s: bytes = b''
        piece_bytes: bytes = b''
        for fpath in fpaths:
            with fpath.open('rb') as fobj:
                while (read_bytes := fobj.read(psize - len(piece_bytes))):
                    piece_bytes += read_bytes
                    self._read_size += len(read_bytes)
                    if len(piece_bytes) == psize:
                        piece_sha1s += toSHA1(piece_bytes)
                        piece_bytes = b''
                else:
                    if piece_bytes: piece_sha1s += toSHA1(piece_bytes)
            self._n_files_read += 1

        if not self._keep_name: self._torrent._info.name = self._path.name
        self._torrent._info.pieces = piece_sha1s
        self._torrent._info.files = [(p.relative_to(self._path).parts, s) for (p, s) in zip(fpaths, file_sizes)]


class TorrentVerifyJob(TorrentJob):

    def __init__(self, torrent: trt.Torrent, spath: Path, job_name: str|None = None):
        super().__init__(torrent=torrent, job_name=job_name)
        self._spath = spath

        self._n_files_read: int = 0
        self._n_total_files: int = 0
        self._read_size: int = 0
        self._total_size: int = 0

        self._errored_pieces: list[int] = []
        self._errored_fpaths: list[str] = []

    @property
    def file_progress(self) -> float:
        return self._n_files_read / (self._n_total_files or 1)

    @property
    def size_progress(self) -> float:
        return self._read_size / (self._total_size or 1)

    @property
    def progress(self) -> float:
        return min(self.file_progress, self.size_progress)

    @property
    def result(self) -> dict[str, list[str]|list[int]]:
        return {
            'pieces': self._errored_pieces[:],
            'files': self._errored_fpaths[:],
            }

    def _start(self):

        spath = self._spath
        num_files = self._torrent.num_files
        torrent_name = self._torrent.name
        psize = self._torrent.piece_length

        if num_files == 1:
            if spath.is_file() and spath.name == torrent_name:
                pass
            elif spath.is_dir():
                raise IsADirectoryError(f'Expect a single file, not a directory "{spath.name}".')
            else:
                raise FileNotFoundError(f'File "{spath.name}" is not found.')
        elif num_files > 1:
            if spath.is_file():
                raise NotADirectoryError(f'Expect a directory, not a file "{spath.name}".')
            elif spath.is_dir() and spath.name == self.name:
                pass
            else:
                raise RuntimeError(f'Directory "{spath.name}" is not found.')
        else:
            raise TorrentIsEmptyError(f"The torrent instance has no files.")

        self._n_total_files = num_files
        self._total_size = self._torrent.size
        piece_bytes: bytes = b''
        piece_idx: int = 0
        piece_hashes: list[bytes] = self._torrent.pieces_hashes
        errored_pieces: set[int] = set()
        errored_fpaths: set[str] = set()

        relative_path = '.'
        for fileinfo in self._torrent.file_list:
            relative_path = os.path.sep.join(fileinfo.path)
            fpath_wanted = spath / relative_path
            fsize_wanted = fileinfo.size
            fsize_exists = 0

            if fpath_wanted.is_file():
                fsize_exists = fpath_wanted.stat().st_size
                read_quota = min(fsize_wanted, fsize_exists)  # to stop reading if the file is larger than wanted
                fobj = fpath_wanted.open('rb')
                while (read_bytes := fobj.read(min(psize - len(piece_bytes), read_quota))):
                    piece_bytes += read_bytes
                    read_quota -= len(read_bytes)
                    if len(piece_bytes) == psize:  # whole piece loaded
                        if toSHA1(piece_bytes) != piece_hashes[piece_idx]:  # sha1 mismatches
                            errored_pieces.add(piece_idx)
                            errored_fpaths.add(relative_path)
                        piece_idx += 1  # whole piece loaded, piece index increase
                        piece_bytes = b''  # whole piece loaded, clear piece bytes
                        self._read_size += psize
                fobj.close()
                if read_quota: raise RuntimeError('Bug')  #! read_quota must be consumed

            # `size_missing` is used to fill the remainder of the piece with \0 if the file is smaller than wanted
            size_missing = fsize_wanted - fsize_exists
            # TODO: add wrong capitalization check
            if size_missing: errored_fpaths.add(relative_path)
            if size_missing > 0:
                n_affected_piece, left_piece_len = divmod(len(piece_bytes) + size_missing, psize)
                if n_affected_piece == 0:  # the file is smaller than a piece
                    piece_bytes += b'\0' * size_missing
                else:
                    piece_bytes += b'\0' * left_piece_len
                    for _ in range(n_affected_piece):
                        errored_pieces.add(piece_idx)
                        errored_fpaths.add(relative_path)
                        piece_idx += 1

            self._n_files_read += 1
        if piece_bytes and toSHA1(piece_bytes) != piece_hashes[piece_idx]:  # remainder
            errored_pieces.add(piece_idx)
            errored_fpaths.add(relative_path)

        sorter = os_sorted if HAS_NATSORT else sorted
        self._errored_pieces = sorted(errored_pieces)
        self._errored_fpaths = [(PurePath(torrent_name) / p).as_posix() for p in sorter(errored_fpaths)]
