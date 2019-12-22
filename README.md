# TorrentUtils = tu

**All major functions should work now.**
**You're welcome to try and post bug reports.**
**API and CLI are still subject to change.**

## Requirements

Run in console:

```txt
python>=3.8
tqdm (optional, for progress bar)
```

No particular dependence to run executables released by pyinstaller.

## CLI Usage

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
  -c, --comment text                       your message to show in various clients
  -s, --piece-size number                  piece size in KiB (default: 4096)
  -p, --private {0,1}                      private torrent if 1 (default: 0)
  --by text                                set the creator of the torrent (default: TorrentUtils)
  --time number                            set the time in second since 19700101 (default: now)
  --encoding text                          set the text encoding (default&recommended: UTF-8)
  --source text                            set the special source message (will change hash)
  --json path                              load a json for metadata preset in creating torrent
  --no-progress                            disable progress bar in creating torrent
  --time-suffix                            append current time to torrent filename
  -y, --yes                                just say yes - don't ask any question
```

---

## Automatic Mode Inference and Path Sort

CLI interface determines 1 of 4 working modes (create, print, modify and verify) to run, which is supplied by user argument `-m` or `--mode`, or passively (also limitedly) inferred from the supplied paths. Each working mode requires exactly 1 or 2 paths. See the table below for how CLI interface determines working mode and sorts paths.

Assume: \
`F`: a file-like path (not torrent-like) \
`D`: a directory-like path \
`T`: a torrent-like path path

| 1: 1st path arg<br>2: 2nd path arg | 1:F/D | 1:T | 1:D<br>2:F | 1:F/D<br>2:D | 1:T<br>2:F/D | 1:F/D<br>2:T | 1:T<br>2:T | 1:F<br>2:F |
|------------------------------------|------------------|------------------|------------------|------------------|------------------|------------------|------------------|------------|
| CLI w/o mode<br>(=GUI Drag-Drop) | create | print | create | create | verify | verify | - | - |
| CLI -m create | load 1<br>save 1 | load 1<br>save 1 | load 2<br>save 1 | load 1<br>save 2 | load 2<br>save 1 | load 1<br>save 2 | load 1<br>save 2 | - |
| CLI -m print | - | read 1 | - | - | - | - | - | - |
| CLI -m verify | - | - | - | - | read 1<br>load 2 | load 1<br>read 2 | - | - |
| CLI -m modify | - | read 1<br>save 1 | - | - | - | - | read 1<br>save 2 | - |

---

## TODO and status

1. Move progress bar implementation outside of core class.
2. Implement multi-process loader for faster torrent creating.

### Core API

- [x] minimal torrent functionality
- [x] set/get/clear common torrent metadata
- [x] read/write torrent files
- [x] load (rebuild) from source files
- [x] verify source files against torrent

### CLI

- [x] Argument Parser
- [x] Working mode
  - [x] **print** torrent information incl. general info, trackers and files
  - [x] **create** new torrent from source files, w/ json preset loader
  - [x] **modify** torrent metadata
  - [x] **verify** source files with torrent
- [x] Automatic mode inference (for GUI Drag-Drop)
  - [x] print torrent information by dropping a single torrent file
  - [x] create a torrent by dropping a non-torrent file/dir, w/ json preset auto-loading
  - [x] verify source files with torrent by dropping a non-torrent file/dir and a torrent

---

## Thanks to

<https://github.com/utdemir/bencoder>

<https://stackoverflow.com/a/31124505>
