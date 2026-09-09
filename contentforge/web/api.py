"""ContentForge Web Demo 后端（FastAPI）。

直接 import 现有 contentforge 模块复用生成/检查/导出能力。
启动：uvicorn web.api:app --reload --port 8000
"""
import io
import json
import re
import sys
import uuid
import zipfile
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# 把 src/ 加入 sys.path 让 web 能直接 import contentforge
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from contentforge.config import load_workspace, llm_config
from contentforge.pipelines.base import generate_one, load_meta, load_item
from contentforge.pipelines import find_topic
from contentforge.registry import load_facts, load_json
from contentforge.checks import run_checks, consistency
from contentforge.export.exporter import export_all

DEFAULT_WS = "pcb"   # 演示默认 workspace

app = FastAPI(title="ContentForge Web Demo", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

# 内存中的批量任务记录（演示用，重启即失）
_batch_jobs: dict = {}


# ============ Pydantic Models ============

class GenerateReq(BaseModel):
    topic_id: str
    formats: list[str] = []
    use_llm: bool = True


class CustomReq(BaseModel):
    question: str
    formats: list[str] = ["faq_page", "article"]
    use_llm: bool = True


class BatchReq(BaseModel):
    topic_ids: list[str]
    use_llm: bool = True


class InjectReq(BaseModel):
    topic_id: str
    inject: str = "1000 亿美元"
    format: str = "faq_page"
    use_llm: bool = True


# ============ Helpers ============

def _ws():
    return load_workspace(DEFAULT_WS)


def _build_topic_dict(question: str) -> dict:
    """临时构造一个 topic dict 不入 topics.json，供 /api/custom 用。"""
    return {
        "id": "T-CUSTOM",
        "title": question,
        "pillar": "faq",
        "kb_refs": ["04_", "02_", "03_"],   # 多目录兜底找事实
        "faq_ref": None,
        "audience": "客户现场提问",
        "platforms": ["site"],
        "angle": question,
        "status": "ready",
    }


def _facts_for_item(item_meta: dict) -> list:
    """拉一份物料引用的事实原断言。"""
    facts = load_facts(_ws())
    ids = set(item_meta.get("facts") or [])
    return [{"id": f["id"], "claim": f["claim"], "kb_ref": f["kb_ref"],
             "source": f.get("source"), "year": f.get("year")}
            for f in facts if f["id"] in ids and not f.get("superseded_at")]


def _format_item_response(item_path) -> dict:
    """统一物料响应结构：含 front-matter + 正文 + 检查报告 + 引用事实。"""
    item = load_item(item_path)
    meta = item["meta"]
    report = run_checks(_ws(), item_path, save_report=False)
    return {
        "id": meta["id"],
        "format": meta["format"],
        "topic": meta.get("topic"),
        "title": meta.get("title"),
        "status": meta["status"],
        "body": item["body"],
        "facts_used": _facts_for_item(meta),
        "gaps": meta.get("gaps") or [],
        "report": report,
    }


# ============ API 端点 ============

@app.get("/api/workspace")
def get_workspace():
    """返回 workspace 信息 + 选题列表。"""
    ws = _ws()
    cfg = llm_config()
    wsdir = Path(ws["dir"])
    topics = [t for t in load_json(wsdir, "topics.json", {}).get("topics", [])
              if not t.get("superseded_at")]
    items = sorted((wsdir / "content").glob("C-*.md")) if (wsdir / "content").exists() else []
    return {
        "name": ws["name"],
        "kb_path": ws["kb_path"],
        "has_llm_key": cfg["has_key"],
        "model": cfg.get("model"),
        "stats": {
            "topics": len(topics),
            "facts": len(load_facts(ws)),
            "items": len(items),
        },
        "topics": [{"id": t["id"], "title": t["title"], "pillar": t.get("pillar"),
                    "kb_refs": t.get("kb_refs"), "first_seen": t.get("first_seen")}
                   for t in topics],
    }


@app.post("/api/generate")
def post_generate(req: GenerateReq):
    """同步生成一份或多份物料。"""
    ws = _ws()
    cfg = llm_config()
    use_llm = req.use_llm and cfg["has_key"]
    topic = find_topic(ws, req.topic_id)
    formats = req.formats or _default_formats(topic)
    meta_ctx = load_meta(ws)
    out = []
    for fmt in formats:
        path = generate_one(ws, topic, fmt, meta_ctx, use_llm, cfg)
        out.append(_format_item_response(path))
    return {"items": out, "used_llm": use_llm}


@app.post("/api/generate/stream")
def post_generate_stream(req: GenerateReq):
    """SSE 流式生成多份物料。每份物料先逐 token 发 'token'，再发 'item' 完整结构。最后 'done'。"""
    ws = _ws()
    cfg = llm_config()
    use_llm = req.use_llm and cfg["has_key"]
    topic = find_topic(ws, req.topic_id)
    formats = req.formats or _default_formats(topic)
    meta_ctx = load_meta(ws)

    def _sse():
        for fmt in formats:
            yield f"event: format\ndata: {json.dumps({'format': fmt}, ensure_ascii=False)}\n\n"
            if use_llm:
                gen = generate_one(ws, topic, fmt, meta_ctx, use_llm, cfg, stream=True)
                path = None
                for chunk in gen:
                    if isinstance(chunk, str):
                        # token
                        yield f"event: token\ndata: {json.dumps({'token': chunk, 'format': fmt}, ensure_ascii=False)}\n\n"
                    elif hasattr(chunk, "exists"):   # Path 对象
                        path = chunk
                if path is None:
                    yield f"event: error\ndata: {json.dumps({'msg': '生成失败', 'format': fmt}, ensure_ascii=False)}\n\n"
                    continue
            else:
                path = generate_one(ws, topic, fmt, meta_ctx, use_llm, cfg)
            item = _format_item_response(path)
            yield f"event: item\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(_sse(), media_type="text/event-stream")


@app.post("/api/custom")
def post_custom(req: CustomReq):
    """客户自带问题，临时构造 topic dict 生成。"""
    ws = _ws()
    cfg = llm_config()
    use_llm = req.use_llm and cfg["has_key"]
    topic = _build_topic_dict(req.question)
    formats = req.formats or ["faq_page", "article"]
    meta_ctx = load_meta(ws)
    out = []
    for fmt in formats:
        path = generate_one(ws, topic, fmt, meta_ctx, use_llm, cfg)
        out.append(_format_item_response(path))
    return {"items": out, "used_llm": use_llm, "question": req.question}


@app.post("/api/batch")
def post_batch(req: BatchReq):
    """批量生成多选题 → 串行调 generate_one + run_checks，最后 export_all。"""
    ws = _ws()
    cfg = llm_config()
    use_llm = req.use_llm and cfg["has_key"]
    meta_ctx = load_meta(ws)
    job_id = f"batch-{uuid.uuid4().hex[:8]}"
    items = []
    for tid in req.topic_ids:
        try:
            topic = find_topic(ws, tid)
        except SystemExit:
            continue
        for fmt in _default_formats(topic):
            path = generate_one(ws, topic, fmt, meta_ctx, use_llm, cfg)
            items.append({
                "id": load_item(path)["meta"]["id"],
                "format": fmt,
                "topic": tid,
                "title": topic["title"],
                "status": load_item(path)["meta"]["status"],
            })
    # 导出 zip（force=True，演示允许未 approved 也导出）
    manifest = export_all(ws, force=True)
    _batch_jobs[job_id] = {"items": items, "manifest": manifest, "topic_count": len(req.topic_ids)}
    return {"job_id": job_id, "items": items, "total": len(items)}


@app.get("/api/batch/download")
def get_batch_download(job_id: str):
    """打包 wsdir/export/ 下文件 + manifest.json 成 zip 下载。"""
    if job_id not in _batch_jobs:
        raise HTTPException(404, "job 不存在")
    wsdir = Path(_ws()["dir"])
    export_dir = wsdir / "export"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if export_dir.exists():
            for p in export_dir.rglob("*"):
                if p.is_file():
                    zf.write(p, arcname=str(p.relative_to(export_dir)))
        else:
            zf.writestr("README.txt", "暂无导出文件")
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip",
                            headers={"Content-Disposition": f"attachment; filename={job_id}.zip"})


