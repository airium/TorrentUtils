import time
import shutil
import hashlib
import pathlib
import argparse
import operator


import tqdm
import bencoder


NO_PROMPT = False
NO_TIME_SUFFIX = False




class Torrent():


    def __init__(self, torrent_fpath, content_fpath):
        self.torrent_fpath = torrent_fpath
        self.content_fpath = content_fpath

        # attributes not initialised in __init__
        # keys that not impacts torrent hash
        self.tracker_list = [] # announce and announce-list
        self.comment = '' # comment
        self.creation_tool = ''# created by
        self.creation_time = 0 # creation date
        self.encoding = '' # encoding
        # keys that impacts torrent hash
        self.content_fpath_list = [] # files
        self.content_fsize_list = [] # length
        self.torrent_name = '' # name
        self.n_bytes_piece_size = 0 # piece length
        self.content_sha1_hex_bytes = bytes() # pieces
        self.private = 0 # private
        self.source = '' # source


    @property
    def piece_size(self):
        return self.n_bytes_piece_size >> 10


    @property
    def torrent_size(self):
        return sum(self.content_fsize_list)


    @property
    def torrent_dict(self):
        torrent_dict = {b'info':{}}

        # keys that not impacts torrent hash
        if self.tracker_list:
            torrent_dict[b'announce'] = bytes(self.tracker_list[0], self.encoding)
        if self.tracker_list[1:]:
            torrent_dict[b'announce-list'] = list(bytes(url, self.encoding) for url in self.tracker_list)
        if self.comment:
            torrent_dict[b'comment'] = bytes(self.comment, self.encoding)
        if self.creation_time:
            torrent_dict[b'creation data'] = self.creation_time
        if self.creation_tool:
            torrent_dict[b'created by'] = bytes(self.creation_tool, self.encoding)
        if self.encoding:
            torrent_dict[b'encoding'] = bytes(self.encoding, self.encoding)

        # keys that impacts torrent hash
        if self.content_fpath_list:
            if len(self.content_fpath_list) == 1:
                torrent_dict[b'info'][b'length'] = self.content_fsize_list[0]
            else:
                torrent_dict[b'info'][b'files'] = []
                for fpath, fsize in zip(self.content_fpath_list, self.content_fsize_list):
                    torrent_dict[b'info'][b'files'].append(
                        {b'length': fsize,
                         b'path': list(bytes(part, self.encoding) for part in fpath.parts)})
        if self.torrent_name:
            torrent_dict[b'info'][b'name'] = bytes(self.torrent_name, self.encoding)
        if self.n_bytes_piece_size:
            torrent_dict[b'info'][b'piece length'] = self.n_bytes_piece_size
        if self.content_sha1_hex_bytes:
            torrent_dict[b'info'][b'pieces'] = self.content_sha1_hex_bytes
        if self.private:
            torrent_dict[b'info'][b'private'] = self.private
        if self.source:
            torrent_dict[b'info'][b'source'] = bytes(self.source, self.encoding)

        # additional key for check purpose
        torrent_dict[b'hash'] = bytes(self.calSha1(bencoder.encode(torrent_dict[b'info'])), self.encoding)

        return torrent_dict


    @staticmethod
    def calSha1(b:bytes, /) -> str:
        sha1_hasher = hashlib.sha1()
        sha1_hasher.update(b)
        return sha1_hasher.hexdigest()


    @staticmethod
    def calSha1Hex(b: bytes, /) -> bytes:
        sha1_hasher = hashlib.sha1()
        sha1_hasher.update(b)
        return bytes.fromhex(sha1_hasher.hexdigest())


    def updateMetadata(self, **metadata_dict):
        for key, value in sorted(metadata_dict.items()):
            if key == 'n_bytes_piece_size':
                # prompt if piece size not 2^n*16KiB or not in [256kiB, 32MiB]
                if value % 262144 or not (262144 < value < 33554432):
                    if not NO_PROMPT and \
                       'y' != input(f'The piece size {value>>10} KiB is NOT common.\n'
                                     'Confirm? (enter y to CONFIRM or anything else to cancel): '):
                        print(f'Piece size {self.n_bytes_piece_size>>10} KiB not changed')
                # change piece size will reset sha1 hash
                if value != self.n_bytes_piece_size:
                    self.content_sha1_hex_bytes = bytes()
            setattr(self, key, value)


    def updateInfoDict(self):
        self.torrent_name = self.content_fpath.name
        fpaths = [self.content_fpath] if self.content_fpath.is_file() else \
                 sorted(filter(operator.methodcaller('is_file'), self.content_fpath.rglob('*')))
        self.content_fpath_list = [fpath.relative_to(self.content_fpath) for fpath in fpaths]
        self.content_fsize_list = [fpath.stat().st_size for fpath in fpaths]
        if self.torrent_size:
            self.content_sha1_hex_bytes = piece_bytes = bytes()
            pbar = tqdm.tqdm(total=self.torrent_size, unit='B', unit_scale=True)
            window_width = shutil.get_terminal_size()[0] // 2
            for fpath in fpaths:
                with open(fpath, 'rb') as fobj:
                    pbar.set_description(str(fpath)[-window_width:], refresh=True)
                    while (read_bytes := fobj.read(self.n_bytes_piece_size - len(piece_bytes))):
                        piece_bytes += read_bytes
                        if len(piece_bytes) == self.n_bytes_piece_size:
                            self.content_sha1_hex_bytes += self.calSha1Hex(piece_bytes)
                            piece_bytes = bytes()
                        pbar.update(len(read_bytes))
            self.content_sha1_hex_bytes += self.calSha1Hex(piece_bytes) if piece_bytes else b''
            pbar.close()
        else:
            print('No info dict was generated as the torrent size is 0')


    def saveTorrent(self):
        assert self.content_fpath_list, 'There is no file given for the torrent'
        fpath = self.torrent_fpath.with_suffix(f'{"" if NO_TIME_SUFFIX else "." + time.strftime("%y%m%d-%H%M%S")}.torrent')
        if not fpath.exists():
            fpath.write_bytes(bencoder.encode(self.torrent_dict))
            print(f'Torrent saved to {fpath}')
        elif fpath.is_file():
            if NO_PROMPT or \
               'y' == input(f'A file already exists at \'{self.torrent_fpath}\'\n'
                             'Overwrite? (enter y to OVERWRITE, or anything else to cancel): '):
                fpath.unlink()
                fpath.write_bytes(bencoder.encode(self.torrent_dict))
                print(f'Torrent saved to {fpath} (overwritten)')
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

        if args.tracker_list: ret_metadata_dict['tracker_list'] = args.tracker_list
        if args.comment: ret_metadata_dict['comment'] = args.comment
        if args.creation_tool: ret_metadata_dict['creation_tool'] = args.creation_tool
        if args.creation_time: ret_metadata_dict['creation_time'] = args.creation_time
        if args.encoding: ret_metadata_dict['encoding'] = args.encoding
        if args.piece_size: ret_metadata_dict['n_bytes_piece_size'] = args.piece_size << 10
        if args.private: ret_metadata_dict['private'] = args.private
        if args.source: ret_metadata_dict['source'] = args.source

        return ret_metadata_dict


    global NO_PROMPT, NO_TIME_SUFFIX
    NO_PROMPT = True if args.no_prompt else False
    NO_TIME_SUFFIX = True if args.no_time_suffix else False
    ret_mode = args.mode if args.mode else __inferModeFromFpaths(args.fpaths)
    ret_fpaths = __sortFpaths(args.fpaths, ret_mode)
    ret_metadata_dict = __pickMetadata(args)
    return ret_mode, ret_fpaths, ret_metadata_dict




def main(args):
    mode, fpaths_dict, metadata_dict = _resolveArgs(args)
    torrent = Torrent(**fpaths_dict)
    if mode == 'create':
        torrent.updateMetadata(**metadata_dict)
        print(f'Creating a new torrent from {torrent.content_fpath}')
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
    parser.add_argument('--version', action='version', version='%(prog)s 0.5')
    main(parser.parse_args())
