<#
.SYNOPSIS
    创建 Windows Explorer 右键上下文菜单，使用 Docker 运行 Mini-Agent。

.DESCRIPTION
    此脚本用于：
    - 直接传递 API 密钥给 Docker 容器
    - 创建右键上下文菜单项，使用 Docker 运行 Mini-Agent
    - 支持在文件夹上右键和文件夹背景上右键两种方式

.PARAMETER Remove
    移除上下文菜单项

.PARAMETER ApiKey
    直接指定 MiniMax API 密钥（未提供时将提示输入）

.PARAMETER SerperKey
    直接指定 Serper API 密钥（可选，未提供时将提示输入，可跳过）

.PARAMETER FirefoxProfile
    直接指定 Firefox profile 路径（可选，未提供时将提示输入，可跳过）
    用于在浏览器中保持登录状态

.EXAMPLE
    .\setup-explorer-context.ps1 -ApiKey "sk-xxx" -FirefoxProfile "C:\Users\xxx\AppData\Roaming\Mozilla\Firefox\Profiles\xxx.default"
    # 使用提供的 API 密钥和 Firefox profile 创建上下文菜单

.EXAMPLE
    .\setup-explorer-context.ps1 -Remove
    # 移除上下文菜单项

.NOTES
    需要安装并运行 Docker Desktop。
    如遇问题，请以管理员身份运行 PowerShell。
#>

param(
    [switch]$Remove,
    [string]$ApiKey = "",
    [string]$SerperKey = "",
    [string]$FirefoxProfile = ""
)

$ErrorActionPreference = "Stop"

# 注册表路径
$FolderShellPath = "Registry::HKEY_CURRENT_USER\Software\Classes\Directory\shell\MiniAgentDocker"
$FolderBgShellPath = "Registry::HKEY_CURRENT_USER\Software\Classes\Directory\Background\shell\MiniAgentDocker"

$MenuName = "使用 Mini-Agent 打开"

# 输出颜色
function Write-Success { param($msg) Write-Host $msg -ForegroundColor Green }
function Write-Info { param($msg) Write-Host $msg -ForegroundColor Cyan }
function Write-Warning { param($msg) Write-Host $msg -ForegroundColor Yellow }
function Write-Error { param($msg) Write-Host $msg -ForegroundColor Red }

# 辅助函数
function Test-DockerImageExists {
    param([string]$ImageName)

    try {
        $images = docker images -q $ImageName 2>&1
        return ($images -and $images.Length -gt 0)
    } catch {
        return $false
    }
}

# 获取或提示配置值（通用函数）
# 支持：API密钥、文件路径等
function Get-OrPromptValue {
    param(
        [string]$ValueName,           # 显示名称（如 "API Key"、"Firefox Profile"）
        [string]$PromptValue,         # 命令行参数提供的值
        [bool]$Required = $false       # 是否必需
    )

    # 检查参数是否提供
    if ($PromptValue -and $PromptValue.Length -gt 0) {
        Write-Info "正在使用参数提供的 $ValueName"
        return $PromptValue
    }

    # 提示用户输入
    if ($Required) {
        Write-Warning "$ValueName 是必需的，否则上下文菜单将无法正常工作"
        $input_ = Read-Host "请输入 $ValueName"

        while (-not $input_ -or $input_.Length -eq 0) {
            Write-Error "输入不能为空，请重新输入"
            $input_ = Read-Host "请输入 $ValueName"
        }

        return $input_
    } else {
        # 可选值
        Write-Info "$ValueName 是可选的，按回车键跳过"
        $input_ = Read-Host "请输入 $ValueName（直接回车跳过）"

        # 用户选择跳过
        if (-not $input_ -or $input_.Length -eq 0) {
            Write-Info "已跳过 $ValueName 设置"
            return $null
        }

        return $input_
    }
}

function New-ContextMenuEntry {
    param(
        [string]$Path,
        [string]$Command
    )

    # 创建主键
    if (-not (Test-Path $Path)) {
        New-Item -Path $Path -Force | Out-Null
    }

    # 设置显示名称和图标
    Set-ItemProperty -Path $Path -Name "(default)" -Value $MenuName
    Set-ItemProperty -Path $Path -Name "Icon" -Value "imageres.dll,83"

    # 创建命令子键
    $commandPath = "$Path\command"
    if (-not (Test-Path $commandPath)) {
        New-Item -Path $commandPath -Force | Out-Null
    }
    Set-ItemProperty -Path $commandPath -Name "(default)" -Value $Command

    Write-Success "已创建上下文菜单：$Path"
}

