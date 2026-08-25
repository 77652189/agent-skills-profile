# 文档治理 — 怎么守

守卫测试的四种形态、五条反模式，以及测试能防什么、防不了什么。
文档里该写什么见 [WRITING.md](WRITING.md)。

## 守卫形态

生成的测试应覆盖这四种。全部放在项目自己的测试目录里(例:`tests/test_docs_boundary.py`)。

### ① 集合相等,而不是包含

```python
ACTIVE_DOCS = {"README.md", "EXECUTION_PLAN.md", "handoff.md", "architecture.md"}

def test_docs_root_contains_only_reviewed_active_docs():
    root_markdown = {p.name for p in (REPO_ROOT / "docs").glob("*.md") if p.is_file()}
    assert root_markdown == ACTIVE_DOCS
```

用 `==` 而不是 `⊇`。任何人往 `docs/` 加一个文件都会红,新增 active 文档必须是有意识的决定。

### ② 废弃文档不复活

```python
DELETED_OBSOLETE_DOCS = {"migration_plan.md", "old_architecture.md", ...}

def test_obsolete_docs_stay_deleted():
    ...
    assert doc_names.isdisjoint(DELETED_OBSOLETE_DOCS)
```

这是一条**被自动执行的负面知识**:没人需要记得"这几份是故意删的",测试记得。压缩、换会话、换人都带不走它。

### ③ 硬约束文本在场

```python
def test_hard_boundaries_are_present_in_handoff():
    text = (REPO_ROOT / "docs" / "handoff.md").read_text(encoding="utf-8")
    assert "<某数据的基准结果不得改动>" in text
    assert "<保密范围的原话>" in text
```

防的是最严重的一类失效:约束在某次改写/压缩里悄悄消失,然后被违反。

### ④ 文档里可核对的声明

文档里出现的**数字、路径、文件名、枚举值**都能对照仓库真实值,也都该测。

```python
def test_documented_scope_number_matches_reality():
    text = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    actual = len(load_curated_entries())
    assert f"{actual} 条" in text
```

这是**唯一能防内容漂移的那部分**。实战里出现过文档写"约 30 条"、实际 122 条的情况,靠这类测试才抓到。

---

## 反模式

四条都是踩出来的。踩中任何一条,守卫退化成装饰品或纯家务。

### 反模式 1 — 断言"当前值"而不是"不变量"

```python
# ✗ 家务：状态一推进就红，修法永远是改测试去迎合文档 → 检测力为零
assert "slice_status: in_progress" in text
assert "current_slice: refactor_auth_layer" in text

# ✓ 守卫：锁字段存在 + 取值合法。状态变了不红，字段丢了才红
assert re.search(r"^slice_status: (in_progress|done|blocked)$", text, re.M)
```

> **测试不变量 = 守卫;测试当前值 = 家务。**

一个你例行更新去迎合现实的测试,失败模式永远是"更新断言",从来不是"文档错了"。它只产生摩擦。

判断法:**这条断言未来会不会因为正常推进而变红?** 会 → 它是家务。

### 反模式 2 — 扫描目标不存在时静默通过

```python
# ✗ 目录不存在时 glob 返回空，断言 vacuously 通过
for root in (docs_root, archive_root, subpackage_docs):
    names |= {p.name for p in root.glob("*.md")}

# ✓ 先确认扫描目标在场
for root in scanned_roots:
    assert root.is_dir(), f"扫描目标不存在，测试会静默通过：{root}"
```

实战里出现过:一条测试扫三个目录,其中两个是空转(一个被 gitignore、一个压根没建过),测试绿了好几个月,测的却是空气。

**任何"遍历目录做断言"的测试都要配防空转断言。**

### 反模式 3 — 依赖未被跟踪的本地状态

被 `.gitignore` 排除的目录,在干净 clone 上不存在。扫它的测试**在你机器上和在 CI 上测的不是同一件事**,结论不可复现。

