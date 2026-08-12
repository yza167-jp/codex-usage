# codex-usage

[English README](README.md)

`codex-usage` 是一个**非官方、本地优先的 Codex 用量分析工具**。它读取本机 Codex session transcript，并按 session、模型、主 agent 和 subagent 汇总 token 活动与估算的 credit 消耗。

它主要回答官方用量视图目前不直接回答的一个问题：

> 我的 Codex 额度到底花在哪个 session 上，为什么会花这么多？

整个工具只有一个 Python 脚本，**零第三方依赖**。

## 主要功能

- 按 session 统计 `today`、`yesterday`、指定日期、日期范围，以及 `6h`、`12h`、`24h` 和任意 `Nh` 滚动时间窗口。
- 区分 GPT-5.6 Sol / Terra / Luna、GPT-5.5、GPT-5.4、GPT-5.4 mini 等模型。
- 区分 MAIN 与 subagent；默认把 subagent 用量回卷到所属根 session。
- `CACHE TAX`：cached input 单独贡献的估算 credits。
- `1H BURN`：最近 60 分钟产生的 credits，用于观察当前消耗速度。
- `ACTIVE` / `RECENT` / `IDLE` 和 `OK` / `WATCH` / `ROTATE` 工作流提示。
- 终端彩色高亮；pipe、JSON、CSV 场景自动关闭颜色。
- 增量 SQLite 索引：首次扫描后，不再重复读取未变化的 JSONL；仍在追加的 session 只读取文件尾部。
- 热路径 discovery：日常查询无需每次遍历全部历史 session 文件。
- 支持 JSON / CSV 输出。

## 环境要求

- Python **3.9+**
- 本机安装并使用过 Codex，且 `$CODEX_HOME` 中存在 session transcript
- macOS 或 Linux

不需要安装任何第三方 Python 包。

## 安装

克隆仓库，然后把脚本安装到 `PATH` 中：

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

```bash
# 今天这个自然日
codex-usage today

# 昨天这个自然日
codex-usage yesterday

# 精确滚动窗口
codex-usage 6h
codex-usage 12h
codex-usage 24h
codex-usage 48h

# 任意小时数
codex-usage 168h

# 日历范围
codex-usage week
codex-usage 7d
codex-usage 2026-08-10
codex-usage 2026-08-01..2026-08-10
```

`24h` 和 `yesterday` 的语义有意保持不同：

- `24h`：从**当前时刻往前精确 24 小时**。
- `yesterday`：本地时区的前一个自然日，即 `00:00–24:00`。

## 如何阅读摘要

典型输出：

```text
SESSION                        MODEL(S)            CREDITS*  CACHE TAX  1H BURN  SHARE  STATUS
current-feature-work (+4 sub)  5.6 Sol / 5.6 Luna    812.4      501.7     184.2   28.6%  ACTIVE/WATCH
older-long-session             5.6 Sol              2034.8     1510.3         —   71.4%  IDLE
```

### `CREDITS*`

根据本地 token counter 和脚本内置的 Codex credit rate card 重建出的估算值。它特别适合做**相对归因**——比较哪个 session、哪个模型更耗额度——但它**不是 OpenAI 服务端的 authoritative quota meter**。

### `CACHE TAX`

cached input 单独对应的估算 credit 成本。某个长期存活的主 thread 如果不断携带庞大上下文，通常会出现很高的 `CACHE TAX`。

### `1H BURN`

最近滚动 60 分钟内实际观察到的 credits。它是活动速度指标，不是套餐额度上限，也不是精确的未来预测。

### `STATUS`

对于包含当前时刻的实时窗口，脚本会把“活跃状态”和“线程健康提示”组合起来：

- `ACTIVE`：最近 15 分钟有 token activity。
- `RECENT`：最近 1 小时有 activity。
- `IDLE`：近期没有 activity。
- `OK`：暂无明显的长上下文成本问题。
- `WATCH`：上下文成本已经值得关注。
- `ROTATE`：建议在自然 milestone 做 checkpoint，并考虑开启新的 root session。

这些都是本地工作流 heuristic，不是 OpenAI 官方告警。

## 详细诊断

```bash
codex-usage 24h --details
```

会额外显示：

- cached input / uncached input / output 的 credit component
- MAIN vs subagents
- model breakdown
- 每个 agent 的 breakdown
- 最近 activity 时间
- 最近 1h burn，以及对 ACTIVE thread 的简单 +2h 线性外推

默认每个 session 最多显示 8 个 agent：

```bash
codex-usage 24h --details --top-agents 5
codex-usage 24h --details --all-agents
```

恢复摘要中的 token 列：

```bash
codex-usage 24h --wide
```

不回卷 subagent，而是把每个 subagent 单独作为顶层行显示：

```bash
codex-usage 24h --show-subagents
```

## 彩色输出

当 stdout 是真实终端时，默认自动启用 ANSI 颜色：

```bash
codex-usage 24h --color always
codex-usage 24h --color never
NO_COLOR=1 codex-usage 24h
```

JSON / CSV 不会带 ANSI 颜色码。

## JSON / CSV

```bash
codex-usage 24h --json
codex-usage 24h --csv
codex-usage week --csv > codex-week.csv
```

