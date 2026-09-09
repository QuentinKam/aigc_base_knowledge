"""ContentForge CLI（spec FR-9）：init / ingest / facts / topics / generate / check / approve / export / status"""
import argparse
import json
import re
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
    from .pipelines import generate_one, FORMATS
    ws = load_workspace(args.workspace)
    cfg = llm_config()
    use_llm = args.llm
    if use_llm and not cfg["has_key"]:
        raise SystemExit("未配置 API key：设置 CF_API_KEY / llm.json，或去掉 --llm 用 mock 模式")
    if not use_llm:
        print("（mock 模式：确定性骨架稿。配置 API key 后加 --llm 生成成稿）")

    topics = _select_topics(ws, args)
    if not topics:
        raise SystemExit("未匹配到任何选题。可选过滤：--topics / --pillar / --since / --status / --file / --dir")
    print(f"已选 {len(topics)} 个选题：{', '.join(t['id'] for t in topics)}")

    formats = None
    if args.formats:
        formats = [f.strip() for f in args.formats.split(",")]
        for f in formats:
            if f not in FORMATS:
                raise SystemExit(f"未知格式 {f}，可选：{','.join(FORMATS)}")

    meta_ctx = load_meta(ws)
    saved = []
    for topic in topics:
        fmts = formats or _default_formats(topic)
        for fmt in fmts:
            path = generate_one(ws, topic, fmt, meta_ctx, use_llm, cfg)
            report = checks.run_checks(ws, path)
            print(checks.print_report(report))
            print(f"  → 已保存 {path}")
            saved.append(path)
        print()
    print(f"完成：{len(saved)} 份物料")


def _select_topics(ws, args) -> list:
    """按 --topics / --pillar / --since / --status / --file / --dir 多条件交集过滤。任一条件命中即过滤。"""
    from .registry import load_json
    from pathlib import Path
    wsdir = Path(ws["dir"])
    all_topics = load_json(wsdir, "topics.json", {}).get("topics", [])
    # 跳过已标 superseded 的选题
    selected = [t for t in all_topics if not t.get("superseded_at")]

    if args.topics:
        ids = {x.strip() for x in args.topics.split(",")}
        selected = [t for t in selected if t["id"] in ids]
    if args.pillar:
        selected = [t for t in selected if t.get("pillar") == args.pillar]
    if args.since:
        from datetime import date as _d
        try:
            cutoff = _d.fromisoformat(args.since)
        except ValueError:
            raise SystemExit(f"--since 需 YYYY-MM-DD 格式，得到：{args.since}")
        selected = [t for t in selected
                     if t.get("first_seen") and _d.fromisoformat(t["first_seen"]) >= cutoff]
    if args.status:
        selected = [t for t in selected if t.get("status") == args.status]
    if args.file or args.dir:
        selected = [t for t in selected if _topic_matches_file_or_dir(t, args.file, args.dir)]
    return selected


def _topic_matches_file_or_dir(topic, file_ref: str, dir_ref: str) -> bool:
    """选题 kb_refs 是否命中指定文件或目录前缀。

    kb_refs 在 PCB 库是简短标识（'01'、'PCB类型与板材'、'02（引用 Prismark 数据）'），
    不是完整路径。匹配规则：
      - file_ref：kb_ref 是否包含 file_ref，反之亦然；
      - dir_ref：拆成数字前缀（'03_' 或 '03'）与中文部分（'选型与采购'），
        任一 kb_ref startswith/contains 任一段即命中。
    """
    refs = topic.get("kb_refs") or []
    for r in refs:
        if file_ref and (file_ref in r or r in file_ref):
            return True
        if dir_ref:
            # 拆成数字前缀与中文段，分别匹配
            parts = []
            m = re.match(r"^(\d+)[_\s]*(.*)$", dir_ref)
            if m:
                parts.append(m.group(1))
                if m.group(2):
                    parts.append(m.group(2))
            parts.append(dir_ref)
            for p in parts:
                if p and (r.startswith(p) or p in r):
                    return True
    return False


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
        aff = m.get("affected_by") or []
        suffix = f" ⚠ affected_by={','.join(aff)}" if aff else ""
        print(f"  {m['id']} [{m['format']}] {m['status']}"
              f" fact={c.get('fact')} geo={c.get('geo')} model={m.get('model')}｜{m.get('title', '')[:36]}{suffix}")


