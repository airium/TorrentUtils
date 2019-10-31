import re
import sys
import string
import argparse
from pathlib import Path
from operator import methodcaller as mc
from itertools import chain
from functools import partial


if sys.version_info < (3, 8):
    print('Please use Python 3.8 or higher')
    sys.exit(1)




def _encode(obj, encoding='utf-8'):
    tobj = type(obj)
    if tobj is bytes:
        ret = str(len(obj)).encode(encoding) + b":" + obj
    elif tobj is str:
        ret = _encode(obj.encode(encoding))
    elif tobj is int:
        ret = b"i" + str(obj).encode(encoding) + b"e"
    elif tobj in (list, tuple):
        ret = b"l" + b"".join(map(partial(_encode, encoding=encoding), obj)) + b"e"
    elif tobj is dict:
        ret = b'd'
        for key, val in sorted(obj.items()):
            if type(key) in (bytes, str):
                ret += _encode(key, encoding) + _encode(val, encoding)
            else:
                raise ValueError("Dict key must be str or bytes")
        ret += b'e'
    else:
        raise ValueError('Input must be int, bytes, list or dict')
    return ret




def _decode(s, encoding='ascii'):
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
            raise ValueError("Invalid bencoded data")

    s = s.encode(encoding) if isinstance(s, str) else s
    ret, rest = decode_first(s)
    if rest:
        raise ValueError("Invalid bencoded data")
    return ret




def main(args):
    for fpath in filter(mc('match', '*.' + args.mode), filter(mc('is_file'), args.path + list(chain(*map(list, map(mc('rglob', '*'), args.path)))))):
        try:

            data = _decode(fpath.read_bytes())
            if not isinstance(data, dict):
                raise TypeError(f'Expect bencoded dict; not {type(data)}')

            encoding = data.get('encoding', 'utf-8')

            if args.mode == 'fastresume':
                if args.new_path:
                    data[b'qBt-savePath'] = bytes(args.new_path, encoding)
                    data[b'save_path'] = bytes(args.new_path, encoding)
                trackers = list(chain(*data.get(b'trackers', [])))
                if args.clear_tracker:
                    trackers = []
                for tracker in args.trackers_to_remove + args.trackers_to_add:
                    trackers = list(filter(mc('__ne__', bytes(tracker, encoding)), trackers))
                for i, tracker in enumerate(args.trackers_to_add):
                    trackers.insert(i, bytes(tracker, encoding))
                data[b'trackers'] = list([tracker] for tracker in trackers)

            if args.mode == 'torrent':
                trackers = ([data.get(b'announce')] if data.get(b'announce') else []) + list(chain(*data.get(b'announce-list', [])))
                if len(trackers) >= 2 and trackers[0] == trackers[1]:
                    trackers.pop(0)
                if args.clear_tracker:
                    trackers = []
                for tracker in args.trackers_to_remove + args.trackers_to_add:
                    trackers = list(filter(mc('__ne__', bytes(tracker, encoding)), trackers))
                for i, tracker in enumerate(args.trackers_to_add):
                    trackers.insert(i, bytes(tracker, encoding))
                if len(trackers) == 0:
                    if b'announce' in data.keys(): data.pop(b'announce')
                    if b'announce-list' in data.keys(): data.pop(b'announce-list')
                elif len(trackers) == 1:
                    data[b'announce'] = trackers[0]
                    if b'announce-list' in data.keys(): data.pop(b'announce-list')
                else:
                    data[b'announce'] = trackers[0]
                    data[b'announce-list'] = list([tracker] for tracker in trackers)

            fpath.write_bytes(_encode(data, encoding))

        except Exception as err:
            print(f'\'{fpath.absolute()}\' : Skipped as {err.__class__.__name__} ({err})')
            continue
        else:
            print(f'\'{fpath.absolute()}\' : OK')




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
    parser = argparse.ArgumentParser(formatter_class=lambda prog: _CustomHelpFormatter(prog),
                                     epilog='Note: tracker operation sequence is clear > del > add; '
                                            'added trackers will be placed on top; '
                                            'existing trackers in one tier will be flattened to different tiers.')
    parser.add_argument('path', nargs='+', type=Path, metavar='path',
                        help='recursively find fastresume/torrent in these files/folders')
    parser.add_argument('-m', '--mode', choices=('fastresume', 'torrent'), default='fastresume',
                        help='to modify libt fastresume or torrent (default: fastresume)')
    parser.add_argument('-at', '--add-tracker', dest='trackers_to_add', nargs='+', action='extend', default=[], metavar='url',
                        help='add a tracker; can be supplied multiple times')
    parser.add_argument('-dt', '--del-tracker', dest='trackers_to_remove', nargs='+', action='extend', default=[], metavar='url',
                        help='del a tracker; can be supplied multiple times')
    parser.add_argument('-ct', '--clear-tracker', dest='clear_tracker', action='store_true', default=False,
                        help='remove all existing trackers')
    parser.add_argument('-to', '--move-to', dest='new_path', type=str, default='', metavar='new_path',
                        help='change saved path in fastresume; no effect in torrent mode')
    main(parser.parse_args())