function Remove-ContextMenuEntry {
    param([string]$Path)

    if (Test-Path $Path) {
        Remove-Item -Path $Path -Recurse -Force
        Write-Success "已移除上下文菜单：$Path"
    }
}

# 显示菜单
function Show-Menu {
    Clear-Host
    Write-Host ""
    Write-Host "======================================" -ForegroundColor Cyan
    Write-Host "   Mini-Agent Explorer 上下文菜单设置" -ForegroundColor Cyan
    Write-Host "======================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "请选择操作:" -ForegroundColor White
    Write-Host ""
    Write-Host "  [1] 安装 - 添加右键菜单" -ForegroundColor Green
    Write-Host "  [2] 移除 - 删除右键菜单" -ForegroundColor Yellow
    Write-Host "  [3] 退出" -ForegroundColor Gray
    Write-Host ""
    Write-Host "======================================" -ForegroundColor Cyan
    Write-Host ""
}

# 获取用户选择
function Get-MenuChoice {
    Show-Menu
    $choice = Read-Host "请输入选项 [1-3]"
    return $choice
}

# 处理安装
function Invoke-Installation {
    Write-Info "正在检查 mini-agent 镜像..."
    if (-not (Test-DockerImageExists -ImageName "mini-agent")) {
        Write-Warning "未找到 mini-agent 镜像"
        Read-Host "`n按回车键退出"
        exit 1
    } else {
        Write-Success "mini-agent 镜像已存在"
    }

    # 获取 API 密钥
    Write-Info "`n=== API 密钥设置 ==="
    Write-Info "密钥将直接传递给 Docker 容器"

    $miniMaxKey = Get-OrPromptValue -ValueName "MiniMax API 密钥" -PromptValue $ApiKey -Required $true
    $serperKey = Get-OrPromptValue -ValueName "Serper API 密钥（可选）" -PromptValue $SerperKey -Required $false
    $firefoxProfile = Get-OrPromptValue -ValueName "Firefox Profile" -PromptValue $FirefoxProfile -Required $false

    # 创建上下文菜单项
    Write-Info "`n=== 创建上下文菜单项 ==="

    # 构建环境变量参数（仅在有值时添加）
    $envVars = "-e MINIMAX_API_KEY=${miniMaxKey}"
    if ($serperKey) {
        $envVars = $envVars + " -e SERPER_API_KEY=${serperKey}"
    }

    # 构建卷参数
    $folderShellVolums = "-v '%1:/project'"
    $folderBgShellVolums = "-v '%V:/project'"
    if ($firefoxProfile) {
        $folderShellVolums = $folderShellVolums + " -v '${firefoxProfile}:/firefox_profile'"
        $folderBgShellVolums = $folderBgShellVolums + " -v '${firefoxProfile}:/firefox_profile'"
    }

    # 在文件夹上右键
    New-ContextMenuEntry -Path $FolderShellPath -Command "powershell.exe -Command `"docker run -it --rm $folderShellVolums $envVars mini-agent`""

    # 在文件夹背景上右键
    New-ContextMenuEntry -Path $FolderBgShellPath -Command "powershell.exe -Command `"docker run -it --rm $folderBgShellVolums $envVars mini-agent`""

    Write-Success "`n=== 设置完成 ==="
    Write-Info "上下文菜单 '$MenuName' 已添加！"
    Write-Info ""
    Write-Info "使用方法："
    Write-Info "  1. 右键点击任意文件夹 -> '使用 Mini-Agent 打开'"
    Write-Info "  2. 右键点击文件夹内部空白处 -> '使用 Mini-Agent 打开'"
    Write-Info ""
    Write-Info "移除方法：运行脚本并选择 [2] 移除"

    Read-Host "`n按回车键退出"
    exit 0
}

# 处理移除
function Invoke-Removal {
    Write-Info "正在移除上下文菜单项..."

    Remove-ContextMenuEntry -Path $FolderShellPath
    Remove-ContextMenuEntry -Path $FolderBgShellPath

    Write-Success "`n上下文菜单已成功移除！"
    Write-Info "请重启资源管理器或重新登录以使更改生效。"

    Read-Host "`n按回车键退出"
    exit 0
}

# 主逻辑 - 如果传入了 -Remove 参数则直接执行移除，否则显示菜单
if ($Remove) {
    Invoke-Removal
} else {
    # 显示菜单并获取用户选择
    while ($true) {
        $choice = Get-MenuChoice

        switch ($choice) {
            "1" {
                Invoke-Installation
                break
            }
            "2" {
                Invoke-Removal
                break
            }
            "3" {
                Write-Info "已退出"
                exit 0
            }
            default {
                Write-Error "无效选项，请重新选择"
                Start-Sleep -Seconds 2
            }
        }
    }
}