def cmd_diff(args):
    """最近一次 ingest 的变更报告：新增/变更/删除文件 + 新增/过期事实与选题 + 受影响物料。"""
    ws = load_workspace(args.workspace)
    report_path = Path(ws["dir"]) / "kbmeta" / "ingest_report.json"
    if not report_path.exists():
        raise SystemExit("无 ingest 报告：先执行 cf ingest")
    rep = json.loads(report_path.read_text(encoding="utf-8"))
    d = rep["diff"]
    print(f"ingest 时间：{rep['generated_at']}｜kb：{rep['kb_path']}")
    print()
    f = d["files"]
    print(f"文件 +{len(f['added'])} ~{len(f['modified'])} -{len(f['removed'])}")
    for p in f["added"]:
        print(f"  + {p}")
    for p in f["modified"]:
        print(f"  ~ {p}")
    for p in f["removed"]:
        print(f"  - {p}")
    print()
    fc = d["facts"]
    print(f"事实：总 {fc['total']}｜新增 {fc['new']}｜过期 {fc['superseded']}")
    if fc["new"]:
        print(f"  新增 ID（前 12）：{', '.join(fc['new_ids'][:12])}")
    print()
    tc = d["topics"]
    print(f"选题：总 {tc['total']}｜新增 {tc['new']}｜过期 {tc['superseded']}")
    if tc["new"]:
        print(f"  新增 ID：{', '.join(tc['new_ids'])}")
    print()
    if d["affected_items"]:
        print(f"受影响物料 {len(d['affected_items'])} 份（已标 affected_by，未改 status）：")
        for it in d["affected_items"]:
            print(f"  {it['id']} [{it['status']}] affected_by={','.join(it['affected_by'])}")
    else:
        print("无受影响物料")


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
    p = sub.add_parser("generate"); p.add_argument("workspace")
    # 选题选择：--topic（向后兼容单数）/ --topics（复数逗号分隔）
    g = p.add_argument_group("选题过滤（任一命中即过滤；多条件为交集）")
    g.add_argument("--topic", help="单选题 ID（向后兼容；等价 --topics=T-001）")
    g.add_argument("--topics", help="多选题 ID，逗号分隔，如 T-001,T-002")
    g.add_argument("--pillar", choices=["trust", "insight", "decision", "faq"])
    g.add_argument("--since", help="仅选 first_seen ≥ 该日（YYYY-MM-DD）")
    g.add_argument("--status", choices=["ready", "scheduled", "produced"])
    g.add_argument("--file", help="按 kb 相对文件路径过滤选题（如 02_行业格局/市场数据与趋势.md）")
    g.add_argument("--dir", help="按 kb 目录前缀过滤选题（如 03_选型与采购）")
    p.add_argument("--formats", help="逗号分隔，如 faq_page,article,video")
    p.add_argument("--llm", action="store_true")
    p.set_defaults(fn=cmd_generate)
    p = sub.add_parser("check");    p.add_argument("workspace"); p.add_argument("--id")
    p.set_defaults(fn=cmd_check)
    p = sub.add_parser("approve");  p.add_argument("workspace"); p.add_argument("--id", required=True)
    p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("export");   p.add_argument("workspace"); p.add_argument("--id")
    p.add_argument("--force", action="store_true");            p.set_defaults(fn=cmd_export)
    p = sub.add_parser("status");   p.add_argument("workspace"); p.set_defaults(fn=cmd_status)
    p = sub.add_parser("diff");     p.add_argument("workspace"); p.set_defaults(fn=cmd_diff)

    args = ap.parse_args(argv)
    # generate 命令：--topic 单数等价于 --topics
    if getattr(args, "fn", None).__name__ == "cmd_generate" and args.topic and not args.topics:
        args.topics = args.topic
    try:
        args.fn(args)
        return 0
    except SystemExit:
        raise
    except Exception as e:                                 # noqa: BLE001
        print(f"错误：{e}", file=sys.stderr)
        return 1
