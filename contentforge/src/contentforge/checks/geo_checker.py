"""GEOChecker：知识库 06 六条写作规范的结构化门禁（spec §6.2）。"""
import re

from .. import numbers
from ..brand import parse_brand

SRC_ANNOTATION = re.compile(r"（[^（）]*(?:来源|\d{4})[^（）]*）")


def check_item(item: dict, ws) -> dict:
    body = item["body"]
    fmt = item["meta"]["format"]
    rules = _rules(ws)
    banned = rules.get("banned_words", [])
    failures, warnings = [], []

    # G5/G6 禁词（全格式）
    for w in banned:
        for m in re.finditer(re.escape(w), body):
            failures.append({"rule": "G5/6", "msg": f"夸大/空话词「{w}」",
                             "line": body[:m.start()].count("\n") + 1})

    # G5 品牌绑定
    brand = parse_brand(ws["dir"])
    if brand["complete"]:
        name = brand["fields"].get("公司名称", "")
        short = re.sub(r"（.*?）", "", name).strip()
        if short and short not in body:
            failures.append({"rule": "G5", "msg": f"品牌「{short}」未在正文自然出现"})
    else:
        warnings.append({"rule": "G5", "msg": f"品牌档案未填全（缺 {len(brand['missing'])} 项），内容为通用版"})
    if brand.get("is_placeholder"):
        warnings.append({"rule": "G5", "msg": "品牌档案为示例占位内容，替换前不得对外发布"})

    paras = [p.strip() for p in body.split("\n\n") if p.strip()]
    numeric_paras = [p for p in paras if any(
        a["kind"] in ("strict", "year") for a in numbers.extract_assertions(p))]

    # G3 事实密度：每 300 字 ≥ 2 个具体数字/标准/年份
    n_facts = sum(1 for a in numbers.extract_assertions(body) if a["kind"] in ("strict", "year"))
    density = n_facts / max(len(body) / 300, 1)
    if density < rules.get("fact_density_per_300", 2):
        failures.append({"rule": "G3", "msg": f"事实密度不足：{density:.1f}/300字（要求 ≥{rules.get('fact_density_per_300', 2)}）"})

    # G4 数据标注来源/年份：数值段落需带（来源…）/（…2025…）式标注
    # 豁免：表格行（来源在列中）、标题行、备选标题、品牌句（品牌数字来自 brand.md）
    from ..brand import parse_brand as _pb
    brand_name = re.sub(r"（.*?）", "", _pb(ws["dir"])["fields"].get("公司名称", "")).strip()
    unannotated = [p for p in numeric_paras
                   if not p.startswith(("|", "#", "（备选"))
                   and not (brand_name and brand_name in p)
                   and not SRC_ANNOTATION.search(p)
                   and "数据来源" not in p]
    if len(unannotated) > max(1, len(numeric_paras) // 3):
        failures.append({"rule": "G4", "msg": f"{len(unannotated)} 个含数据段落缺少（来源，年份）标注"})

    if fmt == "faq_page":
        _faq_rules(body, failures)
    elif fmt == "article":
        _article_rules(body, failures)
    elif fmt == "video":
        _video_rules(body, failures, warnings)
    elif fmt == "data_article":
        _data_rules(body, failures)

    return {"failures": failures, "warnings": warnings, "density": round(density, 2)}


def _first_heading(body: str) -> str:
    m = re.search(r"^#\s+(.+)$", body, re.M)
    return m.group(1).strip() if m else ""


def _faq_rules(body, failures):
    h1 = _first_heading(body)
    if not h1.endswith(("？", "?")):
        failures.append({"rule": "G2", "msg": f"FAQ 标题应为用户真实提问句式：「{h1[:30]}」"})
    m = re.search(r"\*\*直接回答[^\n]*\*\*[：:]?\s*(.+)", body)
    if not m:
        failures.append({"rule": "G1", "msg": "缺少「**直接回答**」块"})
    else:
        first = re.split(r"[。！？]", m.group(1))[0]
        if len(first) < 8:
            failures.append({"rule": "G1", "msg": "直接答案首句过短，不是完整答案"})


def _article_rules(body, failures):
    paras = [p.strip() for p in body.split("\n\n") if p.strip()]
    lead = next((p for p in paras if not p.startswith("#") and not p.startswith("（备选")), "")
    if not (any(a["kind"] in ("strict", "year") for a in numbers.extract_assertions(lead))
            or lead.startswith(("结论", "答案"))):
        failures.append({"rule": "G1", "msg": "文章未结论先行：首段应直接给结论（含数据）"})


def _video_rules(body, failures, warnings):
    required = ["钩子备选", "口播稿", "分镜表", "封面与标题", "发布文案", "拍摄清单"]
    for sec in required:
        if f"## {sec}" not in body:
            failures.append({"rule": "结构", "msg": f"物料包缺少「{sec}」小节"})
    m = re.search(r"## 口播稿[^\n]*\n(.*?)(?=\n## |\Z)", body, re.S)
    if m:
        spoken = re.sub(r"\[\d+\s*[-–]\s*\d+\s*s\]", "", m.group(1))
        spoken = re.sub(r"[\s#*|]", "", spoken)
        if not (120 <= len(spoken) <= 420):
            warnings.append({"rule": "时长", "msg": f"口播稿约 {len(spoken)} 字，建议 240-360 字（60-90 秒）"})


def _data_rules(body, failures):
    m = re.search(r"## 核心数据\n(.*?)(?=\n## |\Z)", body, re.S)
    n = 0
    if m:
        n = len([a for a in numbers.extract_assertions(m.group(1)) if a["kind"] == "strict"])
    if n < 3:
        failures.append({"rule": "数据量", "msg": f"核心数据仅 {n} 个（要求 ≥3 个带来源的数据）"})
    if "来源列表" not in body:
        failures.append({"rule": "G4", "msg": "缺少「来源列表」小节"})


def _rules(ws) -> dict:
    from ..registry import load_json
    from pathlib import Path
    return load_json(Path(ws["dir"]), "kbmeta/rules.json", {})
