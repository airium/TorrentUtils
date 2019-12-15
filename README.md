# TorrentUtils = tu

**All major functions should work now.**
**You're welcome to try and post bug reports.**
**API and CLI are still subject to change.**

## Prerequisite

```txt
python>=3.8
tqdm (optional, for progress bar)
```

## CLI

```txt
$ python38 tu.py -h
usage: tu [-h] [-m {create,print,verify,modify}] [-t url [url ...]] [-s number] [-c text] [-p {0,1}]
          [--by text] [--time number] [--source text] [--encoding text] [--json path]
          [--time-suffix] [--progress] [-y]
          [path [path ...]]

positional arguments:
  path                                     1 or 2 paths depending on mode

optional arguments:
  -h, --help                               show this help message and exit
  -m, --mode {create,print,verify,modify}  mode will be inferred from paths if not specified
  -t, --tracker url [url ...]              trackers can be supplied multiple times
  -s, --piece-size number                  piece size in KiB (default: 4096)
  -c, --comment text                       the message displayed in various clients
  -p, --private {0,1}                      private torrent if 1 (default: 0)
  --by text                                override `created by` message
  --time number                            override the second since 19700101 (default: now)
  --source text                            override source message and change torrent hash
  --encoding text                          override text encoding (recommended: UTF-8)
  --json path                              load a json preset for metadata in creating torrent
  --time-suffix                            insert time between torrent filename and extension
  --progress                               show progress bar during creating torrent
  -y, --yes                                just say yes - don't ask any question
```

---

## Automatic Mode Inference and Path Sort

CLI interface only accepts 1 or 2 paths depending on working mode. If `-m` or `--mode` is not supplied, working mode will be automatically inferred from supplied paths. See the table below for how CLI interface infers working mode and sorts paths.

Assume: \
`T`: a path that looks like a torrent file. \
`D`: a path that looks like a directory. \
`F`: a path that looks like a regular file (not a torrent).

| 1: 1st path arg<br>2: 2nd path arg | 1:F/D | 1:T | 1:F<br>2:F | 1:D<br>2:F | 1:T<br>2:F | 1:F<br>2:D | 1:D<br>2:D | 1:T<br>2:D | 1:F<br>2:T | 1:D<br>2:T | 1:T<br>2:T |
|------------------------------------|------------------|------------------|------------|------------------|------------------|------------------|------------------|------------------|------------------|------------------|------------------|
| CLI w/o mode<br>(=GUI Drag-Drop) | create | print | - | create | verify | create | create | verify | verify | verify | - |
| CLI -m create | load 1<br>save 1 | - | - | load 2<br>save 1 | load 2<br>save 1 | load 1<br>save 2 | load 1<br>save 2 | load 2<br>save 1 | load 1<br>save 2 | load 1<br>save 2 | - |
| CLI -m print | - | read 1 | - | - | - | - | - | - | - | - | - |
| CLI -m verify | - | - | - | - | read 1<br>load 2 | - | - | read 1<br>load 2 | load 1<br>read 2 | load 1<br>read 2 | - |
| CLI -m modify | - | read 1<br>save 1 | - | - | - | - | - | - | - | - | read 1<br>save 2 |

---

## TODO and status

1. Implement a tree-view for CLI print functionality.
2. Implement the progress bar for creating and verifying torrent outside of core class.
3. Implement multi-process for faster torrent creating with mp shared memory.

### Core API

- [x] minimal torrent functionality
- [x] common torrent metadata
- [x] read/write torrent file
- [x] load (rebuild) from source files
- [x] verify source files with torrent

### CLI

- [x] **print** torrent information
- [x] **create** new torrent from source files, with json preset loader
- [x] **modify** torrent metadata
- [x] **verify** source files with torrent

### GUI Drag-Drop (inherit CLI)

- [x] print torrent information by dropping a torrent file
- [x] create a torrent by dropping a non-torrent file/dir, with json preset auto-loading
- [x] verify source files with torrent by dropping a non-torrent file/dir and a torrent

---

## Thanks to

<https://github.com/utdemir/bencoder>

<https://stackoverflow.com/a/31124505>
