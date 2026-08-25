# agent-skills-profile

**A shared skill library + `AGENTS.md` for Claude Code and Codex CLI**, with a one-command
install/sync script and a curated skill set: TDD, disciplined bug diagnosis, a bounded
review-fix loop, doc governance (`canon`), a codebase knowledge-graph workflow
(`codebase-memory-mcp`), Office document editing (`officecli`), and a Matt-Pocock-sourced
architecture-improvement chain (`improve-codebase-architecture` / `codebase-design` /
`domain-modeling` / `grilling`). See [`scripts/install.ps1`](scripts/install.ps1) /
[`scripts/install.sh`](scripts/install.sh) to deploy this on a new machine in one shot.

---

个人编程风格迁移包。**Codex 与 Claude Code 共用**——两边各挂一个目录联接指向本仓库，
所以只有这一份真身，不存在两处拷贝各改各的。

## 内容

`AGENTS.md`：全局工作偏好，装到 `~/.codex/AGENTS.md`。

`deploy-manifest.txt`：**哪些 skill 默认装到本机**的清单，`scripts/install.*` 读这份文件
决定装什么、不装什么——参见下面「在新电脑恢复」。改"装不装"直接改这份清单，不用改脚本。

Claude Code 侧的用户指令**不在本仓库治理范围内**——它没有对应文件（内容在应用设置里），
由使用者自行维护。要同步时以 `AGENTS.md` 为准，去掉末尾 `codebase-memory-mcp` 标记块即可
（Claude 侧那部分由 SessionStart hook 注入，再写进偏好就是同一客户端内的重复）。

### 工作流程

- `skills/clarify`：新需求开始前的澄清流程，防技术债。
- `skills/review-fix-loop`：代码 review、自动修复、聚焦验证、再次复审。
- `skills/zoom-out`：要求给出更高层的上下文与全局视角。

### Matt Pocock 系（`skills/matt-pocock/`）