## 增量索引与性能

长程 Codex session 的 transcript 可能非常大，因此 `codex-usage` 会维护一个本地 SQLite 增量索引。

默认缓存位置：

- macOS：`~/Library/Caches/codex-usage/index-v2.sqlite3`
- Linux：`${XDG_CACHE_HOME:-~/.cache}/codex-usage/index-v2.sqlite3`

查看性能统计：

```bash
codex-usage 24h --perf
```

示例：

```text
Perf: incremental-index | discovery=hot 0.004s | files=86 | hits=27 | cold=0 | ancestor=0 | tail=1 | skipped-old=58 | read=0.2 MiB | sync=0.006s | total=0.24s
```

维护命令：

```bash
codex-usage --cache-info
codex-usage 24h --rebuild-cache --perf
codex-usage 24h --no-cache
codex-usage 24h --full-discovery --perf
```

SQLite 索引只保存统计需要的 metadata 与 token counters，**不会把 prompt / response 正文复制进索引数据库**。

## Fast mode

如果所选时间窗口内所有可用请求都使用了 Codex Fast mode，可以运行：

```bash
codex-usage 24h --fast
```

本地 `token_count` 事件目前不能可靠还原历史 speed tier，所以 `--fast` 的真实含义是：

> 假设当前报告中所有支持 Fast 的用量都使用了 Fast mode。

如果一个时间窗口混用了 Standard / Fast，这只能作为近似值。

## 数据来源与准确性

Codex 官方文档给出的本地 session transcript 路径包括：

- `$CODEX_HOME/sessions`，默认 `~/.codex/sessions`
- `$CODEX_HOME/archived_sessions`，默认 `~/.codex/archived_sessions`

`codex-usage` 解析本地累计 `token_count` 事件，把累计值转换成增量值，再按时间窗口归档；对于 full-history subagent fork，还会尽量识别继承的父 thread 历史，避免重复统计。

脚本内置的 credit rate card 是一个时间点快照，Codex 定价变化后可能过期。报告顶部会显示 rate-card 日期；当前官方价格应以 Codex pricing 文档为准。

官方视图仍然是：

- `/status`：查看当前 session 的信息，包括 current token usage。
- `/usage`：查看账号级 daily / weekly / cumulative token activity。

本工具用于补充“每个 session 到底用了多少”这一维度，不替代官方用量视图。

## 隐私

`codex-usage` 本身是 local-only：

- 不会上传 session 数据。
- 不需要 OpenAI API key。
- 不需要网络访问。
- SQLite 索引只保存统计 metadata / token counter，不复制 prompt / response 正文。

但要注意：**终端输出本身可能包含 session title 和本地 working directory**，其中可能出现项目名或用户名。因此，把输出贴到公开 issue、论坛或聊天前，请先检查并脱敏。

Codex transcript 文件本身可能包含敏感内容，**不要公开整个 `$CODEX_HOME/sessions` 目录**。

## Credit rate 快照

v1.3.0 当前内置的 Codex rate card（每 1M tokens 对应 credits）：

| 模型 | Input | Cached input | Output |
|---|---:|---:|---:|
| GPT-5.6 Sol | 125 | 12.5 | 750 |
| GPT-5.6 Terra | 50 | 5 | 300 |
| GPT-5.6 Luna | 5 | 0.5 | 30 |
| GPT-5.5 | 125 | 12.5 | 750 |
| GPT-5.4 | 62.5 | 6.25 | 375 |
| GPT-5.4 mini | 18.75 | 1.875 | 113 |

脚本的内部 rate card 还包含当前支持的 Daybreak rate。

## 已知限制

- 本地 telemetry 不是服务端 billing ledger。
- credit 估算依赖内置 rate card，可能滞后于官方定价变化。
- 无法从当前本地 token events 可靠恢复 Standard / Fast 混用历史。
- parent / child lineage 可能不完整；无法解析的 child 会显示为 orphan subagent。
- `OK` / `WATCH` / `ROTATE` 是工作流 heuristic。
- Codex 未来可能调整本地 transcript schema。

## 开发与验证

基础 smoke test：

```bash
python3 codex-usage --version
python3 codex-usage --help
python3 -m py_compile codex-usage
```

如需在自己的数据上对比增量索引和直接解析：

```bash
codex-usage 24h --json > /tmp/cached.json
codex-usage 24h --no-cache --json > /tmp/direct.json
```

如果 Codex 正在运行，两条命令之间可能刚好追加新的 token event，因此结果可能存在极小的时间差。

## 官方参考

- [Codex pricing 与 credit rate card](https://learn.chatgpt.com/docs/pricing)
- [Codex troubleshooting：本地 session transcript 路径](https://learn.chatgpt.com/docs/reference/troubleshooting)
- [Codex developer commands：`/status` 与 `/usage`](https://learn.chatgpt.com/docs/developer-commands)

## 声明

本项目为非官方社区工具，与 OpenAI 无隶属或背书关系。“OpenAI”、“ChatGPT” 与 “Codex” 为其各自权利人的商标。

## License

MIT，见 [LICENSE](LICENSE)。
