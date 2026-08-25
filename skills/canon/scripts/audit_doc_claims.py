"""模式 B 的「可核对声明漂移」检查：文档里的路径 / 相对链接 / 提交哈希是否还对得上。

用法：
    python audit_doc_claims.py [仓库根目录]

只报告**对不上的**。判据故意收紧——噪声大的审计比没有审计更糟，会训练人忽略它：

- 反引号里的路径先按仓库根、再按文档自身位置解析；都不中时，
  **再看它的文件名是否存在于仓库任何位置**——文档里常写裸文件名（"在 `schema.py` 里"），
  那是正常行文，不是失效引用。只有仓库里**根本不存在这个名字**才算真发现。
- 仓库外的约定路径（私有区之类）和被 gitignore 的工作目录无法核对，跳过并单独计数。
- 哈希只报告"git 里找不到"，不断言它是错的——它可能是缓存键或运行 id。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PATH_LIKE = re.compile(r"`([A-Za-z0-9_./\\-]+\.(?:py|json|md|mat|csv|yaml|yml|toml|txt))`")
DIR_LIKE = re.compile(r"`([A-Za-z0-9_./\\-]+/)`")
HASH_LIKE = re.compile(r"`([0-9a-f]{7,40})`")
MD_LINK = re.compile(r"\[[^\]]+\]\(([^)#]+?)(?:#[^)]*)?\)")


def git_out(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    return proc.stdout if proc.returncode == 0 else ""


_IGNORED_HEAD: dict[str, bool] = {}


def under_ignored_dir(repo: Path, candidate: str) -> bool:
    """路径本身或它的任一祖先是否被 gitignore。

    被忽略的目录装的是**运行时产物**（缓存、收件箱、导出）：它在跑过的机器上存在、
    在干净 clone 上不存在。文档写「产物落在 `local_runs/solve_cache/`」是在描述约定，
    不是在声称那个目录此刻存在——按存在性去判它，只会在没跑过的机器上刷一屏假阳性。

    **要逐级往上查，不能只看顶层。** 忽略规则常常是嵌套的：`archive/` 本身跟踪，
    而 `archive/summary/supporting_reports/` 被忽略。只查顶层会把后者漏成失效引用。
    """
    parts = Path(candidate).parts
    for depth in range(len(parts), 0, -1):
        prefix = "/".join(parts[:depth])
        if prefix not in _IGNORED_HEAD:
            proc = subprocess.run(
                ["git", "check-ignore", "-q", prefix], cwd=repo, capture_output=True,
            )
            _IGNORED_HEAD[prefix] = proc.returncode == 0
        if _IGNORED_HEAD[prefix]:
            return True
    return False


def main() -> int:
    repo = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    all_tracked = [p for p in git_out(repo, "ls-files", "-z").split("\0") if p]
    if not all_tracked:
        # 全新/空仓库是**预期状态**，不是错误——返回 0，免得在链式命令或 CI 里看着像失败。
        print(f"{repo} 不是 git 仓库，或没有被跟踪的文件。")
        print("→ 没有可核对的声明。全新项目请走模式 A′ 起步。")
        return 0

    # 归档目录默认**不读**（SKILL.md「删除也要有触发条件」）：它存在只是为了不丢，
    # 不是为了被参考。既然不读，它内部的失效引用就不该占审计视野——那只会训练人
    # 忽略这份报告。真要用归档里的东西，先把它移回 active 再说。
    def in_archive(rel: str) -> bool:
        return "archive" in Path(rel).parts[:-1]

    md_tracked = [p for p in all_tracked if p.endswith(".md") and (repo / p).exists()]
    archived = [p for p in md_tracked if in_archive(p)]
    docs = [repo / p for p in md_tracked if not in_archive(p)]
    tracked_names = {Path(p).name for p in all_tracked}
    tracked_segments = {seg for p in all_tracked for seg in Path(p).parts[:-1]}
    # 顶层目录（源码包 / App / tests 之类）。文档常写包内相对路径：
    # 「`ingestion/` 不能成为活跃路径的数据来源」指的是 `experiment_advisor/ingestion/`。
    top_dirs = {Path(p).parts[0] for p in all_tracked if len(Path(p).parts) > 1}

    def resolves_under_a_package(candidate: str) -> bool:
        """文档里的包内相对路径能否在某个顶层目录下解析到。

        判据故意松：宁可漏报一条真断链，也不要因为「文档写简写」刷一屏假阳性——
        噪声大的审计会训练人忽略它，那比没有审计更糟。
        """
        return any((repo / top / candidate).exists() for top in top_dirs)

    stale_paths: list[tuple[str, str]] = []
    dead_links: list[tuple[str, str]] = []
    unknown_hashes: list[tuple[str, str]] = []
    skipped = 0
    by_package = 0
    counts = {"path": 0, "link": 0, "hash": 0}

    for doc in docs:
        rel_doc = doc.relative_to(repo).as_posix()
        text = doc.read_text(encoding="utf-8", errors="replace")

        for token in sorted(set(PATH_LIKE.findall(text))):
            if "..." in token:
                continue          # 行文里的省略号路径（`.../validated/`），不是真引用
            counts["path"] += 1
            candidate = token.replace("\\", "/")
            if (repo / candidate).exists() or (doc.parent / candidate).exists():
                continue
            if Path(candidate).name in tracked_names:
                continue          # 裸文件名的行文引用，正常
            if under_ignored_dir(repo, candidate):
                skipped += 1      # 运行时产物，存在与否因机器而异
                continue
            if resolves_under_a_package(candidate):
                by_package += 1   # 包内相对简写，能在某个顶层目录下解析到
                continue
            stale_paths.append((rel_doc, token))

        for token in sorted(set(DIR_LIKE.findall(text))):
            if "..." in token:
                continue          # 行文里的省略号路径（`.../validated/`），不是真引用
            counts["path"] += 1
            candidate = token.replace("\\", "/").rstrip("/")
            if (repo / candidate).exists() or (doc.parent / candidate).exists():
                continue
            if under_ignored_dir(repo, candidate):
                skipped += 1      # 运行时产物目录，跑过才有
                continue
            head = Path(candidate).parts[0] if Path(candidate).parts else ""
            if resolves_under_a_package(candidate):
                by_package += 1   # 包内相对简写
                continue
            if head not in tracked_segments and not (repo / head).exists():
                skipped += 1      # 仓库外的约定路径，无法核对
                continue
            stale_paths.append((rel_doc, token))

        for target in sorted(set(MD_LINK.findall(text))):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            counts["link"] += 1
            if not (doc.parent / target).exists():
                dead_links.append((rel_doc, target))

        for sha in sorted(set(HASH_LIKE.findall(text))):
            counts["hash"] += 1
            proc = subprocess.run(
                ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                cwd=repo, capture_output=True, text=True,
            )
            if proc.returncode != 0:
                unknown_hashes.append((rel_doc, sha))

    archived_note = f"；另有 {len(archived)} 份在归档目录，按「归档默认不读」未扫" if archived else ""
    print(f"扫了 {len(docs)} 份已跟踪文档：路径 {counts['path']} 处 / "
          f"相对链接 {counts['link']} 处 / 哈希 {counts['hash']} 处"
          f"（{skipped} 处无法核对、{by_package} 处按包内相对路径解析，已跳过）{archived_note}\n")

    def dump(title: str, rows: list[tuple[str, str]], note: str = "") -> None:
        print(f"=== {title}（{len(rows)}）===")
        if not rows:
            print("    ✓ 全部对得上")
        else:
            if note:
                print(f"    {note}")
            for doc, item in sorted(rows):
                print(f"    {doc:50} → {item}")
        print()

    dump("失效的路径引用", stale_paths, "仓库里根本不存在这个文件名")
    dump("死链（相对链接指向不存在的文件）", dead_links)
    dump("git 里找不到的哈希", unknown_hashes,
         "可能是缓存键 / 运行 id 而非提交哈希，需人工判断")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