以下六个都原样／改名搬自 [mattpocock/skills](https://github.com/mattpocock/skills)，统一放进
`skills/matt-pocock/` 子目录，跟自研的 skill 分开，方便审计和跟上游对比：

- `skills/matt-pocock/tdd`：红-绿-重构循环，附接口设计 / mock / 重构 / 深模块四篇参考。
  （同名 `tdd`）
- `skills/matt-pocock/diagnose`：诊断和调试流程，reproduce → minimise → hypothesise →
  instrument → fix → regression-test 六阶段。（原名 `diagnosing-bugs`，改了名字，内容基本原样）
- `skills/matt-pocock/improve-codebase-architecture`：扫描代码库找「可加深模块」的机会，
  出一份可视化 HTML 报告，再逐个候选项 grill 下去。（同名）依赖同目录下的
  `codebase-design` / `grilling` / `domain-modeling`，三者都已收录，链路完整。
- `skills/matt-pocock/codebase-design`：深模块设计的共享词汇与纪律（module / interface /
  depth / seam / adapter / leverage / locality），`improve-codebase-architecture` 用它来
  统一措辞。（同名）
- `skills/matt-pocock/grilling`：逼问式访谈的可复用原语，`improve-codebase-architecture`
  第 3 步用它跟你逐个过设计决策。（同名）
- `skills/matt-pocock/domain-modeling`：维护项目领域模型（`CONTEXT.md` + ADR），挑战术语、
  用边界场景压测。（同名）

装的时候用 `skills/tdd`、`skills/diagnose` 等**扁平名字**链接到本地（见下面的恢复脚本），
调用方式不变，只是仓库里的物理路径多了一层 `matt-pocock/`。

### 文档与代码理解

- `skills/canon`：文档治理。按「改动触发条件」把文档分成五类（需求 / 架构 / 执行计划 /
  handoff / ADR 索引），覆盖新项目建立、接手反推、推进中维护、周期性审计，并生成守卫测试。
- `skills/codebase-memory`：结构化代码查询走知识图谱，而不是 grep。

### 界面与产物

- `skills/streamlit-feature-change`：Streamlit 功能增删改后的接线与 session 状态检查。
- `skills/redesign-skill`：审计既有界面里的通用 AI 味，按高完成度标准重做。
- `skills/officecli`：用 officecli 创建 / 分析 / 校对 / 修改 .docx / .xlsx / .pptx。

### 研究与文献

- `skills/paper-daily-brief`：独立检索学术 API（PubMed / Europe PMC / OpenAlex /
  bioRxiv / medRxiv / Crossref），去重分类、维护候选库、产出带证据的中文简报。
  **不依赖 PaperSort**，可单独运行。
  `config.example.toml` 里的检索式与三个主题词表是调好的值，复制成 `config.toml` 再填
  `contact_email` 即可；API key 走各 `*_api_key_env` 指定的环境变量，不写进文件。

  **当前未本地部署**：面向的是需要每天扫学术文献的用户，不是当前使用者的日常需求。
  代码保留在仓库里（配置和依赖库都没装），需要时再按上面的步骤装，不必因为没装而重写。

## 在新电脑恢复

### 一键（推荐）

```powershell
git clone https://github.com/77652189/agent-skills-profile.git C:\path\to\agent-skills-profile
C:\path\to\agent-skills-profile\scripts\install.ps1
```

```bash
git clone https://github.com/77652189/agent-skills-profile.git ~/path/to/agent-skills-profile
~/path/to/agent-skills-profile/scripts/install.sh
```

脚本做的事：clone / pull 本仓库 → 把 `AGENTS.md` 合到 `~/.codex/AGENTS.md`（保留本机
`codebase-memory-mcp` 标记块已经装好的内容，不会覆盖回仓库里的占位版本）→ 按
`deploy-manifest.txt` 同步 `~/.codex/skills` 和 `~/.claude/skills` 的链接（清单里有、本地
没装的会补上；本地有链接、但清单里已经删掉的会拆掉）→ 检查 `codebase-memory-mcp` 和
`officecli` 这两个外部工具，没装就装上。

**可以随时重新跑**，用来同步最新状态，不止是第一次恢复用：改了 `deploy-manifest.txt`、
或者仓库有新 commit，再跑一次这个脚本就同步好了，不用手动比对。

参数：

- `-SkipTools` / `SKIP_TOOLS=1`：只同步 skill 链接，不碰 `codebase-memory-mcp` /
  `officecli` 这两个外部工具（比如已经手动装过，或者暂时不想碰全局配置）
- `-RepoPath` / `REPO_PATH=`：clone/更新到自定义位置，默认
  `~/Documents/Codex/agent-skills-profile`

脚本内部就是下面「手动等价操作」里的那几步，遇到脚本报错或者想改自动化逻辑本身时，
照着手动步骤逐条排查即可。

### 手动等价操作

不想用脚本，或者脚本坏了要手动排查时，参考下面的等价操作。**推荐链接**：改任何一侧
都是改本仓库，不会出现两份拷贝各自漂移。

**跟脚本的两点差异**，手动操作时留意：下面这几段会把 `skills/` 和 `skills/matt-pocock/`
下**所有**目录都链接上（包括 `deploy-manifest.txt` 故意排除的 `paper-daily-brief`）；
`Copy-Item "$REPO\AGENTS.md" ...` 会**直接覆盖** `~/.codex/AGENTS.md`，把本机
`codebase-memory-mcp` 标记块里已经装好的内容也覆盖掉——脚本会保留那部分，手动执行完
之后如果装过那个 MCP 服务器，记得重新跑一次它的安装器把标记块内容补回来。

Windows PowerShell（`REPO` 换成本仓库的绝对路径）：

```powershell
$REPO = "C:\path\to\agent-skills-profile"
Copy-Item "$REPO\AGENTS.md" $HOME\.codex\AGENTS.md -Force
# 顶层 skill 目录，加上 matt-pocock/ 下嵌套的每一个，链接时都拍平成同一层
$skillDirs = Get-ChildItem "$REPO\skills" -Directory | Where-Object { $_.Name -ne "matt-pocock" }
$skillDirs += Get-ChildItem "$REPO\skills\matt-pocock" -Directory
foreach ($d in $skillDirs) {
  foreach ($home_dir in @("$HOME\.codex\skills", "$HOME\.claude\skills")) {
    New-Item -ItemType Directory $home_dir -Force | Out-Null
    $link = Join-Path $home_dir $d.Name
    if (Test-Path $link) { cmd /c rmdir $link }
    cmd /c mklink /J $link $d.FullName
  }
}
```

macOS 或 Linux：

```bash
REPO=~/path/to/agent-skills-profile
cp "$REPO/AGENTS.md" ~/.codex/AGENTS.md
for d in "$REPO"/skills/*/ "$REPO"/skills/matt-pocock/*/; do
  [ "$(basename "$d")" = "matt-pocock" ] && continue
  for home_dir in ~/.codex/skills ~/.claude/skills; do
    mkdir -p "$home_dir"
    ln -sfn "$d" "$home_dir/$(basename "$d")"
  done
done
```

代价：本仓库被移走或删掉，两个客户端的 skill 同时失效。

### 拷贝

```bash
cp AGENTS.md ~/.codex/AGENTS.md
for target in ~/.codex/skills ~/.claude/skills; do
  mkdir -p "$target"
  find skills -mindepth 1 -maxdepth 1 ! -name matt-pocock -exec cp -R {} "$target/" \;
  cp -R skills/matt-pocock/. "$target/"
done
```

恢复后重启客户端，让全局指令和 skills 重新加载。

验证 Codex 是否真的登记了某个 skill，不用真跑一轮模型：

```bash
codex debug prompt-input "hi" | grep -o '.\{0,40\}canon.\{0,120\}'
```

### 外部活拷贝（审计时逐对比这一份清单）

装到别处、且**实际生效的是那一份**的文件。仓库里这份会悄悄变旧，周期性审计要核。

| 仓库里 | 装在哪 | 形式 | 会漂吗 |
| --- | --- | --- | --- |
| `AGENTS.md` | `~/.codex/AGENTS.md` | **拷贝** | **会**——单文件不能做目录联接。`codebase-memory-mcp` 标记块尤其容易漂：装那个 MCP 服务器时，它的安装脚本会直接改写本机那份 `~/.codex/AGENTS.md` 里的标记块内容，仓库里这份不会跟着变 |
| `skills/*`、`skills/matt-pocock/*` | `~/.codex/skills/`、`~/.claude/skills/`（`officecli` 另经 `~/.agents/skills/`） | 联接（本地按扁平名字挂，不带 `matt-pocock/` 这层） | 不会 |

```bash
diff <(tr -d '\r' < AGENTS.md) <(tr -d '\r' < ~/.codex/AGENTS.md) && echo "AGENTS.md 一致"
```

这类一致性**没法写成守卫测试**：干净 clone 上外部那份不存在，断言会静默通过，
结论因机器而异。只能进审计清单。

## 外部依赖分类（恢复时按这张表办）

原则：**有外部上游的，优先从上游装；本仓库这份只作备份和用法约定。**
自研的反过来——本仓库即唯一真身，没有地方可下载。

| skill | 有没有外部上游 | 恢复时怎么做 |
| --- | --- | --- |
| `officecli` | 有：`officecli` CLI 工具 | 先装工具。skill 本身只是调用约定，工具不在就没用 |
| `codebase-memory` | 有：`codebase-memory-mcp`（见下节） | 先装 MCP 服务器并为仓库建索引 |
| `tdd` · `diagnose` · `improve-codebase-architecture` · `codebase-design` · `grilling` · `domain-modeling`（全放在 `skills/matt-pocock/`） | **有：[mattpocock/skills](https://github.com/mattpocock/skills)**（Matt Pocock 的公开 skills 库） | 换新机器时可以直接从上游 clone 对比，看这份本地拷贝有没有落后 |
| `clarify` · `zoom-out` · `redesign-skill` · `streamlit-feature-change` · `review-fix-loop` | **无，自研** | clone 完就能用，纯文本流程，不装任何东西 |
| `canon` | 半有 | 三个 Python 脚本自带；但 `scripts/mine_sessions.py` 读的是 `~/.codex/sessions` 与 `~/.codex/archived_sessions`，**换新机器后那里是空的，挖不出东西**——这不是坏了，是没有历史可挖 |
| `paper-daily-brief` | **无上游，自研** | **一般不需要下载**：本仓库这份就是真身。只需 `pip` 装脚本用到的库、复制 `config.example.toml` |

被删掉的：`codex@openai-codex` 插件（2026-08-13 移除，随之失效的是 `codex:*` 系列
skill）。`review-fix-loop` 的描述里把 "Codex" 当触发词提过，但它的机制不依赖该插件，
删掉不影响使用。要装回来：marketplace `github.com/openai/codex-plugin-cc`。

## codebase-memory-mcp

这里只保存链接和安装命令，不把 MCP 本体或本机配置放进仓库。

- 仓库链接：https://github.com/DeusData/codebase-memory-mcp

Windows PowerShell：

```powershell
git clone https://github.com/DeusData/codebase-memory-mcp.git
cd codebase-memory-mcp
powershell -ExecutionPolicy Bypass -File .\install.ps1 --ui
```

安装后按该项目说明重启 Codex，并为需要图谱的仓库执行索引。