守卫只扫**版本控制内**的路径。想保护被忽略的私有目录,改为断言忽略规则本身在场:

```python
def test_private_archive_stays_out_of_version_control():
    ignored = {ln.strip() for ln in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert "docs/archive/" in ignored
```

这条守的是真正的风险:那行没了,下一次 `git add -A` 就会把私有文档提交进公开仓库。

### 反模式 4 — 跳过变异检验

没红过的测试,你不知道它在测什么——它可能因为断言写错、扫到空目录、或者根本没跑到那行而**永远绿**。

**永远绿的测试是有害的装饰品**,因为它给你虚假的安全感。

每条新守卫都要走一遍:

```python
original = TARGET.read_bytes()          # 按字节备份
try:
    TARGET.write_bytes(broken)          # 注入故障
    assert run_pytest() != 0            # 必须红
finally:
    TARGET.write_bytes(original)        # 按字节还原
    assert TARGET.read_bytes() == original
assert run_pytest() == 0                # 还原后必须绿
```

**必须用 `try/finally` 并按字节还原。** 尤其在变异 `.gitignore` 时:异常退出会把它留在破损状态,下一次 `git add -A` 就会泄露私有文件。用文本读写可能改掉行尾或加 BOM,只有字节读写能保证还原。

**一种变异不够。** 同一条守卫要试**几种不同的失效方式**——"整节删掉"和"标题改名"是两回事,只试前者会漏掉后者(下面反模式 5 就是这样当场抓出来的)。

### 反模式 5 — 用子串匹配断言"标题在场"

```python
# ✗ 子串匹配：`## 核心证据边界` 仍然是 `## 核心证据边界_DELETED` 的子串
#   → 整节删掉能抓到，"重组时顺手改名"抓不到，而后者才是常见失效方式
missing = [s for s in SECTIONS if s not in text]

# ✓ 按整行比对
headings = {line.strip() for line in text.splitlines()}
missing = [s for s in SECTIONS if s not in headings]
```

这条是变异检验当场逮到的:第一版守卫写成子串匹配,注入"改名"变异后**测试照样绿**。凡是断言"某个标题/字段在场"的守卫,都要按行(或按正则锚定行首尾)比对,不能用 `in`。

### 反模式 6 — 扫描器扫到自己

任何"扫源码找违规写法"的守卫,它自己的源码里必然含有那些写法(那是判断规则本身),扫自己必然命中自己。

```python
# ✓ 扫描器跳过本文件
self_name = Path(__file__).name
for path in sorted(TESTS_DIR.glob("test_*.py")):
    if path.name == self_name:
        continue
```

同类陷阱还有:用脚本分析 transcript / 日志时,**脚本自己的源码已经随工具调用进了那份 transcript**,子串匹配会把自己的代码当成数据。两次实跑都栽在这上面——写扫描器时先问一句:**它会不会把自己算进去?**

---

## 能防什么,不能防什么

| | 测试能防吗 |
|---|---|
| 结构漂移(多了/少了文档、废弃文档复活) | ✅ |
| 硬约束被删掉 | ✅ |
| 可核对声明漂移(数字、路径、枚举) | ✅ |
| 叙述失真(架构描述和代码不符) | ❌ 只能靠人读 |
| 文档有没有用 / 该不该存在 | ❌ 只能靠人判断 |
| 仓库外的活拷贝变旧(装到 home 的偏好 / 配置 / hook) | ❌ 干净 clone 上那份不存在,断言会空转 |

最后一行是个**原则**而不是个例:凡是一致性的另一端在仓库之外,守卫都够不着——因为守卫必须在
任何一台 clone 出来的机器上给出相同结论。这类只能进审计清单(见 SKILL.md「仓库外的活拷贝」)。

不要向用户声称"测试保证文档正确"。准确说法是:**测试保证结构和可核对事实不漂移;叙述部分的唯一防线是有人读它——所以没人读的文档该删。**
