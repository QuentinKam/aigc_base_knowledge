"""未登录主体表述的 LLM 归类（spec §6.1 兜底之一）。

边界（关键）：LLM 不做 pass/fail 裁决，只回答一个窄问题——
「这个未登录表述对应词表里哪个 canonical 标签」。归类结果作为临时别名
注入词表后，仍由确定性验签决定放行与否；LLM 把「大陆」硬归成「全球」
照样被锚点闸拦下。

三种结果：
- 高置信归入现有 canonical → 临时别名，重跑确定性验签
- 确认是全新主体 → 进 subjects_suggestions.json 人工审批队列，本次 FAIL
- 拿不准 / JSON 非法 / API 异常 → fail-closed，原样 FAIL

缓存：归类结论按（词表版本, fid, 分句文本）哈希缓存，词表变更自动失效。
"""
import hashlib
import json
from datetime import datetime
from pathlib import Path

from .. import anchors

CACHE_PATH = "kbmeta/subject_classify_cache.json"
SUGGEST_PATH = "kbmeta/subjects_suggestions.json"

SYSTEM = """你的任务是把一句中文行业陈述中「数据归属的地域主体」归类到给定的标准标签。
你不做事实核查、不判断句子对错，只做文本归类。
必须只输出 JSON，不要任何解释。"""

USER_TMPL = """【待归类分句】
{clause}

【该句引用事实 {fid} 的原始断言（供理解语境，不是归类依据）】
{fact_claim}

【现有标准地域标签】（canonical：已收录的表面写法）
{vocab}

输出 JSON：
{{
  "phrase": "分句中承载地域主体的原文片段（必须是分句里的连续子串）",
  "canonical": "能归入的现有标签名，不能归入时为 null",
  "new_alias": "确认是词表中不存在的全新地域主体时填其名称，否则为 null",
  "label": "new_alias 对应的建议标准名（仅 new_alias 非空时）",
  "confidence": 0.0到1.0,
  "reason": "一句话理由"
}}
判断规则：
1. phrase 是现有写法的同义/口语/局部代称（如「国内」指中国大陆市场）→ canonical 填对应标签。
2. phrase 是词表没有的新地域实体（如某城市群、某省份）→ canonical=null，填 new_alias。
3. 拿不准时 canonical 与 new_alias 都为 null，confidence 低于 0.5。"""


def _read_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _vocab_hash(ws) -> str:
    p = anchors._subjects_path(ws)
    raw = p.read_bytes() if p.exists() else b""
    return hashlib.sha1(raw).hexdigest()[:12]


def _cache_key(vhash: str, fid: str, clause: str) -> str:
    return hashlib.sha1(f"{vhash}|{fid}|{clause}".encode("utf-8")).hexdigest()[:16]


def _vocab_text(dimensions: dict) -> str:
    scope = dimensions.get("scope", {})
    return "\n".join(f"- {c}：{'、'.join(a)}" for c, a in scope.items()) or "（空词表）"


