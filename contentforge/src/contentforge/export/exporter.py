"""导出：按平台打包发布就绪物料（spec FR-7）。site 平台附 FAQPage JSON-LD。"""
import json
import re
from datetime import date
from pathlib import Path


def export_item(ws, item: dict, outdir: Path) -> list:
    meta, body = item["meta"], item["body"].strip()
    fmt = meta["format"]
    files = []

    def write(rel: str, content: str):
        p = outdir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        files.append(str(p.relative_to(outdir)))

    if fmt == "faq_page":
        write(f"site/{meta['id']}.md", body + "\n")
        write(f"site/{meta['id']}.jsonld", _faq_jsonld(body) + "\n")
    elif fmt == "article":
        write(f"zhihu/{meta['id']}.md", body + "\n")
        write(f"wechat/{meta['id']}.md", body + "\n")
    elif fmt == "video":
        for sec_name, fname in [("口播稿", "口播稿"), ("分镜表", "分镜表"),
                                ("发布文案", "发布文案"), ("钩子备选", "钩子备选")]:
            sec = _section(body, sec_name)
            if sec:
                write(f"douyin/{meta['id']}-kit/{fname}.md", sec + "\n")
        write(f"douyin/{meta['id']}-kit/完整物料包.md", body + "\n")
    elif fmt == "data_article":
        write(f"wechat/{meta['id']}.md", body + "\n")
        write(f"site/{meta['id']}.md", body + "\n")
    return files


def _section(body: str, name: str) -> str:
    m = re.search(rf"## .*?{name}.*?\n(.*?)(?=\n## |\Z)", body, re.S)
    return f"## {name}\n{m.group(1).strip()}" if m else ""


def _faq_jsonld(body: str) -> str:
    h1 = re.search(r"^#\s+(.+)$", body, re.M)
    direct = re.search(r"\*\*直接回答[^\n]*\*\*[：:]?\s*(.+)", body)
    q = h1.group(1).strip() if h1 else ""
    a = direct.group(1).strip() if direct else ""
    return json.dumps({
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [{
            "@type": "Question", "name": q,
            "acceptedAnswer": {"@type": "Answer", "text": a},
        }],
    }, ensure_ascii=False, indent=1)


def export_all(ws, ids=None, force=False) -> dict:
    from ..pipelines.base import load_item
    wsdir = Path(ws["dir"])
    outdir = wsdir / "export"
    manifest = {"exported_at": date.today().isoformat(), "items": []}
    paths = sorted((wsdir / "content").glob("C-*.md"))
    for p in paths:
        item = load_item(p)
        if ids and item["meta"]["id"] not in ids:
            continue
        status = item["meta"].get("status")
        if status not in ("approved", "published") and not force:
            continue
        files = export_item(ws, item, outdir)
        manifest["items"].append({"id": item["meta"]["id"], "format": item["meta"]["format"],
                                  "status": status, "files": files})
    (outdir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    return manifest
