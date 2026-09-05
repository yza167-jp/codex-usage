# codex-usage

## v1.7.0：支持 GPT-6 Astra

GPT-6 Astra 现已接入 session、TOTAL、最近一小时、模型/档位、主线程/子代理
统计，以及 weekly 估算、JSON 和 CSV。采用核实的公开 **Work/Codex 参考费率**：
每百万未缓存输入、缓存输入、输出 tokens 分别为 **250 / 25 / 1,250 credits**；
**Fast 为 2.5 倍**，不套用 API 的 Fast 倍率或 API 特有的附加收费。

`gpt-6-astra` 显示为 `6 Astra`。工具兼容 `gpt-6`、`gpt6` 这两个精确简写，
也能将 `gpt-6-astra-YYYY-MM-DD` 日期后缀形式按 Astra 家族计价；这些兼容规则
不表示它们都是官方 API ID。不会把 Pro、WM 等尚未核实费率的其他变体统一算成
Astra。Standard/Fast 分段识别，以及 `--fast` 仅补全 Unknown 的行为不变。

**不需要重建 cache。** 已缓存的 GPT-6 token 记录可以直接重新查询计价，quota
观测历史保留。本版只新增 GPT-6，不修改旧模型参考费率、已有校准数值坐标、
weekly-first 布局、144-cell 上限和项目/session 标题排版。公开 credits 费率
不是订阅 weekly 的官方换算比例；weekly 仍是带来源和可信度标记的估算。
详见[费率来源和兼容性说明](docs/v1.7.0-gpt6.md)。

## v1.6.2：加宽可读的 project-aware SESSION

v1.6.2 重新平衡 144-cell 摘要布局。加入 project 前缀后，旧 `--wide` 模式的 SESSION 只有约 18 格，往往只能看到 `[atomic-cross-mod…]`。现在全宽报告会给 SESSION **34 格**，并把 INPUT/CACHED/OUTPUT 合并为紧凑的 `TOKENS I/C/O`，例如 `95.2M/92.7M/405K`。

当 `[project] session name/title` 仍然过长时，会优先缩短 project tag，并为真正的 Codex session 名或标题保留空间。较窄终端中，`--wide` 会把 token 三元组放到下一条缩进行，而不是继续挤压 SESSION。144-cell 上限、Fast 统计、weekly 估算和 credit 计算均未改变，也不需要重建 cache。

## v1.6.1：项目感知的 session 名称

`SESSION` 列现在优先使用 Codex 界面中显式设置的 session 名称（`threads.name`），并在可用时把 Codex project 名称放在最前面。若没有显式名称，则组合 project 与 Codex 的 preview/title；旧版状态数据库会退回到仓库名或 cwd 目录名。这样，即使多个项目都使用同一套模板化首条指令，也能直接区分：

```text
[steerRL] Sparse-1 S3 对比实验
[knowing-to-see] 读取 AGENTS.md 并继续当前阶段
```

若多个可见 session 最终仍得到完全相同的标签，工具会追加稳定的短 session ID。DETAILS、JSON、CSV 也会提供 session name、thread title、project ID 和 project name。本次更新只读取 `state_5.sqlite` 元数据，不需要重建 token cache。

## v1.6.0：自动区分 Fast / Standard

v1.6.0 会读取 Codex 本地持久化的 service-tier 设置，并把每次累计 `token_count` 的增量归到当时实际生效的档位。`priority` 与 `fast` 统一识别为 **Fast**，`default` / null 识别为 **Standard**。因此，同一个 session 中途切换 Fast 时，可以分别统计，而不再只能把整段记录统一按 Standard 或 Fast 估算。

摘要新增 `TIER(S)`；DETAILS 新增 service-tier breakdown，Model 和 Agent 表也会显示档位，因而可以直接发现使用 Fast 的 subagent。

对缺少档位标记的旧记录，默认按 Standard 计算保守下界，并用 `+` / `≥` 标记不确定性。`--fast` 仍保留，但现在仅把 **Unknown 段**按 Fast 估算，不会覆盖已经识别出的 Standard / Fast。

v1.6 会自动让 token-event 缓存重建一次，以便逐事件保存 `service_tier`；历史 quota observations 会保留。tier-aware credits 使用新的 calibration revision，不会与 v1.5 的全局 Standard/Fast 坐标系混合。

