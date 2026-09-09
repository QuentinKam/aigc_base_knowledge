#!/usr/bin/env bash
# ContentForge Web Demo 一键启动脚本
# 用法：bash web/serve.sh
#   默认 mock 模式（无需 LLM key）；若已 export CF_API_KEY 则启用真 LLM 流式
# 客户访问：http://localhost:5173
set -e

cd "$(dirname "$0")/.."

# ===== 1. 准备 Python venv（首次自动创建）=====
if [ ! -d ".venv" ]; then
  echo "📦 创建 Python venv…"
  python3 -m venv .venv
fi
source .venv/bin/activate

echo "🐍 安装后端依赖（清华源）…"
pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple fastapi uvicorn

# ===== 2. 准备前端 =====
cd web/frontend
if [ ! -d "node_modules" ]; then
  echo "⚡ 配置 pnpm 镜像（npmmirror）…"
  pnpm config set registry https://registry.npmmirror.com
  echo "📦 安装前端依赖…"
  pnpm install
  pnpm approve-builds esbuild || true
fi

cd ../..

# ===== 3. 启动两个进程 =====
echo ""
echo "🚀 启动服务…"
echo "  后端：http://localhost:8000  (FastAPI)"
echo "  前端：http://localhost:5173  (Vite, proxy /api → 8000)"
echo ""
if [ -z "$CF_API_KEY" ]; then
  echo "⚠️  当前未设置 CF_API_KEY，将走 mock 模式（骨架稿，无 LLM 流式）"
  echo "    如需真 LLM，请：export CF_API_KEY=你的key  # 智谱/DeepSeek/OpenAI 任一兼容"
else
  echo "✅ 检测到 CF_API_KEY，启用 LLM 模式"
fi
echo ""
echo "客户端：浏览器打开 http://localhost:5173"
echo "停止：Ctrl+C"

# cleanup
trap "echo ' shutting down…'; kill 0 2>/dev/null; exit" INT TERM

# 后台跑后端，前台跑前端（便于 Ctrl+C 退出）
(uvicorn web.api:app --port 8000 --reload > /tmp/cf_backend.log 2>&1) &
cd web/frontend
pnpm dev
