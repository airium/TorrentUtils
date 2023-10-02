import sys
import math
import json
import shutil
import pathlib
import argparse
from collections import namedtuple

from torrent import Torrent




class _Path(type(pathlib.Path())):

    def isF(self):
        '''Is file (not torrent).'''
        return self.is_file() and self.suffix.lower() != '.torrent'

    def isVF(self, path):
        '''Is virtual file (not torrent).'''
        return not self.is_dir() and self.suffix.lower() != '.torrent'

    def isT(self):
        '''Is torrent.'''
        return self.is_file() and self.suffix.lower() == '.torrent'

    def isVT(self):
        '''Is virtual torrent.'''
        return not self.is_dir() and self.suffix.lower() == '.torrent'

    def isD(self):
        '''Is directory.'''
        return self.is_dir()

    def isVD(self):
        '''Is virtual directory.'''
        return self.is_dir() or not self.is_file()




class Main():

    def __init__(self, args):
        self.torrent = Torrent()

        # extract cli config from cli arguments
        self.cfg = self.__pickCliCfg(args)
        # infer `mode` from the properties of supplied paths if not specified by the user
        self.mode = self.__pickMode(args.mode, args.fpaths)
        # pick the most appropriate paths for torrent and source path
        self.tpath, self.spath = self.__pickPath(args.fpaths, self.mode)
        # try loading user-defined preset for metadata
        self.metadata = self.__loadPreset(args.preset, self.mode)
        # extract metadata from cli arguments
        self.metadata = self.__pickMetadata(args, self.mode, self.metadata)

    @staticmethod
    def __pickCliCfg(args):
        if args.show_progress and 'tqdm' not in globals().keys():
            print("I: Progress bar won't be shown as not installed, consider `python3 -m pip install tqdm`.")
            args.show_progress = False
        cfg = namedtuple('CFG', '     show_prompt       show_progress       with_time_suffix'
                         )(args.show_prompt, args.show_progress, args.with_time_suffix)
        return cfg

    @staticmethod
    def __pickMode(mode, fpaths):
        '''Pick mode from paths is limited: some modes cannot be inferred.'''
        if mode:

            if mode not in ('create', 'print', 'modify', 'verify'):
                Main.__exit('E: unexpected error in mode picker, please file a bug report.')

        else:  # mode == False

            if len(fpaths) == 1:
                if fpaths[0].isD() or fpaths[0].isF():  # 1:F/D -> c
                    mode = 'create'
                elif fpaths[0].isT():  # 1:T -> p
                    mode = 'print'
                else:
                    Main.__exit(f"E: You supplied '{fpaths[0]}' cannot suggest a working mode as it does not exist.")

            elif len(fpaths) == 2:
                # inferred as `create` mode requires 1 existing and 1 virtual path
                if fpaths[0].isVD() and fpaths[1].isF():  # 1:D(v) 2:F = c
                    mode = 'create'
                elif (fpaths[0].isF() or fpaths[0].isD()) and fpaths[1].isVD():  # 1:F/D 2:D(v) = c
                    mode = 'create'
                # inferred as `verify` requires both paths existing
                elif fpaths[0].isT() and (fpaths[1].isF() or fpaths[1].isD()):  # 1:T 2:F/D = v
                    mode = 'verify'
                elif (fpaths[0].isF() or fpaths[0].isD()) and fpaths[1].isT():  # 1:F/D 2:T = v
                    mode = 'verify'
                else:
                    Main.__exit(f"E: You supplied '{fpaths[0]}' and '{fpaths[1]}' cannot suggest a working mode.")

            else:
                Main.__exit(f"E: Expect 1 or 2 positional paths, not {len(fpaths)}.")

        print(f"I: Working mode is '{mode}'.")
        return mode

    @staticmethod
    def __pickPath(fpaths, mode):
        '''Based on the working mode, sort out the most proper paths for torrent and content.'''
        spath = None  # Source PATH is the path to the files specified by a torrent
        tpath = None  # Torrent PATH is the path to the torrent itself

        # `create` mode requires 1 or 2 paths
        # spath must exist, while tpath can be virtual
        if mode == 'create':
            if len(fpaths) == 1:
                if fpaths[0].exists():  # 1:F/D/T
                    spath = fpaths[0]
                    tpath = spath.parent.joinpath(f"{spath.name}.torrent")
                else:
                    Main.__exit(f"E: The source path '{fpaths[0]}' does not exist.")
            elif len(fpaths) == 2:
                if fpaths[0].isVD() and fpaths[1].isF():  # 1:D(v) 2:F
                    spath = fpaths[1]
                    tpath = fpaths[0].joinpath(f"{spath.name}.torrent")
                elif (fpaths[0].isD() or fpaths[0].isF()) and fpaths[1].isVD():  # 1:F/D 2:D(v)
                    spath = fpaths[0]
                    tpath = fpaths[1].joinpath(f"{spath.name}.torrent")
                elif fpaths[0].isVT() and (fpaths[1].isD() or fpaths[1].isF()):  # 1:T(v) 2:F/D
                    spath = fpaths[1]
                    tpath = fpaths[0]
                elif (fpaths[0].isD() or fpaths[0].isF()) and fpaths[1].isVT():  # 1:F/D 2:T(v)
                    spath = fpaths[0]
                    tpath = fpaths[1]
                elif fpaths[0].isT() and fpaths[1].isVT():  # 1:T 2:T(v)
                    spath = fpaths[0]
                    tpath = fpaths[1]
                elif fpaths[0].isVT() and fpaths[1].isT():  # 1:T(v) 2:T
                    spath = fpaths[1]
                    tpath = fpaths[0]
                else:
                    Main.__exit('E: You supplied paths cannot work in `create` mode.')
            else:
                Main.__exit(f"E: `create` mode expects 1 or 2 paths, not {len(fpaths)}.")
            if spath == tpath:  # stop 1:T=2:T
                Main.__exit('E: Source and torrent path cannot be same.')
            if spath.is_file() and spath.suffix.lower() == '.torrent':  # warn spath:T
                print('W: You are likely to create torrent from torrent, which may be unexpected.')

        # `print` mode requires exactly 1 path
        # the path must be an existing tpath
        elif mode == 'print':
            if len(fpaths) == 1:
                if fpaths[0].isT():
                    tpath = fpaths[0]
                else:
                    Main.__exit(f"E: `print` mode expects a valid torrent path, not {fpaths[0]}.")
            else:
                Main.__exit(f"E: `print` mode expects exactly 1 path, not {len(fpaths)}.")

        # `verify` mode requires exactly 2 paths
        # inferred as `verify` requires both paths existing
        elif mode == 'verify':
            if len(fpaths) == 2:
                if fpaths[0].isT() and (fpaths[1].isF() or fpaths[1].isD()):
                    spath = fpaths[1]
                    tpath = fpaths[0]
                elif (fpaths[0].isF() or fpaths[0].isD()) and fpaths[1].isT():
                    spath = fpaths[0]
                    tpath = fpaths[1]
                else:
                    Main.__exit('E: `verify` mode expects a pair of valid source and torrent paths, but not found.')
            else:
                Main.__exit(f"E: `verify` mode expects exactly 2 paths, not {len(fpaths)}.")

        # `modify` mode requires 1 or 2 paths
        elif mode == 'modify':
            if 1 <= len(fpaths) <= 2:
                if fpaths[0].isT():
                    spath = fpaths[0]
                    tpath = spath if not fpaths[1:] else (
                            fpaths[1].joinpath(spath.name) if fpaths[1].is_dir() else (
                            fpaths[1] if fpaths[1].suffix.lower() == '.torrent' else \
                            fpaths[1].parent.joinpath(f"{fpaths[1].name}.torrent")))
                    if spath == tpath:
                        print('W: You are likely to overwrite the source torrent, which may be unexpected.')
                else:
                    Main.__exit(f"E: `modify` mode expects a valid torrent path, not {fpaths[0]}.")
            else:
                Main.__exit(f"E: `modify` mode expects 1 or 2 paths, not {len(fpaths)}.")

        else:
            Main.__exit('E: Unexpected point reached in path picker, please file a bug report.')

        return tpath, spath

    @staticmethod
    def __loadPreset(path, mode):
        metadata = dict()
        if mode != 'create':
            return metadata

        # prepare a preset candidate to read
        preset_path = None
        if path:
            preset_path = _Path(path).absolute()
            if not preset_path.is_file():
                Main.__exit(f"The preset file '{path}' does not exist.")
            if preset_path.suffix not in ('.json', '.torrent'):
                Main.__exit(f"E: Expect json or torrent to read presets, not '{path}'.")
        else:
            exec_path = sys.executable if getattr(sys, 'frozen', False) else __file__
            for ext in ('.json', '.torrent'):
                if (_ := _Path(exec_path).absolute().with_suffix(ext)).is_file():
                    preset_path = _
                    break

        # try read the preset file
        if preset_path:
            try:
                print(f"I: Loading user presets from '{preset_path}'...", end=' ', flush=True)
                if preset_path.suffix == '.torrent':
                    (d := Torrent()).read(preset_path)
                elif preset_path.suffix == '.json':
                    d = json.loads(preset_path.read_bytes())
                else:
                    Main.__exit('E: Unexpected point reached in loading preset, please file a bug report.')

                if _ := d.get('tracker_list'):
                    if isinstance(_, list) and all(isinstance(i, str) for i in _):
                        metadata['tracker_list'] = _
                    else:
                        print('W: tracker list is not loaded as incorrect format.')
                if d.get('comment'): metadata['comment'] = str(d.get('comment'))
                if d.get('created_by'): metadata['created_by'] = str(d.get('created_by'))
                if d.get('creation_date'):
                    if preset_path.suffix == '.torrent':
                        pass  # don't copy date if preset is a torrent file
                    else:
                        metadata['creation_date'] = int(d.get('creation_date'))
                if d.get('encoding'): metadata['encoding'] = str(d.get('encoding'))
                if d.get('piece_size'):
                    metadata['piece_size'] = int(d.get('piece_size'))
                    if preset_path.suffix != '.torrent':
                        metadata['piece_size'] = int(d.get('piece_size')) << 10
                if d.get('private'): metadata['private'] = int(d.get('private'))
                if d.get('source'): metadata['source'] = str(d.get('source'))
            except FileNotFoundError:
                Main.__exit('failed (file not found)')
            except UnicodeDecodeError:
                Main.__exit('failed (invalid file)')
            except json.decoder.JSONDecodeError:
                Main.__exit('failed (invalid file)')
            except BdecodeError:
                Main.__exit('failed (invalid file)')
            except KeyError:
                Main.__exit('failed (missing key)')
            else:
                print('succeeded')

        return metadata

    @staticmethod
    def __pickMetadata(args, mode, metadata):

        if mode == 'create':
            metadata['tracker_list'] = args.tracker_list if args.tracker_list else (
                _ if (_ := metadata.get('tracker_list')) else []
                )
            metadata['comment'] = args.comment if args.comment else (_ if (_ := metadata.get('comment')) else '')
            metadata['created_by'] = args.created_by if args.created_by else (
                _ if (_ := metadata.get('created_by')) else 'https://github.com/airium/TorrentUtils'
                )
            metadata['creation_date'] = args.creation_date if args.creation_date else (
                _ if (_ := metadata.get('creation_date')) else int(time.time())
                )
            metadata['encoding'] = args.encoding if args.encoding else (
                _ if (_ := metadata.get('encoding')) else 'UTF-8'
                )
            metadata['piece_size'] = args.piece_size << 10 if args.piece_size else (
                _ if (_ := metadata.get('piece_size')) else 4096 << 10
                )  # B -> KiB
            metadata['private'] = args.private if args.private else (_ if (_ := metadata.get('private')) else 0)
            metadata['source'] = args.source if args.source else (_ if (_ := metadata.get('source')) else '')

        elif mode == 'modify':
            if not (args.tracker_list is None): metadata['tracker_list'] = args.tracker_list
            if not (args.comment is None): metadata['comment'] = args.comment
            if not (args.created_by is None): metadata['created_by'] = args.created_by
            if not (args.creation_date is None): metadata['creation_date'] = args.creation_date
            if not (args.encoding is None): metadata['encoding'] = args.encoding
            if not (args.piece_size is None):
                print('W: supplied piece size has no effect in `modify` mode.')
                if 'piece_size' in metadata.keys():  # if piece_size is loaded from json, remove it
                    metadata.pop('piece_size')
            if not (args.private is None): metadata['private'] = args.private
            if not (args.source is None): metadata['source'] = args.source

        else:  # `print` or `verify`
            if not (args.tracker_list is None): print(f"W: supplied tracker has not effect in {mode} mode.")
            if not (args.comment is None): print(f"W: supplied comment has not effect in {mode} mode.")
            if not (args.created_by is None): print(f"W: supplied creator has not effect in {mode} mode.")
            if not (args.creation_date is None): print(f"W: supplied time has not effect in {mode} mode.")
            if not (args.encoding is None): print(f"W: supplied encoding has not effect in {mode} mode.")
            if not (args.piece_size is None): print(f"W: supplied piece size has not effect in {mode} mode.")
            if not (args.private is None): print(f"W: supplied private attribute has not effect in {mode} mode.")
            if not (args.source is None): print(f"W: supplied source has not effect in {mode} mode.")

        return metadata

    @staticmethod
    def __exit(chars=''):
        input(chars + '\nTerminated. (Press ENTER to exit)')
        sys.exit()

    def __prompt(self, chars):
        if (not self.cfg.show_prompt) or input(chars).lower() in ('y', 'yes'):
            return True
        else:
            return False

    def __call__(self):
        if self.mode == 'create':
            print(f"I: Creating torrent from '{self.spath}'.")
            self._set()
            self._load()
            self._write()
        elif self.mode == 'print':
            self._read()
            self._print()
        elif self.mode == 'verify':
            print('I: Verifying Source files with Torrent.')
            print(f"Source: '{self.spath}'")
            print(f"Torrent: '{self.tpath}'")
            self._read()
            self._verify()
        elif self.mode == 'modify':
            print(f"I: Modifying torrent '{self.spath}'.")
            self._read()
            self._set()
            self._write()
        else:
            self.__exit(f"Invalid mode: {self.mode}.")

        print()
        input('Press ENTER to exit...')

    def _print(self):
        tname = self.torrent.name
        tsize = self.torrent.torrent_size
        tencd = self.torrent.encoding
        thash = self.torrent.hash
        fsize = self.torrent.size
        fnum = len(self.torrent.file_list)
        psize = self.torrent.piece_length >> 10
        pnum = self.torrent.num_pieces
        tdate = time.strftime('%Y/%m/%d %H:%M:%S', time.localtime(self.torrent.creation_date)) \
                if self.torrent.creation_date else ''
        tfrom = self.torrent.created_by if self.torrent.created_by else ''
        tpriv = 'Private' if self.torrent.private else 'Public'
        tsour = self.torrent.source
        tcomm = self.torrent.comment

        width = shutil.get_terminal_size()[0]

        print(f'General Info ' + '-' * (width-14))
        print(f"Name: {tname}")
        print(f"File: {tsize:,} Bytes, Bencoded" + (f" with {tencd}" if tencd else ''))
        print(f"Hash: {thash}")
        print(
            f"Size: {fsize:,} Bytes" + f", {fnum} File" + ('s' if fnum > 1 else '') + f", {psize} KiB x {pnum} Pieces"
            )
        if tdate and tfrom:
            print(f"Time: {tdate} by {tfrom}")
        elif tdate:
            print(f"Time: {tdate}")
        elif tfrom:
            print(f"From: {tdate}")
        if tcomm:
            print(f"Comm: {tcomm}")
        print(f"Else: {tpriv} torrent" + (f" by {tsour}" if tsour else ''))

        print(f'Trackers ' + '-' * (width-10))
        if self.torrent.tracker_list:
            trnum = math.ceil(math.log10(len(self.torrent.tracker_list))) if self.torrent.tracker_list else 0
            for i, url in enumerate(self.torrent.tracker_list, start=1):
                print(eval("f'{i:0>" + str(trnum) + "}: {url}'"))
        else:
            print('No tracker')

        print(f'Files ' + '-' * (width-7))
        if fnum == 1:
            print(f'1: {tname}')
        else:
            fnum = math.ceil(math.log10(fnum)) if fnum else 0
            for i, (fsize, fpath) in enumerate(self.torrent.file_list, start=1):
                print(eval("f'{i:0>" + str(fnum) + "}: {os.path.join(fpath[0], *fpath[1:])} ({fsize:,} bytes)'"))
                if i == 500 and self.cfg.show_prompt:
                    print('Truncated at 500 files (use -y/--yes to list all)')
                    break

    def _load(self):
        try:
            self.torrent.load(self.spath, False, self.cfg.show_progress)
        except EmptySourceSize:
            self.__exit(f"The source path '{self.spath.absolute()}' has a total size of 0.")

    def _read(self):
        if self.mode in ('verify', 'print'):
            self.torrent.read(self.tpath)
        elif self.mode == 'modify':
            self.torrent.read(self.spath)
        else:
            self.__exit(f"Unexpected {self.mode} mode for read operation.")

    def _verify(self):
        spath = self.spath
        tname = self.torrent.name

        if self.torrent.num_files == 1:
            if spath.is_file() and spath.name == tname:
                spath = self.spath
            elif spath.is_dir():
                if _Path(tname) in spath.iterdir() and (tmp := spath.joinpath(tname)).is_file():
                    spath = tmp
                else:
                    self.__exit(f"E: The source file '{spath}' was not found.")
        elif self.torrent.num_files > 1:
            if spath.is_file():
                self.__exit(f"E: The source directory '{spath}' was not found.")
            elif spath.is_dir():
                if spath.name == tname:
                    spath = spath
                elif _Path(tname) in spath.iterdir() and (tmp := spath.joinpath(self.name)).is_dir():
                    spath = tmp
                else:
                    self.__exit(f"E: The source directory '{spath}' was not found.")

        piece_broken_list = self.torrent.verify(spath)
        ptotal = self.torrent.num_pieces
        pbroken = len(piece_broken_list)
        ppassed = ptotal - pbroken

        files_broken_list = [self.torrent[i] for i in piece_broken_list]
        files_broken_list = list(dict.fromkeys(chain(*files_broken_list)))
        ftotal = self.torrent.num_files
        fbroken = len(files_broken_list)
        fpassed = ftotal - fbroken

        print('Processing...')
        print(f"Piece: {ptotal:>10d} total = {ppassed:>10d} passed + {pbroken:>10d} missing or broken")
        print(f"Files: {ftotal:>10d} total = {fpassed:>10d} passed + {fbroken:>10d} missing or broken")
        if files_broken_list:
            print('Files missing or broken:')
            for i, fpath in enumerate(files_broken_list):
                print(spath.parent.joinpath(fpath))
                if i == 49:
                    if fbroken > 50:
                        print('Truncated at 50 files - too many potential missing or broken files.')
                    break
            print('\nI: Some files may be in fact OK but cannot be verified as their neighbour files failed.')

    def _set(self):
        try:
            self.torrent.set(**self.metadata)
        except PieceSizeTooSmall as e:
            self.__exit(f"Piece size must be larger than 16KiB, not {self.metadata['piece_size']} bytes.")
        except PieceSizeUncommon as e:
            if self.__prompt(f"Uncommon piece size {self.metadata['piece_size'] >> 10} KiB. Confirm? (y/N): "):
                self.torrent.setPieceLength(self.metadata['piece_size'], no_check=True)
                self.metadata.pop('piece_size')
                self.torrent.set(**self.metadata)
            else:
                self.__exit()

    def _write(self):
        fpath = self.tpath.with_suffix(
            f"{'.' + time.strftime('%y%m%d-%H%M%S') if self.cfg.with_time_suffix else ''}.torrent"
            )
        try:
            self.torrent.write(fpath, overwrite=False)
            print(f"I: Torrent saved to '{fpath}'.")
        except FileExistsError as e:
            if self.__prompt(f"The target file '{fpath}' already exists. Overwrite? (y/N): "):
                self.torrent.write(fpath, overwrite=True)
                print(f"I: Torrent saved to '{fpath}' (overwritten).")
            else:
                self.__exit()
        except IsADirectoryError as e:
            self.__exit(f"E: The target '{fpath}' is a directory.")




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
    parser = argparse.ArgumentParser(prog='tu', formatter_class=lambda prog: _CustomHelpFormatter(prog))

    parser.add_argument('fpaths', type=_Path, nargs='*', help='1 or 2 paths depending on mode', metavar='path')
    parser.add_argument(
        '-m',
        '--mode',
        dest='mode',
        choices=('create', 'print', 'verify', 'modify'),
        help='mode will be inferred from paths if not specified'
        )
    parser.add_argument(
        '-t',
        '--tracker',
        dest='tracker_list',
        type=str,
        action='extend',
        nargs='+',
        help='trackers can be supplied multiple times',
        metavar='url'
        )
    parser.add_argument(
        '-c', '--comment', dest='comment', type=str, help='your message to show in various clients', metavar='text'
        )
    parser.add_argument(
        '-s', '--piece-size', dest='piece_size', type=int, help='piece size in KiB (default: 4096)', metavar='number'
        )
    parser.add_argument(
        '-p', '--private', dest='private', type=int, choices={0, 1}, help='private torrent if 1 (default: 0)'
        )
    parser.add_argument(
        '--by', dest='created_by', type=str, help='set the creator of the torrent (default: Github)', metavar='text'
        )
    parser.add_argument(
        '--time',
        dest='creation_date',
        type=int,
        help='set the time in second since 19700101 (default: now)',
        metavar='number'
        )
    parser.add_argument(
        '--encoding',
        dest='encoding',
        type=str,
        help='set the text encoding (default&recommended: UTF-8)',
        metavar='text'
        )
    parser.add_argument(
        '--source', dest='source', type=str, help='set the special source message (will change hash)', metavar='text'
        )
    parser.add_argument(
        '--preset',
        dest='preset',
        type=_Path,
        help='load a preset file for metadata in creating torrent',
        metavar='path'
        )
    parser.add_argument(
        '--no-progress', dest='show_progress', action='store_false', help='disable progress bar in creating torrent'
        )
    parser.add_argument(
        '--time-suffix', dest='with_time_suffix', action='store_true', help='append current time to torrent filename'
        )
    parser.add_argument(
        '-y', '--yes', dest='show_prompt', action='store_false', help='just say yes - don\'t ask any question'
        )
    parser.add_argument('--version', action='version', version='TorrentUtils 0.2.0.20230208')

    Main(parser.parse_args())()