## v1.5.5：weekly-first 使用体验

v1.5.5 调整了整个工具的产品语义：**订阅的 weekly allowance 成为第一使用指标**，`CREDITS*` 退到第二层，主要用于计价细节、cache tax 和调试。

报告顶部现在刻意区分：

```text
Subscription  Pro 5x · CURRENT WEEK 0.0% used / 100.0% left · reset 6d23h · snapshot now
Weekly scale  1% ≈ 180.0 credits* · LOW · historical rebase
Local this week≈ ≥0.48% · CREDITS* 86.2+
```

- `CURRENT WEEK`：本地最新 telemetry 中的 backend 当前周真值。
- `Local this week≈`：本机 transcript 能解释的当前周 quota 归因；即使 backend 仍因取整显示 `0.0%`，也可以给出本地估算。
- 表格里的 `WEEKLY≈`：**所选本地 usage 相当于一个完整 weekly allowance 的多少**。因此 `24h` 等查询即使跨过 weekly reset 仍然可以自然阅读；它并不声称这些 usage 全都属于当前 backend epoch。
- `1H≈`：最近 60 分钟消耗相当于 weekly allowance 的多少。

默认摘要的核心列顺序调整为：

```text
SESSION  MODEL(S)  TIER(S)  WEEKLY≈  1H≈  CREDITS*  CACHE TAX  SHARE  STATUS
```

DETAILS 中 Usage components、MAIN/SUB、Model、Agent breakdown 也统一把 `WEEKLY≈` 放在 credits 前面。

### 任何时点尽量都能给 weekly 数字

v1.5.5 使用分层 fallback：

1. 当前 rate card 下、干净 snapshot interval 学到的 **delta calibration**；
2. 当前/历史的 current-rate baseline，包括安全重新计价得到的 **historical rebase**；
3. 如果仍无本地可用 calibration，则使用低置信度的 **plan bootstrap seed**。

bootstrap 会明确显示 `SEED`，它只是经验启动值，不代表 OpenAI 官方公开了固定的 weekly credits；随着真实 local/backend observations 增加，会自动被更可信的 calibration 取代。

### interval calibration 与 Spark

backend snapshot 与本地累计 credits 现在分开保存。weekly 百分比变化时，工具只统计合适的前后 snapshot plateau 之间的本地 usage。如果某个 interval 含 Spark/未知价格模型，这一段只会被标记为 incomplete 并跳过学习；同一周后续干净 interval 仍然能够正常校准，因此不会再出现“本周出现一次 Spark，整周 calibration 都报废”的情况。


[English README](README.md)

`codex-usage` 是一个**非官方、本地优先的 Codex 用量分析工具**。它读取本机已经存在的 Codex 数据，主要回答一个实际问题：

> 我的 Codex 额度花在哪个 session 上、为什么这么贵，以及这些消耗大约占 GPT/Codex 每周订阅额度的多少？

核心工具仍然只有一个 Python 脚本，**正常使用零强制第三方依赖**，支持 macOS、Windows 10/11 和 Linux。

## v1.5.2：rate-card calibration rebase

v1.5.2 修复了一个更隐蔽的校准问题：当内置 token rate card 发生变化后，历史的 `credits / weekly %` baseline 与当前重新计算的 `CREDITS*` 已经不在同一个数值坐标系中。

现在工具只把旧 quota observation 当作**服务端锚点**，不直接复用旧的 local credits。对于当前 weekly reset epoch 内的历史锚点，它会从 weekly window 起点重放到该锚点时刻的本地 token usage，并使用当前 rate card 重新计价；成功后显示为 `LOW · rebased baseline`。

如果较新的锚点已经包含 GPT-5.3-Codex-Spark 这类未定价模型，会跳过它并继续尝试更早的锚点。如果没有任何锚点可以完整重算，calibration 会保持 `LEARNING`，而不会再退回旧费率的 credits/%。这样 `WEEKLY≈` 与屏幕上的 `CREDITS*` 始终处于同一 rate-card 坐标系。

## v1.5.1：未定价模型下的连续估算

