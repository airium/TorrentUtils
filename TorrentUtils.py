import re
import time
import shutil
import string
import hashlib
import pathlib
import argparse
import operator
import functools


try:
    import tqdm
except ImportError:
    NO_PROGRESS = True
else:
    NO_PROGRESS = False


NO_PROMPT = False
NO_TIME_SUFFIX = False




def encode(obj, encoding:str='utf-8') -> bytes:
    tobj = type(obj)
    if tobj is bytes:
        ret = str(len(obj)).encode(encoding) + b":" + obj
    elif tobj is str:
        ret = encode(obj.encode(encoding))
    elif tobj is int:
        ret = b"i" + str(obj).encode(encoding) + b"e"
    elif tobj in (list, tuple):
        ret = b"l" + b"".join(map(functools.partial(encode, encoding=encoding), obj)) + b"e"
    elif tobj is dict:
        ret = b'd'
        for key, val in sorted(obj.items()):
            if type(key) in (bytes, str):
                ret += encode(key, encoding) + encode(val, encoding)
            else:
                raise ValueError(f"Dict key must be str or bytes, not {key}:{type(key)}")
        ret += b'e'
    else:
        raise ValueError(f'Input must be int, bytes, list or dict; not {obj}:{type(obj)}')
    return ret




def decode(s:(bytes, str), encoding='ascii'):
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


def calSha1(b:bytes) -> str:
    sha1_hasher = hashlib.sha1()
    sha1_hasher.update(b)
    return sha1_hasher.hexdigest()


def calSha1Hex(b: bytes) -> bytes:
    return bytes.fromhex(calSha1(b))


class Torrent():


    def __init__(self, torrent_fpath, content_fpath):
        self._torrent_fpath = torrent_fpath
        self._content_fpath = content_fpath

        # attributes not initialised in __init__
        # keys that not impacts torrent hash
        self._tracker_list = [] # announce and announce-list
        self._comment_str = '' # comment
        self._creator_str = ''# created by
        self._time_sec_int = 0 # creation date
        self._encoding_str = '' # encoding
        # keys that impacts torrent hash
        self._fpath_list = [] # files
        self._fsize_list = [] # length
        self._torrent_name = '' # name
        self._n_bytes_piece_size = 0 # piece length
        self._content_sha1_str = '' # pieces
        self._private_torrent = 0 # private
        self._source_str = '' # source


    @property
    def announce(self):
        return self._tracker_list[0]

    @property
    def announce_list(self):
        return self._tracker_list

    @property
    def comment(self):
        return self._comment_str

    @property
    def created_by(self):
        return self._creator_str

    @property
    def creation_date(self):
        return self._time_sec_int

    @property
    def encoding(self):
        return self._encoding_str

    @property
    def name(self):
        return self._torrent_name

    @property
    def piece_length(self):
        return self._n_bytes_piece_size >> 10

    @property
    def private(self):
        return self._private_torrent

    @property
    def pieces(self):
        return bytes.fromhex(self._content_sha1_str)


    @property
    def torrent_size(self):
        return sum(self._fsize_list)


    @property
    def torrent_dict(self):
        torrent_dict = {b'info':{}}

        # keys that not impacts torrent hash
        if self._tracker_list:
            torrent_dict[b'announce'] = bytes(self._tracker_list[0], self._encoding_str)
        if self._tracker_list[1:]:
            torrent_dict[b'announce-list'] = list([bytes(url, self._encoding_str)] for url in self._tracker_list)
        if self._comment_str:
            torrent_dict[b'comment'] = bytes(self._comment_str, self._encoding_str)
        if self._time_sec_int:
            torrent_dict[b'creation data'] = self._time_sec_int
        if self._creator_str:
            torrent_dict[b'created by'] = bytes(self._creator_str, self._encoding_str)
        if self._encoding_str:
            torrent_dict[b'encoding'] = bytes(self._encoding_str, self._encoding_str)

        # keys that impacts torrent hash
        if self._fpath_list:
            if len(self._fpath_list) == 1 and not self._fpath_list[0].name:
                torrent_dict[b'info'][b'length'] = self._fsize_list[0]
            else:
                torrent_dict[b'info'][b'files'] = []
                for fpath, fsize in zip(self._fpath_list, self._fsize_list):
                    torrent_dict[b'info'][b'files'].append(
                        {b'length': fsize,
                         b'path': list(bytes(part, self._encoding_str) for part in fpath.parts)})
        if self._torrent_name:
            torrent_dict[b'info'][b'name'] = bytes(self._torrent_name, self._encoding_str)
        if self._n_bytes_piece_size:
            torrent_dict[b'info'][b'piece length'] = self._n_bytes_piece_size
        if self._content_sha1_str:
            torrent_dict[b'info'][b'pieces'] = self.pieces
        if self._private_torrent:
            torrent_dict[b'info'][b'private'] = self._private_torrent
        if self._source_str:
            torrent_dict[b'info'][b'source'] = bytes(self._source_str, self._encoding_str)

        # additional key for check purpose
        torrent_dict[b'hash'] = bytes(calSha1(encode(torrent_dict[b'info'])), self._encoding_str)

        return torrent_dict


    def updateMetadata(self, **metadata_dict):
        for key, value in sorted(metadata_dict.items()):
            if key == 'n_bytes_piece_size':
                # prompt if piece size not 2^n*16KiB or not in [256kiB, 32MiB]
                if value % 262144 or not (262144 <= value <= 33554432):
                    if not NO_PROMPT and \
                       'y' != input(f'The piece size {value>>10} KiB is NOT common.\n'
                                     'Confirm? (enter y to CONFIRM or anything else to cancel): '):
                        print(f'Piece size {self._n_bytes_piece_size>>10} KiB not changed')
                # change piece size will reset sha1 hash
                if value != self._n_bytes_piece_size:
                    self._content_sha1_str = bytes()
            print(key, value)
            setattr(self, key, value)


    def updateInfoDict(self):
        self._torrent_name = self._content_fpath.name
        fpaths = [self._content_fpath] if self._content_fpath.is_file() else \
                 sorted(filter(operator.methodcaller('is_file'), self._content_fpath.rglob('*')))
        self._fpath_list = [fpath.relative_to(self._content_fpath) for fpath in fpaths]
        self._fsize_list = [fpath.stat().st_size for fpath in fpaths]
        if self.torrent_size:
            self._content_sha1_str = str()
            piece_bytes = bytes()
            if not NO_PROGRESS: pbar = tqdm.tqdm(total=self.torrent_size, unit='B', unit_scale=True)
            window_width = shutil.get_terminal_size()[0] // 2
            for fpath in fpaths:
                with open(fpath, 'rb') as fobj:
                    if not NO_PROGRESS: pbar.set_description(str(fpath)[-window_width:], refresh=True)
                    while (read_bytes := fobj.read(self._n_bytes_piece_size - len(piece_bytes))):
                        piece_bytes += read_bytes
                        if len(piece_bytes) == self._n_bytes_piece_size:
                            self._content_sha1_str += calSha1(piece_bytes)
                            piece_bytes = bytes()
                        if not NO_PROGRESS: pbar.update(len(read_bytes))
            self._content_sha1_str += calSha1(piece_bytes) if piece_bytes else b''
            if not NO_PROGRESS: pbar.close()
        else:
            print('No info dict was generated as the torrent size is 0')


    def saveTorrent(self):
        assert self._fpath_list, 'There is no file given for the torrent'
        fpath = self._torrent_fpath.with_suffix(f'{"" if NO_TIME_SUFFIX else "." + time.strftime("%y%m%d-%H%M%S")}.torrent')
        if not fpath.exists():
            fpath.write_bytes(encode(self.torrent_dict))
            print(f'Torrent saved to \'{fpath}\'')
        elif fpath.is_file():
            if NO_PROMPT or \
               'y' == input(f'A file already exists at \'{self._torrent_fpath}\'\n'
                             'Overwrite? (enter y to OVERWRITE, or anything else to cancel): '):
                fpath.unlink()
                fpath.write_bytes(encode(self.torrent_dict))
                print(f'Torrent saved to \'{fpath} (overwritten)\'')
            else:
                print(f'Cancelled')
        if fpath.is_dir():
            raise FileExistsError(f'A directory exists at {fpath.absolute()}\n'
                                   'Please remove it before writing torrent')


    def loadTorrent(self):
        raise NotImplementedError


    def checkTorrent(self):
        raise NotImplementedError


    def verifyContent(self):
        raise NotImplementedError




