# TorrentUtils

> The project is still under active early development. Do not use until this message disappears.

## Prerequisite

```txt
python>=3.8
tqdm (optional, for progress bar)
```

## Command line usage

```txt
$ python38 TorrentUtils.py -h
usage: TorrentUtils [-h] [-m {create,print,verify,modify}] [-t url [url ...]] [-s number] [-c text]
                    [-p {0,1}] [--tool text] [--time number] [--source text] [--encoding text] [-y]
                    [--no-time-suffix] [--no-progress] [--version]
                    path [path ...]

positional arguments:
  path                                     1 or 2 paths depending on mode

optional arguments:
  -h, --help                               show this help message and exit
  -m, --mode {create,print,verify,modify}  will be guessed from paths if not specified
  -t, --tracker url [url ...]              can be specified multiple times
  -s, --piece-size number                  piece size in KiB (default: 16384)
  -c, --comment text                       the message displayed in various clients
  -p, --private {0,1}                      private torrent if 1 (default: 0)
  --tool text                              customise `created by` message (default: TorrentUtils)
  --time number                            customise the second since 19700101 (default: now)
  --source text                            customise `source` message (will change torrent hash)
  --encoding text                          customise encoding for filenames (default: UTF-8)
  -y, --yes, --no-prompt                   don't prompt the user with any interactive question
  --no-time-suffix                         don't include the current time in new torrent's name
  --no-progress                            don't display the progress bar in creating torrent
  --version                                show program's version number and exit
```

## TODOs

Core:

- [x] **create** new torrent
- [ ] **print** torrent information
- [x] **verify** files against a torrent
- [x] support various torrent **metadata**

Command line usage:

- [x] **create** a torrent from a file/dir
- [ ] **print** torrent integrity
- [x] **verify** file integrity from a torrent
- [x] **modify** torrent metadata e.g. trackers

GUI drag-drop usage:

- [x] dropping a file/dir (non-torrent) will **create** a torrent
- [ ] dropping a torrent will **print** torrent information
- [x] dropping a file/dir and a torrent will **verify** the file/dir from the torrent

## Thanks to

<https://github.com/utdemir/bencoder>

<https://stackoverflow.com/a/31124505>
