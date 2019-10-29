# TorrentUtils

## Prerequisite

```txt
python>=3.8
```

## Command line usage

```txt
$ python TorrentUtils.py -h
usage: TorrentUtils [-h] [-m {create,check,verify,modify}] [-t url [url ...]] [-s number] [-c text]
                    [-p {0,1}] [--tool text] [--time number] [--source text] [--encoding text] [-y]
                    [--no-time-suffix] [--no-progress] [--version]
                    path [path ...]

positional arguments:
  path                                     1 or 2 paths depending on mode

optional arguments:
  -h, --help                               show this help message and exit
  -m, --mode {create,check,verify,modify}  will be guessed from fpaths if not specified
  -t, --tracker url [url ...]              can be specified multiple times
  -s, --piece-size number                  piece size in KiB (default: 16384KiB)
  -c, --comment text                       the message displayed in various clients
  -p, --private {0,1}                      private torrent if 1 (default: 0)
  --tool text                              customise `created by` message (default: TorrentUtils)
  --time number                            customise the second since 19700101 (default: now)
  --source text                            customise `source` message (will change torrent hash)
  --encoding text                          customise encoding for filenames (default: utf-8)
  -y, --yes, --no-prompt                   don't prompt any interactive question
  --no-time-suffix                         don't add the current time in new torrent's name
  --no-progress                            don't print any progress info
  --version                                show program's version number and exit
```

## TODOs

Core:

- [x] **create** torrent
- [ ] **check** torrent integrity
- [ ] **verify** files from a torrent
- [x] support various torrent **metadata**

Command line usage:

- [x] **create** a torrent from a file/dir
- [ ] **check** torrent integrity
- [ ] **verify** file integrity from a torrent
- [ ] **modify** torrent metadata e.g. trackers

GUI drag-drop usage:

- [x] dropping a file/dir (non-torrent) will **create** a torrent
- [ ] dropping a torrent will **check** torrent integrity
- [ ] dropping a file/dir and a torrent will **verify** the file/dir from the torrent

## Thanks to

<https://github.com/utdemir/bencoder>
