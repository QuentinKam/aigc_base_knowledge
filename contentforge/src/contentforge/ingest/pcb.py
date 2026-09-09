"""知识库接入解析器（spec §3）。

PCB 库适配：目录角色映射 ——
    01_行业基础 / 02_行业格局 / 03_选型与采购 → 事实源（表格 + 含数字列表行）
    04_FAQ                                    → 问答资产（**Qn：** / A： 块）+ qa 事实
    05_内容生产/选题角度库                      → 选题池（编号行 → 素材目录映射）
    05_内容生产/内容模板与发布节奏              → 四类模板骨架 + 发布节奏 + 模板事实
    06_GEO优化                                 → 写作规范（GEOChecker 规则来源）

换行业时复制本文件按新目录名改 DIRS 配置即可（spec §10 可移植性）。
"""
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


def run_ingest(ws: dict, verbose: bool = True) -> dict:
    kb = Path(ws["kb_path"])
    if not kb.exists():
        raise SystemExit(f"知识库路径不存在：{kb}")
    wsdir = Path(ws["dir"])
    today = date.today().isoformat()

    file_index, facts, faq_items, topics = [], [], [], []
    templates, rules, rhythm = {}, {}, []

    md_files = sorted(p for p in kb.rglob("*.md"))
    fact_id = 0

    def add_fact(claim, source, year, cat, kb_path, line=0):
        nonlocal fact_id
        fact_id += 1
        asserts = extract_assertions(claim)
        facts.append({
            "id": f"F-{fact_id:03d}",
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
                            topics.append({
                                "id": f"T-Q{qa['id'][1:]:0>2}", "title": qa["q"],
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
                    topics.append({
                        "id": f"T-{t_id:03d}", "title": title,
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

    out = {
        "generated_at": today,
        "kb_path": str(kb),
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

    if verbose:
        print(f"[ingest] {kb}")
        for k, v in out["counts"].items():
            print(f"  {k}: {v}")
    return out


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
