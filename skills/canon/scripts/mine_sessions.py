"""从 Codex / Claude Code 的历史会话里挖「当时做了决定却没写下来」的候选。

用法：
    python mine_sessions.py <项目仓库根目录> [--out 候选文件.json] [--all]

为什么需要它：ADR 要记的是**唯一不能从仓库推导的东西**——「否掉了哪个可行方案」。
那些讨论只存在于会话记录里。代码、git log、文档都答不上来。

产出是**候选清单，不是 ADR**。反推出来的是猜测，必须交用户逐条确认（见 SKILL.md
「什么时候停下来交给用户」）。

## 两个必须知道的陷阱（都是实跑踩出来的）

1. **`role: user` 不等于用户说的话。**
   - Codex 把 `<codex_internal_context>`、review-agent 提示、子 agent 通知都标成 user。
     实测一次：172 条候选里 117 条是注入。
   - Claude Code 把 **tool_result** 塞在 `type: "user"` 里。实测一次：1371 条 user
     里只有 114 条是真打字的，其余 1249 条是工具输出。
   不剔干净的话，挖出来的全是噪声。

2. **会话是重放式的**：每轮把历史再写一遍。去重前体积放大约 3.5 倍。

## 判据

只留可能构成 ADR 的：命中「否决 / 取舍 / 追问原因 / 硬边界」类标记的消息。
纯拍板（「可以」「就这么办」）不留——没有被否掉的方案，就不值得立 ADR。

输出的候选**必须再做一步**：逐条对照仓库现有 ADR 与 active 文档，已记录的不重复列。
脚本不做这一步，因为「算不算已记录」是语义判断。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

CODEX_ROOTS = [Path.home() / ".codex" / "sessions", Path.home() / ".codex" / "archived_sessions"]
CLAUDE_ROOT = Path.home() / ".claude" / "projects"

# 决策标记：ADR 判据是「否掉了别的可行方案，且将来有人会问为什么不那样做」
STRONG = re.compile(
    r"不做|别做|不要做|放弃|砍掉|先不|暂不|没必要|不值得|不用了|改成|换成|改用|还是用|不如"
    r"|为什么不|为什么要|依据是|理由是|不得|禁止|明确不|不能|不再|不应|不允许"
)
WEAK = re.compile(r"就这么|按这个|确认|拍板|定了|同意|必须|只能|恒|永久|倾向|应该用")

# 每轮任务模板里重复出现的操作性约束，不是项目决策
BOILERPLATE = re.compile(
    r"不启动 MATLAB|不跑全量测试|不安装依赖|git diff --name-only|不跑完整|只跑相关聚焦|如实记录"
)

# harness 注入 / 系统块：标成 user 但不是用户说的
HARNESS_PREFIXES = (
    "<", "The following is the Codex agent history", "# 全局工作偏好",
    "## My request for Codex", "PLEASE IMPLEMENT THIS PLAN:", "Caveat:",
    "This session is being continued", "[SYSTEM NOTIFICATION",
)
HARNESS_CONTAINS = ("<system-reminder>", "<local-command-caveat>", "<command-name>", "<command-message>")


def _is_harness(text: str) -> bool:
    head = text[:200]
    return text.startswith(HARNESS_PREFIXES) or any(s in head for s in HARNESS_CONTAINS)


def _texts_from_codex(payload: dict) -> list[str]:
    out: list[str] = []
    content = payload.get("content")
    if isinstance(content, str):
        out.append(content)
    elif isinstance(content, list):
        out += [p["text"] for p in content
                if isinstance(p, dict) and isinstance(p.get("text"), str)]
    if isinstance(payload.get("message"), str):
        out.append(payload["message"])
    return out


def _texts_from_claude(record: dict) -> list[str]:
    """Claude Code：只取 content 为 str 的，或 list 里 type=='text' 的。

    **不要**取 type=='tool_result'——那是工具输出，占 user 条目的九成以上。
    """
    if record.get("type") != "user":
        return []
    content = record.get("message", {}).get("content")
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [p["text"] for p in content
                if isinstance(p, dict) and p.get("type") == "text" and isinstance(p.get("text"), str)]
    return []


def harvest_codex(repo: Path, seen: set[str], rows: list[dict]) -> int:
    """按每个 rollout 首行的 payload.cwd 过滤——别按线程名，名字筛不准。"""
    target = repo.name.lower()
    files = 0
    for root in CODEX_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.jsonl")):
            try:
                handle = path.open(encoding="utf-8", errors="replace")
            except OSError:
                continue
            with handle:
                try:
                    cwd = json.loads(handle.readline()).get("payload", {}).get("cwd", "")
                except (ValueError, AttributeError):
                    continue
                if target not in cwd.lower().replace("/", "\\"):
                    continue
                files += 1
                day = path.stem[8:18]
                for line in handle:
                    try:
                        payload = json.loads(line).get("payload", {})
                    except ValueError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    if not (payload.get("type") == "user_message" or payload.get("role") == "user"):
                        continue
                    for text in _texts_from_codex(payload):
                        _consider(text, day, "codex", seen, rows)
    return files


def harvest_claude(repo: Path, seen: set[str], rows: list[dict]) -> int:
    """Claude 按项目目录 slug 定位：绝对路径里的分隔符与冒号都换成 '-'。"""
    slug = str(repo.resolve()).replace(":", "-").replace("\\", "-").replace("/", "-")
    project_dir = CLAUDE_ROOT / slug
    if not project_dir.is_dir():
        return 0
    files = 0
    for path in sorted(project_dir.glob("*.jsonl")):
        files += 1
        for line in path.open(encoding="utf-8", errors="replace"):
            try:
                record = json.loads(line)
            except ValueError:
                continue
            day = (record.get("timestamp") or "")[:10]
            for text in _texts_from_claude(record):
                _consider(text, day, "claude", seen, rows)
    return files


def _consider(text: str, day: str, source: str, seen: set[str], rows: list[dict]) -> None:
    text = text.strip()
    if len(text) < 15 or _is_harness(text):
        return
    digest = hashlib.sha1(text.encode()).hexdigest()
    if digest in seen:
        return
    seen.add(digest)
    if STRONG.search(text) or len(WEAK.findall(text)) >= 2:
        rows.append({"day": day, "source": source, "len": len(text), "text": text})


def decision_lines(text: str, limit: int = 8) -> list[str]:
    out = []
    for line in re.split(r"[\n。；;]", text):
        line = line.strip(" -*·\t")
        if 8 < len(line) < 240 and STRONG.search(line) and not BOILERPLATE.search(line):
            out.append(line)
    return out[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("repo")
    parser.add_argument("--out", default="session_decision_candidates.json")
    parser.add_argument("--all", action="store_true", help="打印全文而不是决策句")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    if not repo.is_dir():
        print(f"不是目录：{repo}")
        return 1

    seen: set[str] = set()
    rows: list[dict] = []
    n_codex = harvest_codex(repo, seen, rows)
    n_claude = harvest_claude(repo, seen, rows)
    rows.sort(key=lambda r: (r["day"], r["source"]))

    print(f"项目：{repo}")
    print(f"命中会话：Codex {n_codex} 份 / Claude {n_claude} 份")
    if n_codex == n_claude == 0:
        print("→ 没找到该项目的会话记录。确认项目名与当时的工作目录一致。")
        return 0

    out_path = Path(args.out)
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(r["len"] for r in rows)
    print(f"决策候选：{len(rows)} 条，{total / 1024:.0f} KB → {out_path}")

    from collections import Counter
    print("按月：", dict(sorted(Counter(r["day"][:7] for r in rows).items())))
    print("\n" + "=" * 74)
    for i, row in enumerate(rows):
        if args.all:
            print(f"\n### [{i}] {row['day']} ({row['source']}, {row['len']} 字)\n{row['text']}")
            continue
        hits = decision_lines(row["text"])
        if hits:
            print(f"\n### [{i}] {row['day']} ({row['source']})")
            for hit in hits:
                print(f"  · {hit}")

    print("\n" + "=" * 74)
    print("下一步（脚本不做，需要语义判断）：")
    print("  1. 逐条对照仓库现有 ADR 与 active 文档，已记录的**不重复列**——重复立会造双权威")
    print("  2. 只留「否掉了别的可行方案、且将来有人会问为什么不那样做」的")
    print("  3. 产出 4 栏候选表：日期 | 当时定了什么 | 否掉了哪个方案 | 今天还成立吗")
    print("  4. 交用户逐条确认后再写 ADR。ADR 只被取代、不被改写——只能新增，不能「补完整」旧的")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