def _resolveArgs(args):


    def __inferModeFromFpaths(fpaths):
        ret_mode = None

        if len(fpaths) == 1 and fpaths[0].is_dir():
            ret_mode = 'create'
        if len(fpaths) == 1 and fpaths[0].is_file() and fpaths[0].suffix.lower() != '.torrent':
            ret_mode = 'create'
        if len(fpaths) == 1 and fpaths[0].is_file() and fpaths[0].suffix.lower() == '.torrent':
            ret_mode = 'check'
        if len(fpaths) == 2 and fpaths[0].is_file() and fpaths[0].suffix.lower() == '.torrent':
            ret_mode = 'verify'
        if len(fpaths) == 2 and fpaths[1].is_file() and fpaths[1].suffix.lower() == '.torrent':
            ret_mode = 'verify'

        if ret_mode:
            return ret_mode
        raise ValueError('Failed to infer action mode')


    def __sortFpaths(fpaths, mode):
        ret_fpath_dict = {'torrent_fpath':None, 'content_fpath':None}

        if mode == 'create' and len(fpaths) == 1:
            ret_fpath_dict['torrent_fpath'] = fpaths[0].parent.joinpath(fpaths[0].name + '.torrent')
            ret_fpath_dict['content_fpath'] = fpaths[0]
        if mode == 'create' and len(fpaths) == 2 and fpaths[1].is_dir():
            ret_fpath_dict['torrent_fpath'] = fpaths[1].parent.joinpath(fpaths[1].name + '.torrent')
            ret_fpath_dict['content_fpath'] = fpaths[0]
        if mode == 'create' and len(fpaths) == 2 and fpaths[1].is_file():
            ret_fpath_dict['torrent_fpath'] = fpaths[1]
            ret_fpath_dict['content_fpath'] = fpaths[0]
        if mode == 'check' and len(fpaths) == 1 and fpaths[0].is_file():
            ret_fpath_dict['torrent_fpath'] = fpaths[0]
        if mode == 'verify' and len(fpaths) == 2 and fpaths[1].is_file():
            ret_fpath_dict['torrent_fpath'] = fpaths[1]
            ret_fpath_dict['content_fpath'] = fpaths[0]
        if mode == 'modfiy' and len(fpaths) == 1 and fpaths[0].is_file():
            ret_fpath_dict['torrent_fpath'] = fpaths[0]

        if ret_fpath_dict['torrent_fpath']:
            return ret_fpath_dict
        raise ValueError


    def __pickMetadata(args):
        ret_metadata_dict = dict()

        if args.tracker_list: ret_metadata_dict['_tracker_list'] = args.tracker_list
        if args.comment: ret_metadata_dict['_comment_str'] = args.comment
        if args.creation_tool: ret_metadata_dict['_creator_str'] = args.creation_tool
        if args.creation_time: ret_metadata_dict['_time_sec_int'] = args.creation_time
        if args.encoding: ret_metadata_dict['_encoding_str'] = args.encoding
        if args.piece_size: ret_metadata_dict['_n_bytes_piece_size'] = args.piece_size << 10
        if args.private: ret_metadata_dict['_private_torrent'] = args.private
        if args.source: ret_metadata_dict['_source'] = args.source

        return ret_metadata_dict


    global NO_PROMPT, NO_TIME_SUFFIX, NO_PROGRESS
    NO_PROMPT = True if args.no_prompt else False
    NO_TIME_SUFFIX = True if args.no_time_suffix else False
    if NO_PROGRESS and not args.no_progress: # tqdm is not installed but want to use
        print('I: \'tqdm\' is not installed so no progress bar will be shown')
    else:
        NO_PROGRESS = True if args.no_progress else False
    ret_mode = args.mode if args.mode else __inferModeFromFpaths(args.fpaths)
    ret_fpaths = __sortFpaths(args.fpaths, ret_mode)
    ret_metadata_dict = __pickMetadata(args)
    return ret_mode, ret_fpaths, ret_metadata_dict




