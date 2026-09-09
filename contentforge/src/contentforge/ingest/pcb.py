"""知识库接入解析器（spec §3）。

PCB 库适配：目录角色映射 ——
    01_行业基础 / 02_行业格局 / 03_选型与采购 → 事实源（表格 + 含数字列表行）
    04_FAQ                                    → 问答资产（**Qn：** / A： 块）+ qa 事实
    05_内容生产/选题角度库                      → 选题池（编号行 → 素材目录映射）
    05_内容生产/内容模板与发布节奏              → 四类模板骨架 + 发布节奏 + 模板事实
    06_GEO优化                                 → 写作规范（GEOChecker 规则来源）

增量 ingest（spec §3 解析失败容忍 + §10 可追溯/幂等）：
  - 每次全量解析 kb，但 facts.json / topics.json 采用幂等键合并：
        facts  键 = (kb_ref 文件路径, claim 前 80 字)
        topics 键 = (title, kb_refs 元组)
    命中旧记录 → 复用旧 ID，仅更新可变字段（source/year/numbers）；
    未命中     → 分配新 ID（已用最大 ID +1）。
    旧有但新解析无的 → 标 superseded_at，不删除（保历史供 front-matter 追溯）。
  - 每个 kb 文件 sha256 落 kbmeta/file_hashes.json，供 `cf diff` 报告变更。

换行业时复制本文件按新目录名改 DIRS 配置即可（spec §10 可移植性）。
"""
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from .. import mdutil
from ..numbers import extract_assertions

DIRS = {
    "facts_dirs": ("01_", "02_", "03_"),
    "faq_dir": "04_",
    "topics_file": "选题角度库",
    "templates_file": "内容模板与发布节奏",
    "rules_dir": "06_",
}

PILLAR_MAP = {"①": "trust", "②": "insight", "③": "decision", "④": "faq"}

BANNED_WORDS = ["第一品牌", "顶级", "行业领先", "绝对", "完美",
                "颠覆", "革命性", "无与伦比", "遥遥领先", "独一无二的", "业内最强"]


def _has_digit(s: str) -> bool:
    return any(ch.isdigit() for ch in s)


def _year_of(s: str):
    m = re.search(r"(19|20)\d{2}", s or "")
    return int(m.group(0)) if m else None


def _classify_table(table, rel) -> list:
    """按表头把行转成事实条目。"""
    header = table["header"]
    facts = []
    hset = [h.strip() for h in header]
    if hset[:2] == ["数据", "数值"] and len(hset) >= 3:      # 02 市场数据表
        for row in table["rows"]:
            row += [""] * (len(hset) - len(row))
            if not _has_digit(row[1]):
                continue
            facts.append({"claim": f"{row[0]}：{row[1]}", "source": row[2] or rel,
                          "year": _year_of(row[3] if len(row) > 3 else "") or _year_of(row[1]),
                          "cat": "market_data"})
    elif hset[0] in ("标准", "行业") and len(hset) >= 2:      # 03 标准表 / 认证表
        for row in table["rows"]:
            row += [""] * (len(hset) - len(row))
            if not _has_digit("".join(row)):
                continue
            extra = f"（适用：{row[2]}）" if len(row) > 2 and row[2] else ""
            facts.append({"claim": f"{row[0]}｜{row[1]}{extra}",
                          "source": rel, "year": None, "cat": "standard"})
    elif len(hset) == 2:                                      # 01 参数表
        for row in table["rows"]:
            row += ["", ""]
            if not _has_digit(row[1]):
                continue
            facts.append({"claim": f"{row[0]}：{row[1]}", "source": rel,
                          "year": None, "cat": "param"})
    else:                                                     # 其他表逐行收
        for row in table["rows"]:
            joined = " ｜ ".join(c for c in row if c)
            if _has_digit(joined):
                facts.append({"claim": joined, "source": rel, "year": None, "cat": "misc"})
    return facts


def _dir_of(rel_parts) -> str:
    return rel_parts[0] if rel_parts else ""


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _file_hashes_path(wsdir: Path) -> Path:
    return wsdir / "kbmeta" / "file_hashes.json"


