"""扫描仓库里的 markdown 文档：路径、大小、最后改动、git 跟踪状态。

只读**元数据**，不读正文——避免把私有/保密文档的内容吸进上下文。

用法：
    python scan_docs.py [仓库根目录] [--all]

输出四段：
  1. 已跟踪文档 —— 治理对象，逐条列
  2. 未跟踪但可见 —— git add 会把它们带进来，要么纳入要么删
  3. 被 gitignore 的文档 —— 按顶层目录聚合。守卫测试**不要**扫这些：
     干净 clone 上不存在，断言会静默通过，结论因机器而异
  4. 混合目录 —— 整体被忽略、里面却有文件仍被跟踪，最易误判"整个目录都是私有的"

实现注记：所有 git 调用都用 `-z`（NUL 分隔）。默认输出会对含非 ASCII 或特殊字符的
路径做 C 引用（加引号、转义反斜杠），按行解析会把路径切坏。
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

SKIP_DIRS = {
    ".git", ".claude", ".idea", ".vscode",
    "node_modules", ".venv", "venv", "site-packages", "__pycache__",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".next", "target", "vendor",
}
MAX_LISTED = 60
MAX_DIRS_LISTED = 12


def _git_paths(repo: Path, *args: str) -> set[str] | None:
    """跑 `git ls-files -z ...`，返回 POSIX 风格相对路径集合；不可用时返回 None。"""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z", *args], cwd=repo,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except (OSError, ValueError):
        return None
    if proc.returncode != 0:
        return None
    return {piece for piece in proc.stdout.split("\0") if piece}


def find_docs(repo: Path) -> list[Path]:
    """走目录树找 *.md，剪掉噪声目录和**嵌套的 git 仓库/worktree**。

    嵌套 worktree 各带一整份 docs/，不剪掉会让同名文档重复出现好几遍。
    """
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo):
        here = Path(dirpath)
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not (here / d / ".git").exists()
        ]
        found.extend(here / name for name in filenames if name.endswith(".md"))
    return sorted(found)


def _print_listing(rows: list[tuple[str, Path]], list_all: bool) -> None:
    # 按 (目录, 文件名) 排序而不是整串路径——否则 docs/adr/ 会插在 docs/README.md 与
    # docs/handoff.md 之间，同一个目录标题被打印两次。
    rows = sorted(rows, key=lambda item: (str(Path(item[0]).parent), Path(item[0]).name))
    shown = rows if list_all or len(rows) <= MAX_LISTED else rows[:MAX_LISTED]
    current_dir = None
    for rel, path in shown:
        parent = str(Path(rel).parent)
        if parent != current_dir:
            print(f"\n[{parent}]")
            current_dir = parent
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
        print(f"  {stat.st_size / 1024:>7.1f} KB  {mtime}  {Path(rel).name}")
    if len(shown) < len(rows):
        print(f"\n  …… 另有 {len(rows) - len(shown)} 份未列出（--all 全列）")


def _top_dir(rel: str) -> str:
    parts = Path(rel).parts
    return parts[0] if len(parts) > 1 else "."


def main() -> int:
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    list_all = "--all" in sys.argv
    repo = Path(argv[0] if argv else ".").resolve()
    if not repo.is_dir():
        print(f"不是目录：{repo}")
        return 1

    docs = find_docs(repo)
    if not docs:
        print(f"{repo} 下没找到 markdown 文档")
        return 0

    by_rel = {p.relative_to(repo).as_posix(): p for p in docs}
    tracked = _git_paths(repo, "--", "*.md")
    in_git_repo = tracked is not None
    # 未跟踪且未被忽略 = git status 里会显示、git add -A 会带进来的那批
    visible_untracked = _git_paths(repo, "--others", "--exclude-standard", "--", "*.md") or set()
    # 被忽略 = 磁盘上有，但既不在跟踪列表、也不在"可见未跟踪"列表里
    tracked = tracked or set()
    ignored = {rel for rel in by_rel if rel not in tracked and rel not in visible_untracked}

    print(f"仓库：{repo}")
    if not in_git_repo:
        print("⚠ 不是 git 仓库（或 git 不可用）——跟踪状态无从判断\n")
        _print_listing(sorted(by_rel.items()), list_all)
        return 0

    print(f"共 {len(docs)} 份 markdown："
          f"已跟踪 {len(tracked & by_rel.keys())}，"
          f"未跟踪可见 {len(visible_untracked & by_rel.keys())}，"
          f"被忽略 {len(ignored)}\n")

    # ---- 1. 已跟踪：治理对象 ----
    print("=" * 78)
    print("① 已跟踪文档（治理对象）")
    _print_listing(sorted((r, by_rel[r]) for r in tracked if r in by_rel), list_all)

    # ---- 2. 未跟踪但可见 ----
    visible = sorted((r, by_rel[r]) for r in visible_untracked if r in by_rel)
    if visible:
        print("\n" + "=" * 78)
        print(f"② 未跟踪但可见（{len(visible)} 份）—— `git add -A` 会把它们带进仓库，")
        print("   要么纳入治理、要么删掉、要么加进 .gitignore")
        _print_listing(visible, list_all)

    # ---- 3. 被忽略：按顶层目录聚合（反模式 3） ----
    print("\n" + "=" * 78)
    if ignored:
        print(f"③ 被 gitignore 的文档 {len(ignored)} 份 —— 守卫测试**不要**扫它们")
        print("   干净 clone 上这些文件不存在，断言会静默通过，结论因机器而异。")
        counts = Counter(_top_dir(rel) for rel in ignored)
        for top, n in counts.most_common(MAX_DIRS_LISTED):
            print(f"     {top}/  {n} 份")
        if len(counts) > MAX_DIRS_LISTED:
            print(f"     …… 另有 {len(counts) - MAX_DIRS_LISTED} 个顶层目录")
    else:
        print("③ 没有被 gitignore 的 markdown —— 守卫可以扫全部文档目录")

    # ---- 4. 混合目录 ----
    ignored_dirs = {str(Path(rel).parent) for rel in ignored}
    mixed = []
    for directory in sorted(ignored_dirs):
        here_tracked = sorted(
            r for r in tracked if r in by_rel and str(Path(r).parent) == directory
        )
        if here_tracked:
            mixed.append((directory, here_tracked))
    if mixed:
        print("\n" + "=" * 78)
        print("④ ⚠ 混合目录 —— 目录里既有被忽略的私有文档，又有已跟踪并推送的文件：")
        print("   目录名不告诉你哪个是哪个。往已跟踪的那几份写敏感内容会直接进公开仓库。")
        for directory, files in mixed:
            print(f"     {directory}/")
            for rel in files:
                print(f"       已跟踪 → {Path(rel).name}")

    print("\n下一步：对①按三判据分类（见 WRITING.md），再按 GUARDS.md 生成守卫测试。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
