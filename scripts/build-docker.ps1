<#
.SYNOPSIS
    构建 Mini Agent Docker 镜像。

.DESCRIPTION
    此脚本用于构建 Mini Agent 的 Docker 镜像。

.PARAMETER RepoDirectory
    包含 Dockerfile 和项目文件的目录。默认为脚本所在目录的上层目录。

.EXAMPLE
    .\build-docker.ps1

.EXAMPLE
    .\build-docker.ps1 -RepoDirectory "C:\path\to\repo"

.NOTES
    需要安装并运行 Docker Desktop。
#>

param(
    [Parameter(Mandatory = $false)]
    [string]$RepoDirectory = ""
)

$ErrorActionPreference = "Stop"

# 输出颜色
function Write-Success { param($msg) Write-Host $msg -ForegroundColor Green }
function Write-Info { param($msg) Write-Host $msg -ForegroundColor Cyan }
function Write-Warning { param($msg) Write-Host $msg -ForegroundColor Yellow }
function Write-Error { param($msg) Write-Host $msg -ForegroundColor Red }

# 获取脚本所在目录，并向上查找包含 Dockerfile 的目录作为仓库根目录
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if ([string]::IsNullOrEmpty($RepoDirectory)) {
    # 从脚本所在目录向上查找，直到找到包含 Dockerfile 的目录
    $RepoPath = $ScriptDir
    while ($RepoPath -ne "") {
        $DockerfilePath = Join-Path $RepoPath "Dockerfile"
        if (Test-Path $DockerfilePath) {
            break
        }
        $RepoPath = Split-Path -Parent $RepoPath
    }
    
    if ([string]::IsNullOrEmpty($RepoPath)) {
        Write-Error "无法找到 Dockerfile，请手动指定 -RepoDirectory 参数"
        Read-Host "按回车键退出"
        exit 1
    }
} else {
    $RepoPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($RepoDirectory)
}

Clear-Host
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "      Mini-Agent Docker 镜像构建" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

Write-Info "正在从以下目录构建 Docker 镜像: $RepoPath"
Write-Host ""

docker build -t mini-agent $RepoPath

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Success "======================================"
    Write-Success "  Docker 镜像 'mini-agent' 构建成功！"
    Write-Success "======================================"
    Write-Host ""
    Read-Host "按回车键退出"
    exit 0
} else {
    Write-Host ""
    Write-Error "======================================"
    Write-Error "  Docker 构建失败，退出代码: $LASTEXITCODE"
    Write-Error "======================================"
    Write-Host ""
    Read-Host "按回车键退出"
    exit $LASTEXITCODE
}