def _load_old(wsdir: Path) -> tuple:
    """读旧 facts.json / topics.json / file_hashes.json，缺失返回空。"""
    reg = wsdir / "registry" / "facts.json"
    old_facts = json.loads(reg.read_text(encoding="utf-8"))["facts"] if reg.exists() else []
    tp = wsdir / "topics.json"
    old_topics = json.loads(tp.read_text(encoding="utf-8")).get("topics", []) if tp.exists() else []
    fh = _file_hashes_path(wsdir)
    old_hashes = json.loads(fh.read_text(encoding="utf-8")) if fh.exists() else {}
    return old_facts, old_topics, old_hashes


def _fact_key(f: dict) -> tuple:
    """幂等键：(文件路径部分, claim 前 80 字)。行号不参与键以避免编辑后漂移。"""
    kb_ref = f.get("kb_ref", "")
    path_part = kb_ref.split(":")[0] if kb_ref else ""
    return (path_part, (f.get("claim") or "")[:80])


def _topic_key(t: dict) -> tuple:
    return (t.get("title", ""), tuple(t.get("kb_refs") or []))


def _merge_facts(new_facts: list, old_facts: list) -> tuple:
    """合并新旧事实：复用旧 ID；旧有但 new 无的 → 标 superseded。返回 (merged, new_ids)。"""
    today = date.today().isoformat()
    old_by_key = {_fact_key(f): f for f in old_facts}
    used_ids = set()
    max_id = 0

    def _id_num(fact_id: str) -> int:
        m = re.match(r"F-(\d+)", fact_id or "")
        return int(m.group(1)) if m else 0

    for f in old_facts:
        n = _id_num(f["id"])
        if n:
            used_ids.add(n)
            if n > max_id:
                max_id = n

    merged, new_ids = [], []
    for nf in new_facts:
        key = _fact_key(nf)
        if key in old_by_key:
            of = old_by_key.pop(key)
            # 复用旧 ID，更新可变字段
            of.update({
                "claim": nf["claim"], "source": nf["source"], "year": nf["year"],
                "cat": nf["cat"], "kb_ref": nf["kb_ref"], "numbers": nf["numbers"],
            })
            of.pop("superseded_at", None)
            of.pop("supersede_reason", None)
            merged.append(of)
        else:
            max_id += 1
            while max_id in used_ids:
                max_id += 1
            used_ids.add(max_id)
            nf["id"] = f"F-{max_id:03d}"
            nf["first_seen"] = today
            merged.append(nf)
            new_ids.append(nf["id"])

    # 剩余 old_by_key 中的：kb 中已不存在，标 superseded（不删除）
    for of in old_by_key.values():
        of["superseded_at"] = today
        of.setdefault("supersede_reason", "removed_from_kb")
        merged.append(of)

    return merged, new_ids


def _merge_topics(new_topics: list, old_topics: list) -> tuple:
    """合并选题：复用旧 ID + 给新增选题打 first_seen。返回 (merged, added_ids)。"""
    today = date.today().isoformat()
    old_by_key = {_topic_key(t): t for t in old_topics}
    used_ids = set()
    max_n = 0

    def _topic_num(tid: str) -> int:
        m = re.match(r"T-(\d+)", tid or "")
        return int(m.group(1)) if m else 0

    for t in old_topics:
        n = _topic_num(t["id"])
        if n:
            used_ids.add(n)
            if n > max_n:
                max_n = n

    merged, added = [], []
    for nt in new_topics:
        key = _topic_key(nt)
        if key in old_by_key:
            ot = old_by_key.pop(key)
            for k in ("pillar", "kb_refs", "faq_ref", "audience",
                     "platforms", "angle", "status"):
                if k in nt:
                    ot[k] = nt[k]
            ot.pop("superseded_at", None)
            merged.append(ot)
        else:
            max_n += 1
            while max_n in used_ids:
                max_n += 1
            used_ids.add(max_n)
            nt["id"] = f"T-{max_n:03d}"
            nt["first_seen"] = today
            merged.append(nt)
            added.append(nt["id"])

    # 旧选题不在 new 中（选题池被删/编辑）→ 标 superseded
    for ot in old_by_key.values():
        ot["superseded_at"] = today
        ot.setdefault("supersede_reason", "removed_from_topic_pool")
        merged.append(ot)

    return merged, added


