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
                    [-p {0,1}] [--by text] [--time number] [--source text] [--encoding text]
                    [--time-suffix] [--progress] [-y]
                    [path [path ...]]

positional arguments:
  path                                     1 or 2 paths depending on mode

optional arguments:
  -h, --help                               show this help message and exit
  -m, --mode {create,print,verify,modify}  will be guessed from paths if not specified
  -t, --tracker url [url ...]              can be specified multiple times
  -s, --piece-size number                  piece size in KiB (default: 4096)
  -c, --comment text                       the message displayed in various clients
  -p, --private {0,1}                      private torrent if 1 (default: 0)
  --by text                                customise `created by` message (default: TorrentUtils)
  --time number                            customise the second since 19700101 (default: now)
  --source text                            customise `source` message (will change torrent hash)
  --encoding text                          customise encoding for filenames (default: UTF-8)
  --time-suffix                            insert time between torrent filename and extension
  --progress                               show progress bar during creating torrent
  -y, --yes                                just say yes - don't ask any question
```

## TODOs

### Core

- [x] **print** torrent information
- [x] **create** new torrent
- [x] **verify** files against a torrent
- [x] support various torrent **metadata**

### CLI

- [x] **print** mode to display torrent information
- [x] **create** mode to create a torrent with
- [x] **modify** mode to edit torrent metadata
- [x] **verify** mode to check file integrity against the torrent

### GUI Drag-Drop (inherit CLI)

- [x] **print** torrent information by dropping a single torrent file
- [x] **create** a torrent by dropping a single non-torrent file/dir
- [x] **verify** files against a torrent by dropping a file/dir and a torrent

## Thanks to

<https://github.com/utdemir/bencoder>

<https://stackoverflow.com/a/31124505>
