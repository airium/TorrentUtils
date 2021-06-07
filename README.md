# TorrentUtils = tu

[中文README](README.CN.md)

**All major functions should work now. You're welcome to try and post bug reports. API and CLI are still subject to change.**

**Caution**:

Due to the breaking change in Unicode 5.2.0 (Oct 2009), special characters like emoji encoded with Unicode 5.2+ and 5.2- are **mutually incompatible**.  Since TorrentUtils uses Unicode 12+ from Python 3.8+, if you plan to make & run torrent with legacy clients (Unicode 5.2-), e.g. uTorrent 2.2.1, be careful to avoid special characters in filenames.

## Requirements

```txt
python>=3.8
tqdm (optional, for progress bar)
```

Nothing needed if you just use the released executables.

## CLI Usage

```txt
$ python3 tu.py -h
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
  --by text                                set the creator of the torrent (default: Github)
  --time number                            set the time in second since 19700101 (default: now)
  --encoding text                          set the text encoding (default&recommended: UTF-8)
  --source text                            set the special source message (will change hash)
  --json path                              load a json for metadata preset in creating torrent
  --no-progress                            disable progress bar in creating torrent
  --time-suffix                            append current time to torrent filename
  -y, --yes                                just say yes - don't ask any question
```

---

## Automatic Mode Inference and Path Selector

If not given working mode via `-m`, the script will infer one from the input paths, and also which path to load/read/save. The rules are given below:

Abbr: \
Path Args: `1`/`2` = the 1st path you input / the 2nd path you input (if) \
Path Types: `F`/`D`/`T` = a file-like path (not torrent-like) / a directory-like path / a torrent-like path \
Actions: `L`/`R`/`W` = Load files from / Read torrent from / Write torrent to

| CLI -m argument                | 1:F/D      | 1:T        | 1:D<br>2:F | 1:F/D<br>2:D | 1:T<br>2:F/D | 1:F/D<br>2:T | 1:T<br>2:T | 1:F<br>2:F |
| ------------------------------ | ---------- | ---------- | ---------- | ------------ | ------------ | ------------ | ---------- | ---------- |
| not given or<br> GUI drag-drop | -m create  | -m print   | -m create  | -m create    | -m verify    | -m verify    | -          | -          |
| -m create                      | L 1<br>W 1 | L 1<br>W 1 | L 2<br>W 1 | L 1<br>W 2   | L 2<br>W 1   | L 1<br>W 2   | R 1<br>W 2 | -          |
| -m print                       | -          | R 1        | -          | -            | -            | -            | -          | -          |
| -m verify                      | -          | -          | -          | -            | R 1<br>L 2   | L 1<br>R 2   | -          | -          |
| -m modify                      | -          | R 1<br>W 1 | -          | -            | -            | -            | R 1<br>W 2 | -          |

---

## TODO and Progress

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
