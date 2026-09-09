"""ContentForge CLI（spec FR-9）：init / ingest / facts / topics / generate / check / approve / export / status"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import checks, registry
from .config import WORKSPACES_DIR, load_workspace, llm_config
from .pipelines.base import load_item, load_meta, update_item


def cmd_init(args):
    d = WORKSPACES_DIR / args.name
    if (d / "workspace.json").exists() and not args.force:
        raise SystemExit(f"workspace 已存在：{d}")
    (d / "registry").mkdir(parents=True, exist_ok=True)
    (d / "kbmeta").mkdir(parents=True, exist_ok=True)
    (d / "content").mkdir(parents=True, exist_ok=True)
    (d / "runs").mkdir(parents=True, exist_ok=True)
    (d / "export").mkdir(parents=True, exist_ok=True)
    (d / "workspace.json").write_text(json.dumps({
        "name": args.name, "kb_path": str(Path(args.kb).resolve()),
        "created_at": date.today().isoformat()}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✓ workspace 就绪：{d}")


def cmd_ingest(args):
    from .ingest import run_ingest
    run_ingest(load_workspace(args.workspace))


def cmd_facts(args):
    ws = load_workspace(args.workspace)
    facts = registry.load_facts(ws)
    for f in facts:
        if args.cat and f["cat"] != args.cat:
            continue
        if args.search and args.search not in f["claim"]:
            continue
        nums = ",".join(f"{n['n']}{n['u']}" for n in f["numbers"][:4])
        print(f"{f['id']} [{f['cat']}] {f['claim'][:70]}"
              + (f"  ⟪{nums}⟫" if nums else ""))


def cmd_topics(args):
    ws = load_workspace(args.workspace)
    topics = registry.load_json(Path(ws["dir"]), "topics.json", {}).get("topics", [])
    for t in topics:
        if args.pillar and t["pillar"] != args.pillar:
            continue
        print(f"{t['id']} [{t['pillar']}] {t['title'][:60]} → {','.join(t['kb_refs'])}")


def cmd_generate(args):
    from .pipelines import generate_one, find_topic, FORMATS
    ws = load_workspace(args.workspace)
    cfg = llm_config()
    use_llm = args.llm
    if use_llm and not cfg["has_key"]:
        raise SystemExit("未配置 API key：设置 CF_API_KEY / llm.json，或去掉 --llm 用 mock 模式")
    if not use_llm:
        print("（mock 模式：确定性骨架稿。配置 API key 后加 --llm 生成成稿）")
    topic = find_topic(ws, args.topic)
    formats = [f.strip() for f in args.formats.split(",")] if args.formats else _default_formats(topic)
    for f in formats:
        if f not in FORMATS:
            raise SystemExit(f"未知格式 {f}，可选：{','.join(FORMATS)}")
    meta_ctx = load_meta(ws)
    for fmt in formats:
        path = generate_one(ws, topic, fmt, meta_ctx, use_llm, cfg)
        report = checks.run_checks(ws, path)
        print(checks.print_report(report))
        print(f"  → 已保存 {path}\n")


def _default_formats(topic):
    if topic["pillar"] == "faq":
        return ["faq_page", "article", "video"]
    if topic["pillar"] == "insight":
        return ["data_article", "article", "video"]
    return ["article", "video"]


def cmd_check(args):
    from .checks import consistency
    ws = load_workspace(args.workspace)
    wsdir = Path(ws["dir"])
    if args.id:
        path = wsdir / "content" / f"{args.id}.md"
        if not path.exists():
            raise SystemExit(f"物料不存在：{path}")
        print(checks.print_report(checks.run_checks(ws, path)))
        return
    items = [load_item(p) for p in sorted((wsdir / "content").glob("C-*.md"))]
    if not items:
        print("（无物料）")
        return
    for it in items:
        report = checks.run_checks(ws, it["path"])
        print(checks.print_report(report) + "\n")
    creport = consistency.check_all(ws, items)
    print(consistency.render_matrix(creport))


def cmd_approve(args):
    ws = load_workspace(args.workspace)
    path = Path(ws["dir"]) / "content" / f"{args.id}.md"
    if not path.exists():
        raise SystemExit(f"物料不存在：{path}")
    meta = load_item(path)["meta"]
    if meta["checks"]["fact"] != "pass" or meta["checks"]["geo"] != "pass":
        raise SystemExit(f"检查未全通过（fact={meta['checks']['fact']}, geo={meta['checks']['geo']}），先处理 fail")
    update_item(path, status="approved")
    print(f"✓ {args.id} → approved（可导出）")


def cmd_export(args):
    from .export.exporter import export_all
    ws = load_workspace(args.workspace)
    ids = {args.id} if args.id else None
    manifest = export_all(ws, ids=ids, force=args.force)
    if not manifest["items"]:
        print("（无可导出物料：需 approved 状态，或加 --force）")
        return
    for it in manifest["items"]:
        print(f"✓ {it['id']} [{it['format']}] {it['status']}")
        for f in it["files"]:
            print(f"    {ws['dir']}/export/{f}")


def cmd_status(args):
    ws = load_workspace(args.workspace)
    wsdir = Path(ws["dir"])
    items = [load_item(p) for p in sorted((wsdir / "content").glob("C-*.md"))]
    print(f"workspace {ws['name']}｜知识库 {ws['kb_path']}")
    print(f"物料 {len(items)} 份：")
    for it in items:
        m = it["meta"]
        c = m.get("checks", {})
        print(f"  {m['id']} [{m['format']}] {m['status']}"
              f" fact={c.get('fact')} geo={c.get('geo')} model={m.get('model')}｜{m.get('title', '')[:36]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="contentforge", description="知识库 → 多平台内容物料生产线")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init");     p.add_argument("name"); p.add_argument("--kb", required=True)
    p.add_argument("--force", action="store_true");            p.set_defaults(fn=cmd_init)
    p = sub.add_parser("ingest");   p.add_argument("workspace"); p.set_defaults(fn=cmd_ingest)
    p = sub.add_parser("facts");    p.add_argument("workspace")
    p.add_argument("--cat"); p.add_argument("--search");       p.set_defaults(fn=cmd_facts)
    p = sub.add_parser("topics");   p.add_argument("workspace"); p.add_argument("--pillar")
    p.set_defaults(fn=cmd_topics)
    p = sub.add_parser("generate"); p.add_argument("workspace"); p.add_argument("--topic", required=True)
    p.add_argument("--formats"); p.add_argument("--llm", action="store_true")
    p.set_defaults(fn=cmd_generate)
    p = sub.add_parser("check");    p.add_argument("workspace"); p.add_argument("--id")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("approve");  p.add_argument("workspace"); p.add_argument("--id", required=True)
    p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("export");   p.add_argument("workspace"); p.add_argument("--id")
    p.add_argument("--force", action="store_true");            p.set_defaults(fn=cmd_export)
    p = sub.add_parser("status");   p.add_argument("workspace"); p.set_defaults(fn=cmd_status)

    args = ap.parse_args(argv)
    try:
        args.fn(args)
        return 0
    except SystemExit:
        raise
    except Exception as e:                                 # noqa: BLE001
        print(f"错误：{e}", file=sys.stderr)
        return 1