v1.5.1 修复了真实使用中发现的主要边界情况：当本周出现 `GPT-5.3-Codex-Spark` 这类官方尚未给出最终 credits rate 的模型时，不再让整个 `WEEKLY≈` calibration 退回为 `—`。

- 如果某个 session 显示 `543.1+ CREDITS*`，`+` 表示已定价部分可以计算，但还包含未定价模型；只要已有 calibration，`WEEKLY≈` 会显示为类似 `≥3.15%` 的**下界**。
- 当前 weekly window 不完整时不会写入新的 calibration observation，但会继续使用已经学到的 calibration。
- 内置 token rate card 已同步到当前官方值：GPT-5.6 Terra 为 `62.5 / 6.25 / 375`，GPT-5.6 Luna 为 `25 / 2.5 / 150`，GPT-5.3-Codex 与 GPT-5.2 为 `43.75 / 4.375 / 350` credits / 1M input、cached input、output tokens。GPT-5.3-Codex-Spark 仍保持未定价，因为官方仍将其标记为 research preview。
- calibration 按内部 rate-card revision 隔离。v1.5.0 的旧 calibration 可以暂时作为 `LOW · prior-rate fallback` 展示，但不会和 v1.5.1 的新观测混在一起做 delta 学习。
- baseline 阶段不再显示 `local coverage≈100%`，因为该值由定义恒等得到；只有真正产生独立 delta calibration 后才显示 local coverage。

## v1.5.0：订阅额度估算

v1.5.0 增加了两种**刻意区分**的 quota 信息：

- **`WEEKLY`**：从本地 Codex rollout telemetry 中读到的最新 backend weekly 已用/剩余百分比。这是服务端返回的 quota snapshot，不是根据 token 反推出来的。
- **`WEEKLY≈`**：估算某个本地 session 消耗了 weekly allowance 的多少。它通过本机重建的 `CREDITS*` 与多次 backend weekly 百分比观测之间的关系自适应学习。

示例：

```text
Codex usage — last 6h (...) — CST (UTC+08:00)
Credit mode: Standard credits (rate card 2026-08-12)
Subscription  Pro 5x · WEEKLY 43.0% used / 57.0% left · reset 3d18h · snapshot 20s
Calibration   1% weekly ≈ 397.0 credits* · MEDIUM · 4 clean / 6.0pp · local coverage≈91%

SESSION                         MODEL(S)       CREDITS*  WEEKLY≈  CACHE TAX  1H BURN  SHARE  STATUS
/goal durable ultragoal         5.6 Sol / Luna    814.1     2.05%      632.5     134.5  60.9%  ACTIVE/WATCH
另一个任务                       5.6 Sol            203.1     0.51%      125.1     203.1  15.2%  ACTIVE/OK
```

`WEEKLY≈` 明确带 `≈`：它是**归因估算**，不是 OpenAI 官方 billing/quota meter。

## 主要功能

- 按 session 统计 `today`、`yesterday`、指定日期、日期范围，以及 `6h`、`12h`、`24h` 和任意 `Nh` 滚动时间窗口。
- 按模型、MAIN agent、subagent 估算 credits。
- `CACHE TAX`：cached input 单独贡献的估算 credits。
- `1H BURN`：最近 60 分钟观察到的 credits 消耗速度。
- `ACTIVE` / `RECENT` / `IDLE` 和 `OK` / `WATCH` / `ROTATE` 工作流提示。
- **v1.5：** 本地 ChatGPT plan 识别、backend weekly quota snapshot、自适应 `CREDITS* → WEEKLY≈` 校准、confidence 与 local coverage。
- 增量 SQLite 索引与 hot discovery；首次扫描后只读取有变化的 rollout 尾部。
- 彩色终端、中文/CJK terminal-cell 对齐、最大 144-cell 阅读栏。
- JSON / CSV 输出。
- Windows PowerShell 安装器与 CMD launcher。
- Windows / macOS / Linux × Python 3.9 / 3.13 CI。

## 环境要求

- Python **3.9+**
- 本机安装 Codex，session transcript 位于 `$CODEX_HOME` / `%CODEX_HOME%`，或通过 `--codex-home` 指定
- macOS、Windows 10/11 或 Linux

正常使用不需要额外 Python 包。

## 安装

### macOS / Linux