def run_ingest(ws: dict, verbose: bool = True) -> dict:
    kb = Path(ws["kb_path"])
    if not kb.exists():
        raise SystemExit(f"知识库路径不存在：{kb}")
    wsdir = Path(ws["dir"])
    today = date.today().isoformat()

    old_facts, old_topics, old_hashes = _load_old(wsdir)

    file_index, new_facts, faq_items, new_topics = [], [], [], []
    templates, rules, rhythm = {}, {}, []
    new_hashes = {}

    md_files = sorted(p for p in kb.rglob("*.md"))
    seq = [0]  # 闭包计数器
    seen_keys = set()  # 单次 ingest 内 add_fact 去重，避免同 (kb_ref, claim) 抽取多份

    def add_fact(claim, source, year, cat, kb_path, line=0):
        key = (kb_path, (claim or "").strip()[:80])
        if key in seen_keys:
            return
        seen_keys.add(key)
        seq[0] += 1
        asserts = extract_assertions(claim)
        new_facts.append({
            "id": f"F-TEMP{seq[0]:03d}",   # 临时 ID，merge 阶段重分配
            "claim": claim.strip()[:300],
            "source": source,
            "year": year,
            "cat": cat,
            "kb_ref": f"{kb_path}:{line}" if line else kb_path,
            "numbers": [{"n": a["num"], "u": a["unit"], "k": a["kind"]} for a in asserts],
        })

    for f in md_files:
        rel = f.relative_to(kb)
        relstr = str(rel)
        text = mdutil.read(f)
        new_hashes[relstr] = _sha256_file(f)
        d0 = _dir_of(rel.parts)
        sections = mdutil.parse_sections(text)
        summary = ""
        m = re.search(r"^>\s*摘要[：:]\s*(.+)$", text, re.M)
        if m:
            summary = m.group(1).strip()
        file_index.append({
            "path": relstr, "title": f.stem,
            "summary": summary,
            "headings": [s["title"] for s in sections if s["level"] <= 3],
        })

        # --- FAQ 库 ---
        if relstr.startswith(DIRS["faq_dir"]):
            for qa in mdutil.parse_qa_blocks(text):
                faq_items.append({
                    "id": qa["id"], "q": qa["q"],
                    "a": qa["a"],
                    "a_direct": mdutil.first_sentence(qa["a"]),
                    "line": qa["line"],
                })
                add_fact(f"FAQ {qa['id']} {qa['q']}｜答：{qa['a']}",
                         relstr, None, "qa", relstr, qa["line"])

        # --- 事实源：表格 + 含数字列表行 ---
        if d0.startswith(DIRS["facts_dirs"]):
            for table in mdutil.parse_tables(text):
                for ft in _classify_table(table, relstr):
                    add_fact(ft["claim"], ft["source"], ft["year"], ft["cat"],
                             relstr, table["line"])
            for b in mdutil.bullets(text):
                if "http" in b["text"] or len(b["text"]) > 220 or not _has_digit(b["text"]):
                    continue
                if not any(a["kind"] in ("strict", "strict_bare")
                           for a in extract_assertions(b["text"])):
                    continue
                cat = {"01_": "process", "02_": "market_data", "03_": "decision"}.get(d0[:3], "misc")
                add_fact(b["text"], relstr, None, cat, relstr, b["line"])

        # --- 选题池 ---
        if rel.stem == DIRS["topics_file"]:
            pillar = "trust"
            t_id = 0
            for s in sections:
                pm = re.search(r"支柱([①②③④])", s["title"])
                if pm:
                    pillar = PILLAR_MAP[pm.group(1)]
                for line in s["text"].splitlines():
                    m2 = re.match(r"^(\d{1,2})\.\s*(.+?)(?:\s*→\s*(.+))?$", line.strip())
                    if not m2:
                        continue
                    title, ref = m2.group(2).strip(), (m2.group(3) or "").strip()
                    if "04_FAQ" in title:      # 元选题：展开为逐条 FAQ 选题
                        for qa in faq_items:
                            new_topics.append({
                                "id": f"T-TEMP{len(new_topics)+1:03d}",
                                "title": qa["q"],
                                "pillar": "faq", "kb_refs": [DIRS["faq_dir"]],
                                "faq_ref": qa["id"],
                                "audience": "采购/研发工程师",
                                "platforms": ["site", "zhihu", "douyin"],
                                "angle": f"FAQ {qa['id']} 改写多平台版本",
                                "status": "ready",
                            })
                        continue
                    t_id += 1
                    refs = [r.strip() for r in re.split(r"[、/]", ref) if r.strip()] if ref else []
                    new_topics.append({
                        "id": f"T-TEMP{len(new_topics)+1:03d}",
                        "title": title,
                        "pillar": pillar,
                        "kb_refs": refs or [d0],
                        "faq_ref": None,
                        "audience": "采购/研发工程师",
                        "platforms": ["site", "zhihu", "douyin"],
                        "angle": title,
                        "status": "ready",
                    })

        # --- 模板与节奏 ---
        if rel.stem == DIRS["templates_file"]:
            tmap = {"模板一": "faq_page", "模板二": "article", "模板三": "video", "模板四": "data_article"}
            for s in sections:
                for zh, en in tmap.items():
                    if s["title"].startswith(zh):
                        blocks = mdutil.parse_fenced_blocks(s["text"])
                        templates[en] = {
                            "title": s["title"],
                            "structure": blocks[0]["body"] if blocks else s["text"],
                        }
            for table in mdutil.parse_tables(text):
                if table["header"] and table["header"][0] == "频率":
                    for row in table["rows"]:
                        if len(row) >= 2:
                            rhythm.append({"frequency": row[0], "action": row[1]})
            # 模板骨架与标题中的数字（如 60-90 秒）注册为模板事实，供成稿引用
            for en, t in templates.items():
                for a in extract_assertions(t["structure"] + " " + t["title"]):
                    if a["kind"] in ("strict", "strict_bare"):
                        add_fact(f"模板约束（{en}）：{a['raw'].strip()} 出自模板结构",
                                 relstr, None, "template", relstr, 0)

        # --- GEO 规则 ---
        if d0.startswith(DIRS["rules_dir"]):
            for s in sections:
                if "写作规范" in s["title"]:
                    rules["six_rules"] = [b["text"] for b in mdutil.bullets(s["text"])]
                if "常见错误" in s["title"]:
                    rules["common_errors"] = [b["text"].lstrip("❌ ") for b in mdutil.bullets(s["text"])]
                if "发布与分发" in s["title"]:
                    rules["distribution"] = mdutil.parse_tables(s["text"])

    # 模板事实补挂（上面 templates 循环内 add_fact 使用的 line 字段不存在 → 0，可接受）
    rules["banned_words"] = BANNED_WORDS
    rules["fact_density_per_300"] = 2

    # ===== 增量合并 =====
    facts, added_fact_ids = _merge_facts(new_facts, old_facts)
    topics, added_topic_ids = _merge_topics(new_topics, old_topics)

    # 受影响物料：扫 content/C-*.md，引用了 superseded 事实的标 affected_by
    affected = _mark_affected_items(wsdir, facts)

    out = {
        "generated_at": today,
        "kb_path": str(kb),
        "diff": {
            "files": {
                "added": sorted(set(new_hashes) - set(old_hashes)),
                "modified": sorted(p for p in (set(new_hashes) & set(old_hashes))
                                   if new_hashes[p] != old_hashes[p]),
                "removed": sorted(set(old_hashes) - set(new_hashes)),
            },
            "facts": {
                "total": len(facts),
                "new": len(added_fact_ids),
                "new_ids": added_fact_ids,
                "superseded": sum(1 for f in facts if f.get("superseded_at")),
            },
            "topics": {
                "total": len(topics),
                "new": len(added_topic_ids),
                "new_ids": added_topic_ids,
                "superseded": sum(1 for t in topics if t.get("superseded_at")),
            },
            "affected_items": affected,
        },
        "counts": {
            "files": len(file_index), "facts": len(facts),
            "faq": len(faq_items), "topics": len(topics),
            "templates": list(templates), "rules": bool(rules.get("six_rules")),
        },
    }
    (wsdir / "registry").mkdir(parents=True, exist_ok=True)
    (wsdir / "kbmeta").mkdir(parents=True, exist_ok=True)
    (wsdir / "registry" / "facts.json").write_text(
        json.dumps({"generated_at": today, "kb_path": str(kb), "facts": facts},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    (wsdir / "kbmeta" / "faq.json").write_text(
        json.dumps({"items": faq_items}, ensure_ascii=False, indent=1), encoding="utf-8")
    (wsdir / "topics.json").write_text(
        json.dumps({"generated_at": today, "topics": topics,
                    "platforms_config": _platforms_config(kb)},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    (wsdir / "kbmeta" / "templates.json").write_text(
        json.dumps({"templates": templates, "rhythm": rhythm}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    (wsdir / "kbmeta" / "rules.json").write_text(
        json.dumps(rules, ensure_ascii=False, indent=1), encoding="utf-8")
    (wsdir / "kbmeta" / "files.json").write_text(
        json.dumps({"files": file_index}, ensure_ascii=False, indent=1), encoding="utf-8")
    (wsdir / "kbmeta" / "ingest_report.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    _file_hashes_path(wsdir).write_text(
        json.dumps(new_hashes, ensure_ascii=False, indent=1), encoding="utf-8")

    if verbose:
        print(f"[ingest] {kb}")
        for k, v in out["counts"].items():
            print(f"  {k}: {v}")
        d = out["diff"]
        if d["files"]["added"]:
            print(f"  新增文件：{len(d['files']['added'])} 个")
            for p in d["files"]["added"]:
                print(f"    + {p}")
        if d["files"]["modified"]:
            print(f"  变更文件：{len(d['files']['modified'])} 个")
            for p in d["files"]["modified"]:
                print(f"    ~ {p}")
        if d["files"]["removed"]:
            print(f"  删除文件：{len(d['files']['removed'])} 个")
            for p in d["files"]["removed"]:
                print(f"    - {p}")
        if d["facts"]["new"]:
            print(f"  新增事实 {d['facts']['new']} 条"
                  + (f"：{', '.join(d['facts']['new_ids'][:6])}" if d['facts']['new_ids'] else ""))
        if d["facts"]["superseded"]:
            print(f"  过期事实 {d['facts']['superseded']} 条（标 superseded_at，保留供历史追溯）")
        if d["topics"]["new"]:
            print(f"  新增选题 {d['topics']['new']} 条：{', '.join(d['topics']['new_ids'])}")
        if d["topics"]["superseded"]:
            print(f"  过期选题 {d['topics']['superseded']} 条")
        if d["affected_items"]:
            print(f"  受影响物料 {len(d['affected_items'])} 份（已标 affected_by，未改 status）")
    return out


def _mark_affected_items(wsdir: Path, facts: list) -> list:
    """扫 content/C-*.md，凡引用了 superseded 事实的物料在 front-matter 写 affected_by。"""
    from ..pipelines.base import load_item, update_item
    super_ids = {f["id"] for f in facts if f.get("superseded_at")}
    if not super_ids:
        return []
    affected = []
    content_dir = wsdir / "content"
    if not content_dir.exists():
        return []
    for p in sorted(content_dir.glob("C-*.md")):
        try:
            item = load_item(p)
        except Exception:
            continue
        meta = item["meta"]
        cited = meta.get("facts") or []
        hit = [fid for fid in cited if fid in super_ids]
        if not hit:
            # 清理之前的 affected_by（事实被重新激活的情况）
            if meta.get("affected_by"):
                update_item(p, affected_by=[])
            continue
        existing = set(meta.get("affected_by") or []) | set(hit)
        if list(existing) != (meta.get("affected_by") or []):
            update_item(p, affected_by=sorted(existing))
            affected.append({"id": meta.get("id"), "file": p.name,
                              "affected_by": sorted(existing),
                              "status": meta.get("status")})
    return affected


def _platforms_config(kb: Path) -> list:
    f = None
    for p in kb.rglob(f"*{DIRS['topics_file']}*.md"):
        f = p
        break
    if not f:
        return []
    text = mdutil.read(f)
    for table in mdutil.parse_tables(text):
        if table["header"] and "平台" in table["header"][0]:
            return [{"platform": r[0], "format": r[1] if len(r) > 1 else "",
                     "note": r[2] if len(r) > 2 else ""} for r in table["rows"] if r]
    return []
