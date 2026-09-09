"""FactChecker：成稿中每一个 (数值, 单位) 断言必须能溯源到事实注册表（spec §6.1）。"""
import re

from .. import numbers, registry


def check_item(item: dict, ws) -> dict:
    body = item["body"]
    index = registry.build_check_index(ws)
    assertions = numbers.extract_assertions(body)
    checked = numbers.check_assertions(assertions, index)

    failures = [a for a in checked if a["verdict"] == "FAIL"]
    warnings = [a for a in checked if a["verdict"] == "warn"]
    gaps = re.findall(r"\[数据缺口[：:][^\]]*\]", body)

    matched_ids = _match_fact_ids([a for a in checked if a["verdict"] == "pass"], ws)

    return {"total": len(checked), "failures": failures, "warnings": warnings,
            "gaps": gaps, "matched_ids": sorted(matched_ids)}


def _match_fact_ids(passed: list, ws) -> set:
    """把通过的断言映射回事实 ID（一致性矩阵用）。"""
    if not passed:
        return set()
    facts = registry.load_facts(ws)
    from ..brand import brand_assertions
    sources = {f["id"]: {(round(n["n"], 4), n["u"]) for n in f["numbers"]}
               for f in facts}
    sources["BRAND"] = {(round(a["num"], 4), a["unit"])
                        for a in brand_assertions(ws["dir"]) if a["kind"] in ("strict", "strict_bare")}
    ids = set()
    for a in passed:
        key = (round(a["num"], 4), a["unit"])
        if a["kind"] == "year":
            ids.update(fid for fid, nums in sources.items()
                       if any(u == "年" and n == key[0] for n, u in nums))
            continue
        for fid, nums in sources.items():
            if key in nums:
                ids.add(fid)
                break
    return ids
