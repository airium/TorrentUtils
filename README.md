# TorrentUtils

## Prerequisite

```txt
python>=3.8
bencoder
```

## TODOs

Core:

- [x] create torrent
- [ ] check torrent integrity
- [ ] verify files from a torrent
- [ ] support various torrent metadata

Command line usage:

- [ ] **create** a torrent from a file/dir
- [ ] **check** torrent integrity
- [ ] **verify** file integrity from a torrent
- [ ] **modify** torrent metadata e.g. trackers

GUI drag-drop usage:

- [ ] dropping a file/dir (non-torrent) will **create** a torrent
- [ ] dropping a torrent will **check** torrent integrity
- [ ] dropping a file/dir and a torrent will **verify** the file/dir from the torrent
