# codex-usage

[English README](README.md)

`codex-usage` 是一个**非官方、本地优先的 Codex 用量分析工具**。它读取本机 Codex session transcript，并按 session、模型、主 agent 和 subagent 汇总 token 活动与估算的 credit 消耗。

它主要回答官方用量视图目前不直接回答的一个问题：

> 我的 Codex 额度到底花在哪个 session 上，为什么会花这么多？

核心工具仍然只有一个 Python 脚本，**正常使用零强制第三方依赖**。**v1.4.0 正式增加原生 Windows 支持**，同时保留 macOS 和 Linux 支持。

## 主要功能

- 按 session 统计 `today`、`yesterday`、指定日期、日期范围，以及 `6h`、`12h`、`24h` 和任意 `Nh` 滚动时间窗口。
- 区分 GPT-5.6 Sol / Terra / Luna、GPT-5.5、GPT-5.4、GPT-5.4 mini 等模型。
- 区分 MAIN 与 subagent；默认把 subagent 用量回卷到所属根 session。
- `CACHE TAX`：cached input 单独贡献的估算 credits。
- `1H BURN`：最近 60 分钟产生的 credits，用于观察当前消耗速度。
- `ACTIVE` / `RECENT` / `IDLE` 和 `OK` / `WATCH` / `ROTATE` 工作流提示。
- 终端彩色高亮；Windows 下自动尝试开启 VT/ANSI 支持。
- 增量 SQLite 索引：首次扫描后，不再重复读取未变化的 JSONL；仍在追加的 session 只读取文件尾部。
- 热路径 discovery：日常查询无需每次遍历全部历史 session 文件。
- 支持 JSON / CSV 输出。
- Windows PowerShell 安装器与 CMD 启动器。
- Windows / macOS / Linux 三平台 CI。

## 环境要求

- Python **3.9+**
- 本机安装并使用过 Codex，session transcript 位于 `$CODEX_HOME` / `%CODEX_HOME%`，或者通过 `--codex-home` 指定路径
- Windows 10/11、macOS 或 Linux

正常按照系统本地时区使用时，不需要安装任何第三方 Python 包。

### Windows 时区说明

Windows 上的 Python 通常不会自带 IANA 时区数据库。默认使用**系统本地时区**时完全不需要额外依赖。

如果你显式指定：

```powershell
codex-usage 24h --timezone Asia/Tokyo
```

并遇到时区不可用提示，可以安装可选的 `tzdata`：

```powershell
py -3 -m pip install tzdata
```

## 安装

### Windows（PowerShell）

```powershell
git clone https://github.com/yza167-jp/codex-usage.git
cd codex-usage
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

安装器默认将：

```text
codex-usage
codex-usage.cmd
```

复制到：

```text
%LOCALAPPDATA%\Programs\codex-usage
```

并把该目录加入**用户级 PATH**。重新打开一个终端后验证：

```powershell
codex-usage --version
```

也可以指定安装目录：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -InstallDir C:\Tools\codex-usage
```

如果不想安装，直接运行：

```powershell
py -3 .\codex-usage 24h
```

### macOS / Linux

```bash
git clone https://github.com/yza167-jp/codex-usage.git
cd codex-usage
mkdir -p ~/.local/bin
install -m 755 codex-usage ~/.local/bin/codex-usage
```

如果 `~/.local/bin` 尚未加入 `PATH`，zsh 可以执行：