@app.post("/api/inject")
def post_inject(req: InjectReq):
    """防编造演示：故意注入伪造数字，看 FactChecker 拦截。"""
    ws = _ws()
    cfg = llm_config()
    use_llm = req.use_llm and cfg["has_key"]
    topic = find_topic(ws, req.topic_id)
    meta_ctx = load_meta(ws)
    path = generate_one(ws, topic, req.format, meta_ctx, use_llm, cfg,
                       inject_fabrication=req.inject)
    item = _format_item_response(path)
    # 标注演示要点
    item["inject"] = req.inject
    item["highlight_gaps"] = re.findall(r"\[数据缺口[：:][^\]]*\]", item["body"])
    return item


@app.get("/api/kb/verify")
def get_kb_verify(item_id: str):
    """返回该物料引用的事实原文，供 Demo2 对照核验。"""
    ws = _ws()
    wsdir = Path(ws["dir"])
    path = wsdir / "content" / f"{item_id}.md"
    if not path.exists():
        raise HTTPException(404, f"物料 {item_id} 不存在")
    meta = load_item(path)["meta"]
    return {"item_id": item_id, "facts": _facts_for_item(meta)}


@app.get("/api/items")
def list_items():
    """列出所有已生成物料。"""
    wsdir = Path(_ws()["dir"])
    content = wsdir / "content"
    if not content.exists():
        return {"items": []}
    items = []
    for p in sorted(content.glob("C-*.md")):
        m = load_item(p)["meta"]
        items.append({
            "id": m["id"], "format": m["format"], "topic": m.get("topic"),
            "title": m.get("title"), "status": m["status"],
            "checks": m.get("checks", {}),
        })
    return {"items": items}


@app.get("/api/consistency")
def get_consistency():
    """跨物料一致性矩阵。"""
    ws = _ws()
    wsdir = Path(ws["dir"])
    items = [load_item(p) for p in sorted((wsdir / "content").glob("C-*.md"))]
    if not items:
        return {"pass": True, "shared_facts": {}}
    r = consistency.check_all(ws, items)
    return r


def _default_formats(topic: dict) -> list:
    if topic["pillar"] == "faq":
        return ["faq_page", "article", "video"]
    if topic["pillar"] == "insight":
        return ["data_article", "article", "video"]
    return ["article", "video"]


@app.get("/")
def root():
    return {"name": "ContentForge Web Demo", "default_workspace": DEFAULT_WS,
            "endpoints": ["/api/workspace", "/api/generate", "/api/generate/stream",
                          "/api/custom", "/api/batch", "/api/batch/download",
                          "/api/inject", "/api/kb/verify", "/api/items", "/api/consistency"]}
