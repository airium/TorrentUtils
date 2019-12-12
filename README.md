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
                    [--json path] [--time-suffix] [--progress] [-y]
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
  --json path                              user-defined json providing metadata preset
  --time-suffix                            insert time between torrent filename and extension
  --progress                               show progress bar during creating torrent
  -y, --yes                                just say yes - don't ask any question
```

## TODOs and status

1. Complete the print functionality
2. Complete the verify functionality and various locators

### Core

- [x] minimal torrent functionality
- [x] common torrent metadata
- [x] read/write torrent file read
- [x] load (rebuild) from source files
- [ ] verify source files with torrent

### CLI

- [ ] **print** torrent information
- [x] **create** new torrent from source files, with json preset loader
- [x] **modify** torrent metadata
- [ ] **verify** source files with torrent

### GUI Drag-Drop (inherit CLI)

- [x] print torrent information by dropping a torrent file
- [x] create a torrent by dropping a non-torrent file/dir, with json preset auto-loading
- [ ] verify source files with torrent by dropping a file/dir and a torrent

## Thanks to

<https://github.com/utdemir/bencoder>

<https://stackoverflow.com/a/31124505>
