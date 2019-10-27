import time
import hashlib
import pathlib
import argparse

import bencoder




class Torrent():


    def __init__(self, torrent_fpath, content_fpath):
        self.torrent_fpath = torrent_fpath
        self.content_fpath = content_fpath
        self.info_dict = dict()

        # attributes not initialised in __init__
        self.n_bytes_piece_size = 0
        self.tracker_list = []
        self.creation_tool = ''
        self.creation_time = 0
        self.encoding = ''
        self.comment = ''
        self.source = ''
        self.private = 0


    @staticmethod
    def calSha1Hex(b: bytes, /) -> bytes:
        sha1_hasher = hashlib.sha1()
        sha1_hasher.update(b)
        return bytes.fromhex(sha1_hasher.hexdigest())


    def _calPiecesSha1Hex(self, fpaths, n_bytes_piece_size):
        pieces_sha1_hex_bytes = bytes()
        piece_bytes = bytes()
        for fpath in fpaths:
            if fpath.is_dir():
                continue
            with open(fpath, 'rb') as fobj:
                while (read_bytes := fobj.read(n_bytes_piece_size - len(piece_bytes))):
                    piece_bytes += read_bytes
                    if len(piece_bytes) == n_bytes_piece_size:
                        pieces_sha1_hex_bytes += self.calSha1Hex(piece_bytes)
                        piece_bytes = bytes()
        pieces_sha1_hex_bytes += self.calSha1Hex(piece_bytes) if piece_bytes else b''
        return pieces_sha1_hex_bytes


    self.loadTorrent(self):
        raise NotImplementedError


    self.checkTorrent(self):
        raise NotImplementedError


    def updateInfoDict(self):
        info_dict = dict()
        info_dict[b'name'] = bytes(self.content_fpath.name, 'utf-8')
        info_dict[b'piece length'] = self.n_bytes_piece_size
        info_dict[b'pieces'] = bytes()
        if self.private: info_dict[b'private'] = 1
        if self.source: info_dict[b'source'] = bytes(self.source, 'utf-8')
        if self.content_fpath.is_file(): # torrent of single file
            info_dict[b'pieces'] = self._calPiecesSha1Hex([self.content_fpath], self.n_bytes_piece_size)
            info_dict[b'length'] = self.content_fpath.stat().st_size
        else: # torrent of a directory
            fpaths = sorted(self.content_fpath.rglob('*'))
            info_dict[b'pieces'] = self._calPiecesSha1Hex(fpaths, self.n_bytes_piece_size)
            info_dict[b'files'] = list()
            for fpath in fpaths:
                if fpath.is_dir():
                    continue
                info_dict[b'files'].append(
                    {b'length': fpath.stat().st_size,
                     b'path': list(bytes(f, 'utf-8') for f in fpath.relative_to(self.content_fpath).parts)})
        self.info_dict[b'info'] = info_dict


    self.updateMetaData(self):
        raise NotImplementedError


    def save(self):
        torrent_fpath = self.torrent_fpath.with_suffix(f'.{time.strftime("%Y%m%d-%H%M%S%z")}.torrent')
        assert not torrent_fpath.exists()
        torrent_fpath.write_bytes(bencoder.encode(self.info_dict))
        print(f'Torrent saved to {torrent_fpath.absolute()}')




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
        raise ValueError


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
        if args.creation_tool: ret_metadata_dict['creation_tool'] = args.creation_tool
        if args.creation_time: ret_metadata_dict['creation_time'] = args.creation_time
        if args.encoding: ret_metadata_dict['encoding'] = args.encoding
        if args.comment: ret_metadata_dict['comment'] = args.comment
        if args.source: ret_metadata_dict['source'] = args.source
        if args.private: ret_metadata_dict['private'] = args.private

        return ret_metadata_dict


    ret_mode = args.mode if args.mode else __inferModeFromFpaths(args.fpaths)
    ret_fpaths = __sortFpaths(args.fpaths, ret_mode)
    ret_metadata_dict = __pickMetadata(args)
    return ret_mode, ret_fpaths, ret_metadata_dict




def main(args):
    mode, fpaths_dict, metadata_dict = _resolveArgs(args)
    torrent = Torrent(**fpaths_dict)
    if mode == 'create':
        torrent.updateMetaData(**metadata_dict)
        torrent.updateInfoDict()
        torrent.save()
    elif mode == 'check':
        torrent.loadTorrent()
        torrent.checkTorrent()
    elif mode == 'verify':
        torrent.loadTorrent()
        torrent.verifyContent()
    elif mode == 'modify':
        torrent.loadTorrent()
        torrent.updateMetadata(**metadata_dict)
        torrent.save()
    else:
        raise ValueError




if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('fpaths', nargs='+', type=pathlib.Path)
    parser.add_argument('-m', '--mode', choices=('create', 'check', 'verify', 'modify'), default=None)
    parser.add_argument('-t', '--tracker', action='extend', nargs='+', dest='tracker_list', type=str)
    parser.add_argument('-s', '--piece-size', dest='piece_size', nargs=1, default=16384, type=int)
    parser.add_argument('--encoding', nargs=1, dest='encoding', type=str)
    parser.add_argument('--comment', nargs=1, dest='comment', type=str)
    parser.add_argument('--time', nargs=1, dest='creation_time', type=int)
    parser.add_argument('--tool', nargs=1, dest='creation_tool', type=int)
    parser.add_argument('--source', nargs=1, dest='source', type=str)
    parser.add_argument('--private', action='store_true')
    main(parser.parse_args())