def classify_clause(ws, clause: str, fid: str, fact: dict, dimensions: dict,
                    chat_json_fn, threshold: float = 0.9, use_cache: bool = True) -> dict:
    """对单个未登录分句做归类。返回 {outcome: hit|new|reject, ...}。

    chat_json_fn(messages) -> dict（注入便于测试；生产绑 llm.chat_json）。
    任何异常/不合规输出统一 outcome=reject（fail-closed）。
    """
    wsdir = Path(ws["dir"])
    vhash = _vocab_hash(ws)
    key = _cache_key(vhash, fid, clause)

    cache = _read_json(wsdir / CACHE_PATH, {"vocab_hash": vhash, "entries": {}})
    if cache.get("vocab_hash") != vhash:
        cache = {"vocab_hash": vhash, "entries": {}}
    if use_cache and key in cache["entries"]:
        return {**cache["entries"][key], "cached": True}

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": USER_TMPL.format(
            clause=clause, fid=fid, fact_claim=fact.get("claim", ""),
            vocab=_vocab_text(dimensions))},
    ]
    try:
        data = chat_json_fn(messages)
    except Exception as e:                          # noqa: BLE001 —— 兜底统一 reject
        return {"outcome": "reject", "reason": f"llm_error: {str(e)[:80]}"}

    phrase = (data.get("phrase") or "").strip()
    canonical = data.get("canonical")
    new_alias = (data.get("new_alias") or "").strip() or None
    label = (data.get("label") or "").strip() or None
    try:
        confidence = float(data.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0.0

    scope = dimensions.get("scope", {})
    # 高置信归入现有标签，且 phrase 必须真是分句子串（防 LLM 幻觉一个不存在的写法）
    if (canonical in scope and confidence >= threshold
            and phrase and phrase in clause):
        result = {"outcome": "hit", "canonical": canonical,
                  "phrase": phrase, "confidence": confidence}
    elif new_alias and phrase and phrase in clause:
        result = {"outcome": "new", "new_alias": new_alias,
                  "label": label or new_alias, "phrase": phrase,
                  "confidence": confidence}
    else:
        result = {"outcome": "reject",
                  "reason": (data.get("reason") or "低置信/字段不合规")[:120]}

    if use_cache and result["outcome"] in ("hit", "reject"):
        cache["entries"][key] = result
        _write_json(wsdir / CACHE_PATH, cache)
    return result


def _append_suggestion(ws, rec: dict, model: str = "") -> str:
    path = Path(ws["dir"]) / SUGGEST_PATH
    data = _read_json(path, {"suggestions": []})
    # 同 (fid, phrase) 不重复入队
    for s in data["suggestions"]:
        if s["fid"] == rec["fid"] and s["phrase"] == rec["phrase"] and s.get("status") == "pending":
            return s["id"]
    nums = [int(s["id"].split("-")[1]) for s in data["suggestions"] if s.get("id", "").startswith("S-")]
    sid = f"S-{max(nums or [0]) + 1:04d}"
    data["suggestions"].append({
        "id": sid, "status": "pending", "ts": datetime.now().isoformat(timespec="seconds"),
        "model": model, **rec,
    })
    _write_json(path, data)
    return sid


def resolve_subject_missing(ws, body: str, result: dict, facts: list,
                            tagger, dimensions: dict, chat_json_fn,
                            threshold: float = 0.9, model: str = "") -> dict:
    """对验签结果中的 anchor:subject-missing 逐条归类；命中的临时别名注入后全量复验。

    返回新的验签结果（结构同 anchors.verify_body），warnings 内追加归类说明。
    """
    missing = [f for f in result["failures"] if f["rule"] == "anchor:subject-missing"]
    if not missing:
        return result

    fmap = {f["id"]: f for f in facts}
    extras: dict[str, list] = {}
    warnings = list(result.get("warnings", []))
    seen = set()

    for rec in missing:
        sig = (rec["fid"], rec["clause"])
        if sig in seen:
            continue
        seen.add(sig)
        fact = fmap.get(rec["fid"])
        if not fact:
            continue
        r = classify_clause(ws, rec["clause"], rec["fid"], fact, dimensions,
                            chat_json_fn, threshold)
        if r["outcome"] == "hit":
            extras.setdefault(r["canonical"], []).append(r["phrase"])
            warnings.append({"rule": "classify:hit",
                             "msg": f"L{rec['line']} 未登录表述「{r['phrase']}」经 LLM 归类为「{r['canonical']}」"
                                    f"（conf={r['confidence']}），已注入临时别名重跑确定性验签"})
        elif r["outcome"] == "new":
            sid = _append_suggestion(ws, {"fid": rec["fid"], "phrase": r["phrase"],
                                          "new_alias": r["new_alias"], "label": r["label"],
                                          "clause": rec["clause"],
                                          "fact_claim": fact.get("claim", "")}, model)
            warnings.append({"rule": "classify:new",
                             "msg": f"L{rec['line']} 疑似全新地域主体「{r['phrase']}」→ 审批队列 {sid}"
                                    f"（cf subjects 审批），本次仍 FAIL"})
        else:
            warnings.append({"rule": "classify:reject",
                             "msg": f"L{rec['line']} 主体表述归类失败（{r.get('reason', '')[:60]}），FAIL-closed"})

    if not extras:
        return {**result, "warnings": warnings}

    rerun = anchors.verify_body(body, facts, tagger, extra_aliases=extras)
    return {**rerun, "warnings": warnings + rerun.get("warnings", [])}
