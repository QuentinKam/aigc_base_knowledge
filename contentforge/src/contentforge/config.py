"""Workspace 与 LLM 配置。

一个行业/公司 = 一个 workspace，目录结构：
    workspaces/<name>/
        workspace.json   # {name, kb_path, created_at}
        brand.md
        registry/facts.json
        topics.json
        kbmeta/{templates,rules,files}.json
        content/C-*.md
        runs/
        export/
"""
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]   # contentforge/（仓库根）
WORKSPACES_DIR = REPO_ROOT / "workspaces"

LLM_ENV_KEYS = {
    "api_key": ("CF_API_KEY", "OPENAI_API_KEY", "ZHIPUAI_API_KEY"),
    "base_url": ("CF_BASE_URL", "OPENAI_BASE_URL"),
    "model": ("CF_MODEL", "OPENAI_MODEL"),
}

DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"  # 智谱 OpenAI 兼容端点，可换任意 OpenAI 兼容服务
DEFAULT_MODEL = "glm-4-flash"


def _load_dotenv() -> None:
    """加载仓库根 .env（KEY=VALUE，支持 # 注释 / 引号 / export 前缀），不覆盖已有环境变量。"""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    preexisting = set(os.environ)          # 真实环境变量优先，.env 内部后者覆盖前者
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in preexisting:
            os.environ[key] = val


def workspace_dir(name: str) -> Path:
    d = WORKSPACES_DIR / name
    if not (d / "workspace.json").exists():
        raise SystemExit(f"workspace 不存在：{d}（先执行 init）")
    return d


def load_workspace(name: str) -> dict:
    d = workspace_dir(name)
    cfg = json.loads((d / "workspace.json").read_text(encoding="utf-8"))
    cfg["dir"] = str(d)
    return cfg


def llm_config() -> dict:
    """优先级：环境变量 > 仓库根 .env > llm.json > 默认（智谱）。"""
    _load_dotenv()
    cfg = {}
    llm_json = REPO_ROOT / "llm.json"
    if llm_json.exists():
        cfg.update(json.loads(llm_json.read_text(encoding="utf-8")))
    for key, envs in LLM_ENV_KEYS.items():
        for e in envs:
            if os.environ.get(e):
                cfg[key] = os.environ[e]
                break
    cfg.setdefault("base_url", DEFAULT_BASE_URL)
    cfg.setdefault("model", DEFAULT_MODEL)
    cfg["has_key"] = bool(cfg.get("api_key"))
    return cfg
