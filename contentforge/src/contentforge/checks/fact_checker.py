"""FactChecker：成稿中每一个 (数值, 单位) 断言必须能溯源到事实注册表（spec §6.1）。"""
import re

from .. import numbers, registry

# 拍摄执行区块：这些小节是给拍摄/剪辑的执行指令（画面示意数字、道具与设备数量），
# 不属于事实性正文，其中的数字不参与溯源；真实业务数据仍由正文（口播稿/直接回答/正文段落）覆盖。
PRODUCTION_SECTIONS = ("分镜表", "拍摄清单")


def _production_lines(body: str) -> set:
    """返回拍摄执行区块（分镜表/拍摄清单）覆盖的行号集合。"""
    lines, active = set(), False
    for i, line in enumerate(body.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            active = any(s in stripped for s in PRODUCTION_SECTIONS)
        elif active:
            lines.add(i)
    return lines


def check_item(item: dict, ws) -> dict:
    body = item["body"]
    index = registry.build_check_index(ws)
    skip = _production_lines(body)
    assertions = [a for a in numbers.extract_assertions(body) if a["line"] not in skip]
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
