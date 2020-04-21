# TorrentUtils = tu

所有主要功能现已能使用，欢迎试用和汇报问题，脚本参数和内部接口未来仍存在变动。

**注意**：Unicode 版本低于 5.2.0 的老客户端如 uTorrent 2.2.1 无法识别 Unicode 5.2.0 或更高标准编码的特殊字符如 emoji 表情，而本脚本由 Python 3.8 使用 Unicode 12.1.0。这意味着如果文件名中包含大量特殊字符，你应该小心由本脚本（或任何使用 Unicode 5.2.0 及更高的制种软件）创建的种子将可能无法为 uTorrent 2.2.1 使用（一般应该没问题）。本脚本目前也不能识别以 Unicode 5.1 或更低标准编码的特殊字符，因为 Python 3 对此直接报错，且 Python 3 早期版本如 Python 3.1 就已经是 Unicode 6.0.0 了。未来可能考虑提供将旧 Unicode 编码的种子升级到新版，但这会改变种子的 SHA1（无论如何在文件名中应避免使用特殊字符）。

---

## 需求

```txt
python>=3.8
tqdm (可选, 用于显示进度条)
```

直接使用发布的 exe 执行文件的话不需要以上这些。

---

## 命令行参数

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

## 自动模式推测和路径选取

如果没有以 -m 参数指出模式，那么将自动根据输入的路径进行推测，同时判断那个路径是用来做什么的。下表给出规则：

简写：\
`F`/`D`/`T` = 一个看起来像文件但不像种子的路径 / 一个看起来像目录的路径 / 一个看起来像种子的路径 \
`1`/`2` = 第一个输入的路径  / 第二个输入的路径 (如果有) \
`L`/`R`/`W` = 由此读取文件 / 由此读取种子 / 保存种子到

| 命令行 -m 参数       | 1:F/D      | 1:T        | 1:D<br>2:F | 1:F/D<br>2:D | 1:T<br>2:F/D | 1:F/D<br>2:T | 1:T<br>2:T | 1:F<br>2:F |
| -------------------- | ---------- | ---------- | ---------- | ------------ | ------------ | ------------ | ---------- | ---------- |
| 未输入或<br>拖拽操作 | -m create  | -m print   | -m create  | -m create    | -m verify    | -m verify    | -          | -          |
| -m create            | L 1<br>W 1 | L 1<br>W 1 | L 2<br>W 1 | L 1<br>W 2   | L 2<br>W 1   | L 1<br>W 2   | R 1<br>W 2 | -          |
| -m print             | -          | R 1        | -          | -            | -            | -            | -          | -          |
| -m verify            | -          | -          | -          | -            | R 1<br>L 2   | L 1<br>R 2   | -          | -          |
| -m modify            | -          | R 1<br>W 1 | -          | -            | -            | -            | R 1<br>W 2 | -          |

---

## 感谢

<https://github.com/utdemir/bencoder>

<https://stackoverflow.com/a/31124505>
