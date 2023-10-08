from torrentutils.cli import parser
from torrentutils.main import Main

if __name__ == '__main__':
    Main(parser.parse_args())()
