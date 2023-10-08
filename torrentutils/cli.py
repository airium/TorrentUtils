__all__ = ['parser']

import argparse
from pathlib import Path

from torrentutils.version import TU_VER




class _CustomHelpFormatter(argparse.HelpFormatter):

    def __init__(self, prog):
        super().__init__(prog, max_help_position=50, width=100)

    def _format_action_invocation(self, action):
        if not action.option_strings or action.nargs == 0:
            return super()._format_action_invocation(action)
        default = self._get_default_metavar_for_optional(action)
        args_string = self._format_args(action, default)
        return ', '.join(action.option_strings) + ' ' + args_string




parser = argparse.ArgumentParser(prog='tu', formatter_class=lambda prog: _CustomHelpFormatter(prog))

parser.add_argument(
    'fpaths',
    type=Path,
    nargs='*',
    help='1 or 2 paths depending on mode',
    metavar='path',
    )
parser.add_argument(
    '-m',
    '--mode',
    dest='mode',
    choices=('create', 'print', 'verify', 'modify'),
    help='mode will be inferred from paths if not specified',
    )
parser.add_argument(
    '-t',
    '--tracker',
    dest='tracker_list',
    type=str,
    action='extend',
    nargs='+',
    help='trackers can be supplied multiple times',
    metavar='url',
    )
parser.add_argument(
    '-c',
    '--comment',
    dest='comment',
    type=str,
    help='your message to show in various clients',
    metavar='text',
    )
parser.add_argument(
    '-s',
    '--piece-size',
    dest='piece_size',
    type=int,
    help='piece size in KiB (default: 4096)',
    metavar='number',
    )
parser.add_argument(
    '-p',
    '--private',
    dest='private',
    type=int,
    choices={0, 1},
    help='private torrent if 1 (default: 0)',
    )
parser.add_argument(
    '--by',
    dest='created_by',
    type=str,
    help='set the creator of the torrent (default: Github)',
    metavar='text',
    )
parser.add_argument(
    '--time',
    dest='creation_date',
    type=int,
    help='set the time in second since 19700101 (default: now)',
    metavar='number',
    )
parser.add_argument(
    '--encoding',
    dest='encoding',
    type=str,
    help='set the text encoding (default&recommended: UTF-8)',
    metavar='text',
    )
parser.add_argument(
    '--source',
    dest='source',
    type=str,
    help='set the special source message (will change hash)',
    metavar='text',
    )
parser.add_argument(
    '--preset',
    dest='preset',
    type=Path,
    help='load a preset file for metadata in creating torrent',
    metavar='path',
    )
parser.add_argument(
    '--no-progress',
    dest='show_progress',
    action='store_false',
    help='disable progress bar in creating torrent',
    )
parser.add_argument(
    '--time-suffix',
    dest='with_time_suffix',
    action='store_true',
    help='append current time to torrent filename',
    )
parser.add_argument(
    '-y',
    '--yes',
    dest='show_prompt',
    action='store_false',
    help='just say yes - dont ask any question',
    )
parser.add_argument('--version', action='version', version=TU_VER)
