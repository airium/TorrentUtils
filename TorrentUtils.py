import time
import hashlib
import pathlib
import argparse
import operator

import bencoder




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
    def torrent_dict(self):
        torrent_dict = {b'info':{}}

        # keys that not impacts torrent hash
        if self.tracker_list:
            torrent_dict[b'announce'] = bytes(self.tracker_list[0], self.encoding)
        if self.tracker_list[1:]:
            torrent_dict[b'announce-list'] = list(bytes(url, self.encoding) for url in self.tracker_list)
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

        return torrent_dict


    def updateMetadata(self, **metadata_dict):
        for key, value in sorted(metadata_dict.items()):
            # change piece size will reset sha1 hash
            if key == 'n_bytes_piece_size' and value != self.n_bytes_piece_size:
                self.content_sha1_hex_bytes = bytes()
            setattr(self, key, value)

    @staticmethod
    def calSha1Hex(b: bytes, /) -> bytes:
        sha1_hasher = hashlib.sha1()
        sha1_hasher.update(b)
        return bytes.fromhex(sha1_hasher.hexdigest())


    def updateInfoDict(self):
        self.torrent_name = self.content_fpath.name
        fpaths = [self.content_fpath] if self.content_fpath.is_file() else \
                 sorted(filter(operator.methodcaller('is_file'), self.content_fpath.rglob('*')))
        self.content_fpath_list = [fpath.relative_to(self.content_fpath) for fpath in fpaths]
        self.content_fsize_list = [fpath.stat().st_size for fpath in fpaths]
        self.content_sha1_hex_bytes = piece_bytes = bytes()
        for fpath in fpaths:
            with open(fpath, 'rb') as fobj:
                while (read_bytes := fobj.read(self.n_bytes_piece_size - len(piece_bytes))):
                    piece_bytes += read_bytes
                    if len(piece_bytes) == self.n_bytes_piece_size:
                        self.content_sha1_hex_bytes += self.calSha1Hex(piece_bytes)
                        piece_bytes = bytes()
        self.content_sha1_hex_bytes += self.calSha1Hex(piece_bytes) if piece_bytes else b''


    def saveTorrent(self):
        assert self.content_fpath_list, 'There is no file given for the torrent'
        fpath = self.torrent_fpath.with_suffix(f'{"" if no_time_suffix else "." + time.strftime("%Y%m%d-%H%M%S%z")}.torrent')
        if not fpath.exists():
            fpath.write_bytes(bencoder.encode(self.torrent_dict))
        elif fpath.is_file():
            if no_prompt or input(f'A file already exists at \'{self.torrent_fpath}\'\n'
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
        if args.piece_size: ret_metadata_dict['n_bytes_piece_size'] = args.piece_size * 1024
        if args.private: ret_metadata_dict['private'] = args.private
        if args.source: ret_metadata_dict['source'] = args.source

        return ret_metadata_dict


    global no_prompt, no_time_suffix
    no_prompt = True if args.no_prompt else False
    no_time_suffix = True if args.no_time_suffix else False
    ret_mode = args.mode if args.mode else __inferModeFromFpaths(args.fpaths)
    ret_fpaths = __sortFpaths(args.fpaths, ret_mode)
    ret_metadata_dict = __pickMetadata(args)
    return ret_mode, ret_fpaths, ret_metadata_dict




def main(args):
    mode, fpaths_dict, metadata_dict = _resolveArgs(args)
    torrent = Torrent(**fpaths_dict)
    if mode == 'create':
        print(f'Creating a new torrent from {torrent.content_fpath}')
        torrent.updateMetadata(**metadata_dict)
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




if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('fpaths', nargs='+', type=pathlib.Path)
    parser.add_argument('-m', '--mode', choices=('create', 'check', 'verify', 'modify'), default=None)
    parser.add_argument('-t', '--tracker', action='extend', nargs='+', dest='tracker_list', type=str)
    parser.add_argument('-s', '--piece-size', dest='piece_size', default=16384, type=int)
    parser.add_argument('--encoding', dest='encoding', default='utf-8', type=str)
    parser.add_argument('--comment', dest='comment', type=str)
    parser.add_argument('--time', dest='creation_time', default=int(time.time()), type=int)
    parser.add_argument('--tool', dest='creation_tool', default='TorrentUtils', type=str)
    parser.add_argument('--source', dest='source', type=str)
    parser.add_argument('--private', action='store_const', const=1)
    parser.add_argument('-y', '--yes', '--no-prompt', action='store_true', dest='no_prompt')
    parser.add_argument('--no-time-suffix', action='store_true', dest='no_time_suffix')
    main(parser.parse_args())