```bash
grep -q '.local/bin' ~/.zshrc 2>/dev/null || \
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

验证：

```bash
codex-usage --version
```

## 快速开始

```text
codex-usage today
codex-usage yesterday
codex-usage 6h
codex-usage 12h
codex-usage 24h
codex-usage 48h
codex-usage 168h
codex-usage week
codex-usage 7d
codex-usage 2026-08-10
codex-usage 2026-08-01..2026-08-10
```

`24h` 与 `yesterday` 刻意保持不同语义：

- `24h`：从当前时刻向前精确滚动 24 小时。
- `yesterday`：本地时区的上一个自然日，即 `00:00–24:00`。

v1.4.0 的任意 `Nh` 窗口按照**实际经过时间**计算，在跨夏令时切换时也不会把 23/25 小时误当作 24 小时。

## 如何阅读摘要

典型输出：

```text
SESSION                        MODEL(S)            CREDITS*  CACHE TAX  1H BURN  SHARE  STATUS
current-feature-work (+4 sub)  5.6 Sol / 5.6 Luna    812.4      501.7     184.2   28.6%  ACTIVE/WATCH
older-long-session             5.6 Sol              2034.8     1510.3         —   71.4%  IDLE
```

### `CREDITS*`

根据本地 token counter 和脚本内置 rate card 重建出的估算值。它非常适合做**相对归因**，例如比较哪个 session、哪个模型最消耗额度，但它**不是 OpenAI 服务端的 authoritative quota meter**。

### `CACHE TAX`

cached input 单独造成的估算 credit 成本。该值持续升高，通常说明一个长期存活的主 thread 在反复携带很大的历史上下文。

### `1H BURN`

最近 60 分钟实际观察到的 credits，是滚动活动指标，不是套餐限制，也不是账单预测。

### `STATUS`

对于实时窗口：

- `ACTIVE`：最近 15 分钟有 token 活动。
- `RECENT`：最近 1 小时有活动。
- `IDLE`：近期无活动。
- `OK`：暂未出现明显长上下文成本问题。
- `WATCH`：上下文成本开始值得关注。
- `ROTATE`：建议在自然 milestone 做 checkpoint，然后考虑新开 root session。

这些只是本地工作流 heuristic，不是 OpenAI 产品告警。

## 详细诊断

```text
codex-usage 24h --details
```

会增加：

- cached input / uncached input / output 的 credit component
- MAIN vs subagent 汇总
- model breakdown
- agent breakdown
- 最近活动时间
- 最近一小时 burn 与 active thread 的简单 +2h 线性外推

默认每个 session 只显示最重要的前 8 个 agent：

```text
codex-usage 24h --details --top-agents 5
codex-usage 24h --details --all-agents
```

恢复 token 列：

```text
codex-usage 24h --wide
```

不回卷 subagent，而是分别显示：

```text
codex-usage 24h --show-subagents
```

## 彩色终端

交互式终端中默认自动开启颜色。v1.4.0 在 Windows 下会尝试自动启用 Virtual Terminal Processing，因此 Windows Terminal、现代 PowerShell 以及支持 VT 的 `cmd.exe` 可以获得和 macOS/Linux 相同的状态颜色。

```text
codex-usage 24h --color always
codex-usage 24h --color never
```

支持标准 `NO_COLOR` 环境变量。JSON / CSV 永远不会混入 ANSI 控制字符。

## JSON / CSV

```text
codex-usage 24h --json
codex-usage 24h --csv
codex-usage week --csv > codex-week.csv
```

## 增量索引与性能

长程 Codex session 的 transcript 可能非常大，因此 `codex-usage` 使用本地 SQLite 增量索引。

默认 cache 路径：

- Windows：`%LOCALAPPDATA%\codex-usage\index-v2.sqlite3`
- macOS：`~/Library/Caches/codex-usage/index-v2.sqlite3`
- Linux：`${XDG_CACHE_HOME:-~/.cache}/codex-usage/index-v2.sqlite3`

性能诊断：

```text
codex-usage 24h --perf
```

例如：

```text
Perf: incremental-index | discovery=hot 0.004s | files=86 | hits=27 | cold=0 | ancestor=0 | tail=1 | skipped-old=58 | read=0.2 MiB | sync=0.006s | total=0.24s
```

维护命令：

```text
codex-usage --cache-info
codex-usage 24h --rebuild-cache --perf
codex-usage 24h --no-cache
codex-usage 24h --full-discovery --perf
```

SQLite cache 只保存统计需要的 metadata 与 token counter，不会把 prompt / response 正文复制进去。

## Codex 数据路径

默认路径：

```text
~/.codex
```

在 Windows、macOS、Linux 上都会映射到当前用户 home。也可以设置 `CODEX_HOME`，或者显式：

```text
codex-usage 24h --codex-home <path>
```

如果你的 Codex session 实际位于 **WSL** 内，最简单、最可靠的方式仍然是在同一个 WSL distribution 内运行 `codex-usage`。原生 Windows 版本也可以通过 `--codex-home` 指向 Windows 能访问的 transcript 路径，但 profiler 自己的 SQLite cache 最好保留在 Windows 本地文件系统上。

## Fast mode

如果所选时间窗口内所有支持 Fast 的请求都使用了 Fast mode：

```text
codex-usage 24h --fast
```

由于本地 `token_count` 事件无法可靠恢复每个历史请求的 Standard/Fast tier，`--fast` 的含义是：**假设报告窗口内所有符合条件的请求都用了 Fast**。

## 数据来源与准确性

工具读取本机 Codex rollout JSONL，并在存在时读取 `state_5.sqlite` 获取 thread metadata；随后利用脚本内置 rate card 将 token counter 换算为估算 credits。

重要边界：

- 本地 transcript 是 telemetry，不是 authoritative server-side quota meter。
- 历史 Fast / Standard tier 无法可靠恢复。
- 模型和 rate card 会变化；可以查看脚本中的 `RATE_CARD_AS_OF`。
- full-history fork / subagent 可能复制父级历史 token counter；工具利用 lineage + cumulative counter 去重继承历史。
- lineage 无法解析的 child 会显示 `[ORPHAN SUB]`，而不会猜测父 session。

## 隐私

`codex-usage` 坚持 local-first：

- 不上传 Codex transcript。
- 不要求 API key。
- SQLite cache 不保存 prompt / response 正文。
- 终端输出可能包含本地 thread 标题和项目目录名；公开截图或日志前请自行检查。

公开仓库本身不包含作者个人路径或 session 数据。

## 跨平台测试

仓库内置 smoke tests，覆盖：

- CLI version / help
- synthetic rollout 在无 cache / 增量 cache 两种模式下的解析
- SQLite read-only URI，包括带空格的路径
- 各平台默认 cache path

GitHub Actions 会在 `windows-latest`、`macos-latest`、`ubuntu-latest` 上分别使用 Python 3.9 与 3.13 运行测试。

本地运行：

```text
python -m unittest discover -s tests -v
```

## License

MIT，见 [LICENSE](LICENSE)。

## Disclaimer

本项目与 OpenAI 无隶属或官方背书关系。Codex 行为、transcript 格式、模型和 rate card 都可能发生变化；请把它作为本地诊断工具，而不是账单或额度的权威来源。