def main(args):
    mode, fpaths_dict, metadata_dict = _resolveArgs(args)
    torrent = Torrent(**fpaths_dict)
    if mode == 'create':
        torrent.updateMetadata(**metadata_dict)
        print(f'Creating a new torrent from \'{torrent._content_fpath}\'')
        torrent.updateInfoDict()
        torrent.saveTorrent()
    elif mode == 'check':
        torrent.loadTorrent()
        torrent.checkTorrent()
    elif mode == 'verify':
        torrent.loadTorrent()
        torrent.verifyContent()
    elif mode == 'modify':
        torrent.loadTorrent()
        torrent.updateMetadata(**metadata_dict)
        torrent.saveTorrent()
    else:
        raise ValueError




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
    parser = argparse.ArgumentParser(prog='TorrentUtils',
                                     formatter_class=lambda prog: _CustomHelpFormatter(prog))
    parser.add_argument('fpaths', nargs='+', type=pathlib.Path,
                        help='1 or 2 paths depending on mode', metavar='path')
    parser.add_argument('-m', '--mode', choices=('create', 'check', 'verify', 'modify'), default=None,
                        help='will be guessed from fpaths if not specified')
    parser.add_argument('-t', '--tracker', action='extend', nargs='+', dest='tracker_list', type=str,
                        help='can be specified multiple times', metavar='url')
    parser.add_argument('-s', '--piece-size', dest='piece_size', default=16384, type=int,
                        help='piece size in KiB (default: 16384KiB)', metavar='number')
    parser.add_argument('-c', '--comment', dest='comment', type=str,
                        help='the message displayed in various clients', metavar='text')
    parser.add_argument('-p', '--private', choices={0,1}, type=int,
                        help='private torrent if 1 (default: 0)')
    parser.add_argument('--tool', dest='creation_tool', default='TorrentUtils', type=str,
                        help='customise `created by` message (default: TorrentUtils)', metavar='text')
    parser.add_argument('--time', dest='creation_time', default=int(time.time()), type=int,
                        help='customise the second since 19700101 (default: now)', metavar='number')
    parser.add_argument('--source', dest='source', type=str,
                        help='customise `source` message (will change torrent hash)', metavar='text')
    parser.add_argument('--encoding', dest='encoding', default='utf-8', type=str,
                        help='customise encoding for filenames (default: utf-8)', metavar='text')
    parser.add_argument('-y', '--yes', '--no-prompt', action='store_true', dest='no_prompt',
                        help='don\'t prompt any interactive question')
    parser.add_argument('--no-time-suffix', action='store_true', dest='no_time_suffix',
                        help='don\'t add the current time in new torrent\'s name')
    parser.add_argument('--no-progress', action='store_true', dest='no_progress',
                        help='don\'t print any progress info')
    parser.add_argument('--version', action='version', version='%(prog)s 0.5')
    main(parser.parse_args())
