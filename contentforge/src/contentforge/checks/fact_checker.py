"""FactChecker：两道防线（spec §6.1）。

- 契约模式（正文带事实锚点〔F-xxx〕）：走 anchors.verify_body 确定性验签——
  主体/细分/指标/数值/单位/年份按 ID 绑定的元组逐项比对，拦截张冠李戴。
- 旧版模式（无锚点，存量物料）：成稿 (数值, 单位) 断言必须能溯源到事实注册表，
  额外给迁移警告；新生成内容必须挂锚点。
"""
import re

from .. import anchors, mdutil, numbers, registry

# 拍摄执行区块：这些小节是给拍摄/剪辑的执行指令（画面示意数字、道具与设备数量），
# 不属于事实性正文，其中的数字不参与溯源；真实业务数据仍由正文（口播稿/直接回答/正文段落）覆盖。
PRODUCTION_SECTIONS = ("分镜表", "拍摄清单")
# 营销文案区块（与 geo_checker NON_DATA_SECTIONS 同源）：钩子/封面/发布文案不强制锚点
NON_DATA_SECTIONS = ("钩子备选", "分镜表", "封面与标题", "发布文案", "拍摄清单")


def check_item(item: dict, ws, llm_assist: bool = False,
               chat_json_fn=None, threshold: float = 0.9, model: str = "") -> dict:
    body = item["body"]
    facts = registry.load_facts(ws)
    tagger = anchors.load_tagger(ws)
    allowed = set(item.get("meta", {}).get("facts") or [])

    # 拍摄/营销区块不参与锚点验签
    anchor_skip = mdutil.section_lines(body, tuple(set(PRODUCTION_SECTIONS + NON_DATA_SECTIONS)))
    anchor_result = anchors.verify_body(body, facts, tagger,
                                        skip_lines=anchor_skip, allowed_ids=allowed or None)

    if anchor_result["anchored"]:
        # 未登录主体表述：LLM 只做归类，归类结果回确定性闸复验（默认关闭，check 纯确定性）
        if llm_assist and chat_json_fn and anchor_result["failures"]:
            from .classify import resolve_subject_missing
            dimensions = anchors.load_dimensions(ws)
            anchor_result = resolve_subject_missing(
                ws, body, anchor_result, facts, tagger, dimensions,
                chat_json_fn, threshold=threshold, model=model)
        return {"total": 0, "failures": anchor_result["failures"],
                "warnings": anchor_result["warnings"], "gaps": _gaps(body),
                "matched_ids": sorted(anchor_result["matched_ids"]),
                "mode": "anchor"}

    # ---- 旧版裸值集合校验（存量物料迁移期保留）----
    index = registry.build_check_index(ws)
    skip = mdutil.section_lines(body, PRODUCTION_SECTIONS)
    assertions = [a for a in numbers.extract_assertions(body) if a["line"] not in skip]
    checked = numbers.check_assertions(assertions, index)

    failures = [a for a in checked if a["verdict"] == "FAIL"]
    warnings = [a for a in checked if a["verdict"] == "warn"]
    warnings.append({"rule": "anchor:migration",
                     "msg": "未检测到事实锚点（〔F-xxx〕），按旧版裸值集合规则校验；新生成内容必须挂锚点（主体张冠李戴旧规则拦不住）"})
    matched_ids = _match_fact_ids([a for a in checked if a["verdict"] == "pass"], ws)

    return {"total": len(checked), "failures": failures, "warnings": warnings,
            "gaps": _gaps(body), "matched_ids": sorted(matched_ids),
            "mode": "legacy"}


def _gaps(body: str) -> list:
    return re.findall(r"\[数据缺口[：:][^\]]*\]", body)


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
