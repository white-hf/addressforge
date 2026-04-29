#!/bin/bash
# AddressForge Console 启动脚本
# 确保在 addressforge 根目录运行

# 1. 设置工作目录
cd "$(dirname "$0")"

# 2. 确保虚拟环境激活
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "../.venv" ]; then
    source ../.venv/bin/activate
fi

# 3. 配置 Python 环境
export PYTHONPATH="$PWD/src:$PYTHONPATH"

# 4. 加载数据库配置 (如果存在 .env.local)
if [ -f "src/addressforge/core/.env.local" ]; then
    export $(grep -v '^#' src/addressforge/core/.env.local | xargs)
fi

# 5. 启动服务
echo "Starting AddressForge Console on http://127.0.0.1:8011 ..."
python src/addressforge/console/server.py
