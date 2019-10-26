import time
import hashlib
import pathlib
import argparse

import bencoder


class Torrent():

    def __init__(self, torrent_fpath):
        self.torrent_fpath = torrent_fpath
        self.torrent_dict = dict()

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

    def updateInfoDict(self, dest_path=None, n_bytes_piece_size=None, private=False, source=None):
        info_dict = dict()
        info_dict[b'name'] = bytes(dest_path.name, 'utf-8')
        info_dict[b'piece length'] = n_bytes_piece_size
        info_dict[b'pieces'] = bytes()
        if private: info_dict[b'private'] = 1
        if source: info_dict[b'source'] = bytes(source, 'utf-8')
        if dest_path.is_file(): # torrent of single file
            info_dict[b'pieces'] = self._calPiecesSha1Hex([dest_path], n_bytes_piece_size)
            info_dict[b'length'] = dest_path.stat().st_size
        else: # torrent of a directory
            fpaths = sorted(dest_path.rglob('*'))
            info_dict[b'pieces'] = self._calPiecesSha1Hex(fpaths, n_bytes_piece_size)
            info_dict[b'files'] = list()
            for fpath in fpaths:
                if fpath.is_dir():
                    continue
                info_dict[b'files'].append(
                    {b'length': fpath.stat().st_size,
                     b'path': list(bytes(f, 'utf-8') for f in fpath.relative_to(dest_path).parts)})
        self.torrent_dict[b'info'] = info_dict

    def save(self):
        torrent_fpath = self.torrent_fpath.with_suffix(f'.{time.strftime("%Y%m%d-%H%M%S%z")}.torrent')
        assert not torrent_fpath.exists()
        torrent_fpath.write_bytes(bencoder.encode(self.torrent_dict))
        print(f'Torrent saved to {torrent_fpath.absolute()}')


def main(args):
    if args.cmd == 'create':
        print('Creating a new torrent')
        torrent = Torrent(args.fpaths[0])
        torrent.updateInfoDict(args.fpaths[0], 1024 * args.piece_size, args.private)
        torrent.save()
    elif args.cmd == 'check':
        print('Check the torrent integrity')
        raise NotImplementedError
    elif args.cmd == 'verify':
        print('Verify torrent integrity')
        raise NotImplementedError
    elif args.cmd == 'modify':
        print('Modify torrent metadata')
        raise NotImplementedError
    else: # try to infer cmd from `fpaths` as none was given
        if len(args.fpaths) == 1:
            if args.fpaths[0].suffix.lower() == '.torrent':
                print('Assuming you want to check the torrent')
                args.cmd = 'check'
                raise NotImplementedError
            else:
                print('Assuming you want to create a torrent')
                args.cmd = 'create'
                raise NotImplementedError
        elif len(args.fpaths) == 2:
            if args.fpaths[0].suffix.lower() == '.torrent':
                args.cmd = 'verify'
                raise NotImplementedError
            elif args.fpaths[1].suffix.lower() == '.torrent':
                args.cmd = 'verify'
                raise NotImplementedError
            else:
                raise ValueError('You must specify at least one torrent')
        else:
            raise ValueError('Only 2 paths is allowed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('fpaths', nargs='+', type=pathlib.Path)
    parser.add_argument('-c', '--cmd', choices=('create', 'check', 'verify', 'modify'), default=None)
    parser.add_argument('-s', '--piece-size', dest='piece_size', nargs=1, default=16384, type=int)
    parser.add_argument('-p', '--private', action='store_true')
    parser.add_argument('-t', '--tracker', action='extend', nargs='+', type=str)
    parser.add_argument('--comment', nargs=1, type=str)
    main(parser.parse_args())
