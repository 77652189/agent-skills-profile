# agent-skills-profile 一键部署 / 同步（Windows）
#
# 做的事：
#   1. clone（第一次）或 pull（以后每次）本仓库
#   2. 把 AGENTS.md 合到 ~/.codex/AGENTS.md，保留 codebase-memory-mcp 标记块里
#      已经装在本机的内容（那部分是 codebase-memory-mcp 安装器自己写的，不能被
#      仓库里的占位内容覆盖回去）
#   3. 按 deploy-manifest.txt 同步 ~/.codex/skills 和 ~/.claude/skills 的目录联接：
#      清单里有、本地没链接的 -> 建；本地链接指向本仓库、但清单里已经没有的 -> 拆
#      （不碰指向别处的链接，不碰仓库里的源文件）
#   4. 按需装 codebase-memory-mcp 和 officecli 这两个外部工具（-SkipTools 跳过）
#
# 可以重复运行：每次都会先拉最新，再把本地状态同步成清单当前的样子。
#
# 用法：
#   .\scripts\install.ps1                  # 完整安装/同步（含外部工具）
#   .\scripts\install.ps1 -SkipTools        # 只同步 skill 链接，不装外部工具
#   .\scripts\install.ps1 -RepoPath D:\dev\agent-skills-profile   # clone/更新到自定义位置

param(
    [string]$RepoUrl = "https://github.com/77652189/agent-skills-profile.git",
    [string]$RepoPath = "$HOME\Documents\Codex\agent-skills-profile",
    [switch]$SkipTools
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

# --- 1. clone 或 pull ---------------------------------------------------

if (Test-Path "$RepoPath\.git") {
    Write-Step "拉取最新: $RepoPath"
    git -C $RepoPath pull --ff-only
} else {
    Write-Step "克隆到: $RepoPath"
    New-Item -ItemType Directory -Force -Path (Split-Path $RepoPath) | Out-Null
    git clone $RepoUrl $RepoPath
}

# --- 2. 合并 AGENTS.md，保留本机 codebase-memory-mcp 标记块 -------------

Write-Step "同步 AGENTS.md -> ~/.codex/AGENTS.md"

$repoAgents = Get-Content "$RepoPath\AGENTS.md" -Raw
$marker = "<!-- codebase-memory-mcp:start -->"
$liveAgentsPath = "$HOME\.codex\AGENTS.md"

$repoHead = ($repoAgents -split [regex]::Escape($marker))[0].TrimEnd() + "`n"

if (Test-Path $liveAgentsPath) {
    $liveAgents = Get-Content $liveAgentsPath -Raw
    if ($liveAgents -match [regex]::Escape($marker)) {
        # 本机已经有标记块（大概率是 codebase-memory-mcp 装过之后写的），保留它
        $liveTail = $liveAgents.Substring($liveAgents.IndexOf($marker))
        $merged = $repoHead + "`n" + $liveTail
    } else {
        # 本机没有标记块，用仓库里的占位内容做初始值
        $repoTail = $repoAgents.Substring($repoAgents.IndexOf($marker))
        $merged = $repoHead + "`n" + $repoTail
    }
} else {
    $repoTail = $repoAgents.Substring($repoAgents.IndexOf($marker))
    $merged = $repoHead + "`n" + $repoTail
}

New-Item -ItemType Directory -Force -Path "$HOME\.codex" | Out-Null
Set-Content -Path $liveAgentsPath -Value $merged -NoNewline -Encoding utf8

# --- 3. 按 deploy-manifest.txt 同步 skill 链接 ---------------------------

Write-Step "同步 skills（按 deploy-manifest.txt）"

$manifest = Get-Content "$RepoPath\deploy-manifest.txt" |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -and -not $_.StartsWith("#") }

$homeDirs = @("$HOME\.codex\skills", "$HOME\.claude\skills")
$repoSkillsRoot = (Resolve-Path "$RepoPath\skills").Path

foreach ($homeDir in $homeDirs) {
    New-Item -ItemType Directory -Force -Path $homeDir | Out-Null

    # 3a. 建缺的链接
    foreach ($name in $manifest) {
        $src = Join-Path "$RepoPath\skills" $name
        if (-not (Test-Path $src)) {
            $src = Join-Path "$RepoPath\skills\matt-pocock" $name
        }
        if (-not (Test-Path $src)) {
            Write-Warning "清单里的 '$name' 在仓库 skills/ 和 skills/matt-pocock/ 下都找不到，跳过"
            continue
        }
        $link = Join-Path $homeDir $name
        $existing = Get-Item $link -Force -ErrorAction SilentlyContinue
        $alreadyCorrect = $existing -and $existing.LinkType -and
            ($existing.Target -and (Resolve-Path $existing.Target[0]).Path -eq (Resolve-Path $src).Path)
        if ($alreadyCorrect) { continue }
        if (Test-Path $link) { cmd /c rmdir /s /q "$link" 2>$null; if (Test-Path $link) { Remove-Item -Recurse -Force $link } }
        cmd /c mklink /J "$link" "$src" | Out-Null
        Write-Host "  + $name"
    }

    # 3b. 拆清单里已经没有、但本地还链接着（指向本仓库）的
    Get-ChildItem $homeDir -Force | Where-Object {
        $_.LinkType -eq "Junction" -and $_.Name -notin $manifest
    } | ForEach-Object {
        $targetPath = $_.Target[0]
        $isOurs = $false
        try { $isOurs = (Resolve-Path $targetPath).Path.StartsWith($repoSkillsRoot) } catch {}
        if ($isOurs) {
            cmd /c rmdir /s /q "$($_.FullName)"
            Write-Host "  - $($_.Name)（清单里已移除）"
        }
    }
}

# --- 4. 外部工具 ---------------------------------------------------------

if (-not $SkipTools) {
    Write-Step "检查外部工具"

    if (Get-Command codebase-memory-mcp -ErrorAction SilentlyContinue) {
        Write-Host "  codebase-memory-mcp 已装，跳过"
    } else {
        Write-Host "  安装 codebase-memory-mcp..."
        $tmp = New-TemporaryFile
        Invoke-WebRequest -Uri https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.ps1 -OutFile $tmp
        Unblock-File $tmp
        & $tmp
    }

    if (Get-Command officecli -ErrorAction SilentlyContinue) {
        Write-Host "  officecli 已装，跳过"
    } else {
        Write-Host "  安装 officecli..."
        $tmp = New-TemporaryFile
        Invoke-WebRequest -Uri https://d.officecli.ai/install.ps1 -OutFile $tmp
        Unblock-File $tmp
        & $tmp
        # 安装脚本会往 ~/.claude/skills/officecli 扔一份独立文件；换成指向仓库的联接，
        # 保持跟其它 skill 一致的单一来源
        $officecliLink = "$HOME\.claude\skills\officecli"
        if ((Test-Path $officecliLink) -and -not (Get-Item $officecliLink -Force).LinkType) {
            Remove-Item -Recurse -Force $officecliLink
            cmd /c mklink /J "$officecliLink" "$RepoPath\skills\officecli" | Out-Null
        }
    }
} else {
    Write-Host "`n(已跳过外部工具检查，见 -SkipTools)"
}

Write-Step "完成"
Write-Host "重启 Codex / Claude Code 会话让改动生效。"