```bash
git clone https://github.com/yza167-jp/codex-usage.git
cd codex-usage
mkdir -p ~/.local/bin
install -m 755 codex-usage ~/.local/bin/codex-usage
```

确保 `~/.local/bin` 在 `PATH` 中，然后：

```bash
codex-usage --version
codex-usage 6h
```

已有本地 clone 时更新：

```bash
cd /path/to/codex-usage
git pull
install -m 755 codex-usage ~/.local/bin/codex-usage
```

### Windows PowerShell

```powershell
git clone https://github.com/yza167-jp/codex-usage.git
cd codex-usage
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

默认安装到：

```text
%LOCALAPPDATA%\Programs\codex-usage
```

重新打开终端：

```powershell
codex-usage --version
codex-usage 6h
```

WSL 按 Linux 使用；如有需要，用 `--codex-home` 指向 WSL 能看到的 Codex home。

## 常用命令

```bash
codex-usage 6h
codex-usage 12h
codex-usage 24h
codex-usage today
codex-usage yesterday
codex-usage week
codex-usage 168h
codex-usage 2026-08-12
codex-usage 2026-08-01..2026-08-12
```

常用视图：

```bash
codex-usage 6h --details
codex-usage 24h --wide
codex-usage 24h --show-subagents
codex-usage 24h --details --all-agents
codex-usage 24h --perf
codex-usage 24h --json
codex-usage 24h --csv
```

完全关闭 v1.5 的订阅/quota 读取与估算：

```bash
codex-usage 6h --no-quota
```

## v1.5 如何读取订阅状态

这是一个早期本地工具，v1.5 优先选择实现简单。

### Plan 类型

脚本直接读取：

```text
$CODEX_HOME/auth.json
```

并解码本地 ID token 的 payload，取得 ChatGPT plan。当前显示映射为：

| Codex plan value | `codex-usage` 显示 |
|---|---|
| `plus` | Plus |
| `prolite` | Pro 5x |
| `pro` | Pro 20x |

这里的 `Pro 5x / Pro 20x` 是本工具采用的显示名称；真正用于隔离校准 regime 的是 backend plan value。

### Weekly quota snapshot

最近的 rollout JSONL 里有 `token_count` event。当前 Codex 协议允许它携带 `rate_limits`，包括：

```text
used_percent
window_minutes
resets_at
plan_type
```

`codex-usage` 会查看最近修改的多个 rollout 尾部，按 event timestamp 选择最新的 Codex rate-limit snapshot，并通过约 **10080 分钟（7 天）**识别 weekly window，而不是假定 `primary` 或 `secondary` 永远代表 weekly。

因此：

```text
WEEKLY 43% used / 57% left
```

来自 backend snapshot。脚本同时显示 snapshot age，方便识别 stale telemetry。

## `WEEKLY≈` 如何自适应学习

脚本在原有 SQLite cache 中额外保存 quota observation，只存校准需要的元信息：

```text
哈希后的本地账户分段键
plan type
weekly reset timestamp
weekly used percent
本机 credit-equivalent usage
rate-card version
standard / fast credit mode
snapshot timestamp / source
```

**不会**把原始 access token、refresh token、ID token 复制进 `codex-usage` 的数据库，也不会主动打印这些 token。

### 第一次估算

拿到 weekly snapshot 后，脚本会从当前 weekly window 的起点到 snapshot 时刻，重建本机累计 credits。

假设 backend 显示：

```text
weekly used = 40%
```

本地历史重建得到：

```text
15,200 CREDITS*
```

则第一次会得到：

```text
1 weekly percentage point ≈ 380 CREDITS*
effective weekly capacity ≈ 38,000 CREDITS*
confidence: LOW
```

这里**不是**说 OpenAI 给了 38,000 个可购买 credits；它只是为了把 included weekly allowance 映射到一个有效的 credit-equivalent 坐标系。

### 多次查询后逐渐校准

随着 Codex 产生新的 quota snapshot，脚本在同一个 weekly reset epoch 内学习：

```text
Δ 本机 CREDITS* / Δ backend weekly used%
```

估计器使用 weighted median，并过滤明显偏低/偏高的 interval。

如果 backend weekly% 增长很多、但本机 credits 几乎没变，这通常说明还有本工具看不到的 quota 消耗来源；这种 interval 不应该直接把 conversion ratio 拉低。

Confidence 大致分为：

- `LEARNING`：还没有可用换算关系
- `LOW`：只有初始 baseline，或有效 quota movement 太少
- `MEDIUM`：已有多个 clean delta interval
- `HIGH`：已有多个相互一致的 interval，并覆盖了足够的 weekly 百分比变化

校准会按 account、plan、rate-card version、credit mode、weekly reset epoch 分段。换套餐或进入新的 weekly window 时，不会简单把旧 epoch 当成同一个观测序列。

## Local coverage

`local coverage≈` 表示在当前 calibration 下，backend weekly used% 中有多少大致可以被本机 transcript 中的 credits 解释。

如果它很低，可能意味着：

- 另一台设备也在用 Codex；
- 还有本机 transcript 看不到的 agentic usage；
- 当前 calibration 样本还太少。

它只是诊断指标，不是账户审计结果。

## Credits 估算

`CREDITS*` 来自本地 token counter 和内置 rate card。由于 cached input 是 input 的子集：

```text
uncached input = input - cached input
credits* = uncached input component + cached input component + output component
```

Reasoning tokens 是 output 的细分，不会重复收费。

`codex-usage` 会从持久化的 `turn_context` / `thread_settings_applied` 设置重建实际档位；`priority` 视为 Fast。缺少档位标记时默认按 Standard 给出保守下界；`--fast` 只把这些 Unknown 段按 Fast 估算，不会覆盖已经识别出的 Standard / Fast。

`CREDITS*` 与 `WEEKLY≈` 都不是 OpenAI 官方服务端账单/额度 meter。

## Cache 与性能

默认 cache：

- macOS：`~/Library/Caches/codex-usage/index-v2.sqlite3`
- Windows：`%LOCALAPPDATA%\codex-usage\index-v2.sqlite3`
- Linux：`$XDG_CACHE_HOME/codex-usage/index-v2.sqlite3`，否则 `~/.cache/codex-usage/index-v2.sqlite3`

cache 保存 token-event index 与 quota calibration observations，不复制完整 prompt / response。

第一次扫描后，未变化的 rollout JSONL 不会重复读取；仍在追加的文件只解析新尾部。v1.5 第一次运行时，为了建立 weekly baseline，可能需要额外扫描当前 weekly window 内尚未索引的文件；之后继续走增量缓存。

诊断命令：

```bash
codex-usage 24h --perf
codex-usage --cache-info
codex-usage 24h --full-discovery --perf
codex-usage 24h --no-cache
```

从 v1.4.x 升级到 v1.5.0 一般**不需要** rebuild cache；`quota_observations` 是增量添加的新表。

## 时区

默认使用系统本地时区，并同时显示时区简称/名称和 UTC offset，例如：

```text
CST (UTC+08:00)
```

也可以显式指定 IANA 时区：

```bash
codex-usage 24h --timezone Asia/Tokyo
```

Windows 的 Python 不一定自带 IANA timezone database；系统本地时间无需额外包，显式 IANA zone 可能需要可选 `tzdata`。

## 隐私 / 信任边界

本工具是 local-first，但 **v1.5 会直接读取 `auth.json`**，而这是一个包含凭据的 Codex 文件。当前实现只解码 plan / account segmentation 所需元信息，不主动打印原始 token，也不把原始 token 存进自己的 SQLite。

如果以后把工具给更多人使用，应把这段代码当作“能读取 Codex home 凭据”的代码来审计。

如果不希望脚本读取订阅/auth metadata：

```bash
codex-usage 6h --no-quota
```

## 局限

- 本机 transcript 无法证明 weekly usage 全部来自这台机器。
- OpenAI/Codex 的 quota 语义和 plan 行为可能独立变化。
- release 内置的 credit rate card 未来可能过期。
- `WEEKLY≈` 在积累多次观测后才更有价值；如果本周大量 usage 发生在别处，第一次 baseline 会有偏差。
- included weekly allowance 达到 100% 后，额外购买/flexible credits 是另一套概念，不应该把 `WEEKLY≈` 理解成 100% 以上还能继续增加的订阅百分比。

## License

MIT，见 [LICENSE](LICENSE)。
