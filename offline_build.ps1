Set-Location $PSScriptRoot

# 创建虚拟环境（如果不存在）
if (-not (Test-Path .venv)) {
    python -m venv .venv
}

# 直接使用虚拟环境中的 pip，避免激活脚本的作用域问题
.venv\Scripts\python.exe -m pip install --no-index --find-links=./offline_packages -e .