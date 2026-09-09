"""事实注册表：加载与检查索引构建（spec §4.1、§6.1）。

检查索引 = 知识库事实 + 模板约束事实 + 选题标题 + 品牌档案 ——
生成端允许出现的全部数字都必须来自这四类人工策展内容。
"""
import json
from pathlib import Path

from . import numbers


def load_facts(ws) -> list:
    p = Path(ws["dir"]) / "registry" / "facts.json"
    if not p.exists():
        raise SystemExit("事实注册表为空，先执行 ingest")
    return json.loads(p.read_text(encoding="utf-8"))["facts"]


def load_json(wsdir: Path, rel: str, default):
    p = Path(wsdir) / rel
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def build_check_index(ws) -> dict:
    """汇总四类可引用来源的数字断言，构建 (数值, 单位) 允许集。"""
    wsdir = Path(ws["dir"])
    per_fact = {}

    for f in load_facts(ws):
        asserts = [{"num": n["n"], "unit": n["u"], "kind": n["k"]} for n in f["numbers"]]
        if f.get("year"):
            asserts.append({"num": float(f["year"]), "unit": "年", "kind": "year"})
        per_fact[f["id"]] = asserts

    # 选题标题（人工策展的选题池，数字视为可引用）
    topics = load_json(wsdir, "topics.json", {}).get("topics", [])
    for i, t in enumerate(topics):
        per_fact[f"TOPIC-{t['id']}"] = numbers.extract_assertions(t["title"])

    # 品牌档案
    from .brand import brand_assertions
    per_fact["BRAND"] = brand_assertions(wsdir)

    return numbers.build_index(per_fact)


def facts_for_kb_refs(facts: list, kb_refs: list) -> list:
    out = []
    for f in facts:
        kbfile = f["kb_ref"].split(":")[0]
        for ref in kb_refs or []:
            if kbfile.startswith(ref) or ref in kbfile:
                out.append(f)
                break
    return out
