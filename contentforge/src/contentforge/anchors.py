"""事实锚点（Fact Anchor）：生成契约 + 确定性验签（spec §6.1 升级）。

机制：
1. 事实入库时带唯一 ID，实体维度（scope/segment/metric）由 kbmeta/subjects.json
   词表扫描 claim 自动打标签（fact["tags"] 可显式覆盖），人工只做校验。
2. 生成时每个含数据的分句必须内嵌所引事实 ID：735 亿美元〔F-017〕。
3. 校验时按分句取 ID 查事实元组，逐项比对主体/细分/指标/数值/单位/年份——
   张冠李戴、错挂 ID、裸写数据、年份缺失全部确定性 FAIL，主链路不调用 LLM。

残余风险：ID/数字/主体全对但上下文用暗示手法歪曲，自动方案无解，靠人工抽检。
"""
import json
import re
from pathlib import Path

from . import numbers

# 〔F-017〕为主，兼容（F-017）/(F-017)/[F-017]
ANCHOR_RE = re.compile(r"[〔\[（(]\s*(F-\d{3})\s*[〕\]）)]")
ID_RE = re.compile(r"F-\d{3}")

# 分句：中文逗号/句号/分句/叹问 + 英文逗号句号（表格行与标题行在调用前剔除）
_CLAUSE_SPLIT_RE = re.compile(r"[，,。；;！？!?]")

# 表格行 / 标题行不参与锚点校验（表格数据靠"数据来源"区块，标题不承载数据引用）
def _is_exempt_line(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("|") or s.startswith("#")


class Tagger:
    """按维度组织的实体词表；别名最长匹配、命中区间不重叠。"""

    def __init__(self, dimensions: dict):
        # [(dim, canonical, alias)]，别名长的优先
        self.entries = []
        for dim, groups in dimensions.items():
            for canonical, aliases in groups.items():
                for alias in aliases:
                    self.entries.append((dim, canonical, alias))
        self.entries.sort(key=lambda e: -len(e[2]))

    def scan(self, text: str) -> dict:
        """返回 {dim: {canonical, ...}}，命中区间不重叠（先到先得）。"""
        masked = list(text)
        out: dict[str, set] = {}
        for dim, canonical, alias in self.entries:
            start = 0
            while True:
                i = text.find(alias, start)
                if i < 0:
                    break
                start = i + len(alias)
                if any(masked[j] == "␣" for j in range(i, start)):
                    continue
                for j in range(i, start):
                    masked[j] = "␣"
                out.setdefault(dim, set()).add(canonical)
        return out


def load_tagger(ws) -> Tagger:
    p = Path(ws["dir"]) / "kbmeta" / "subjects.json"
    if not p.exists():
        return Tagger({})
    data = json.loads(p.read_text(encoding="utf-8"))
    return Tagger(data.get("dimensions", {}))


def fact_tags(fact: dict, tagger: Tagger) -> dict:
    """事实的实体标签：显式 tags 覆盖，否则扫描 claim。返回 {dim: {canonical}}。"""
    if fact.get("tags"):
        return {dim: set(v) for dim, v in fact["tags"].items()}
    return tagger.scan(fact.get("claim", ""))


def fact_value_set(fact: dict) -> set:
    return {(round(n["n"], 4), n["u"]) for n in fact.get("numbers", [])
            if n.get("k") in ("strict", "strict_bare")}


def fact_years(fact: dict) -> set:
    years = {int(n["n"]) for n in fact.get("numbers", []) if n.get("k") == "year"}
    if fact.get("year"):
        years.add(int(fact["year"]))
    return years


def find_anchors(text: str) -> list:
    return ANCHOR_RE.findall(text)


def has_anchor(text: str) -> bool:
    return bool(ANCHOR_RE.search(text))


def _fail(failures, rule, msg, line, snippet, fid=None, num=None):
    rec = {"rule": rule, "msg": msg, "line": line, "snippet": snippet[:60]}
    if fid:
        rec["fid"] = fid
    if num is not None:
        rec["num"] = num
    failures.append(rec)


def verify_body(body: str, facts: list, tagger: Tagger,
                skip_lines: set = None, allowed_ids: set = None) -> dict:
    """对正文做锚点验签。

    返回 {anchored, failures, warnings, matched_ids}。
    - 全文（非豁免区）无锚点 → anchored=False，调用方走旧版裸值规则。
    - 有锚点 → 契约模式：未挂锚点的严格数字一律 FAIL。
    """
    skip_lines = skip_lines or set()
    facts_map = {f["id"]: f for f in facts}
    tag_cache = {f["id"]: fact_tags(f, tagger) for f in facts}
    val_cache = {f["id"]: fact_value_set(f) for f in facts}
    year_cache = {f["id"]: fact_years(f) for f in facts}

    failures, warnings_, matched = [], [], set()

    # 先判断是否进入契约模式（豁免区外出现锚点）
    contract = False
    for i, line in enumerate(body.splitlines(), start=1):
        if i not in skip_lines and not _is_exempt_line(line) and ANCHOR_RE.search(line):
            contract = True
            break
    if not contract:
        return {"anchored": False, "failures": failures, "warnings": warnings_,
                "matched_ids": matched}

    # 段落级上下文：主体可沿同段分句继承（"全球……，其中大陆……"），年份同理
    para_scope = None        # canonical scope tag
    para_years: set = set()

    for i, raw_line in enumerate(body.splitlines(), start=1):
        if i in skip_lines or _is_exempt_line(raw_line):
            continue
        if not raw_line.strip():
            para_scope, para_years = None, set()
            continue

        for clause in _CLAUSE_SPLIT_RE.split(raw_line):
            text = clause.strip()
            if not text:
                continue
            anchors = ANCHOR_RE.findall(text)
            assertions = numbers.extract_assertions(ANCHOR_RE.sub("", text))
            strict = [a for a in assertions if a["kind"] in ("strict", "strict_bare")]
            clause_years = {int(a["num"]) for a in assertions if a["kind"] == "year"}
            clause_tags = tagger.scan(text)
            clause_scope = clause_tags.get("scope", set())

            # 无论是否带锚点，分句中明示的主体/年份更新段落上下文
            if clause_scope:
                para_scope = next(iter(clause_scope))
            para_years |= clause_years

            if not anchors:
                # 带严格数字却没挂锚点 → 游离断言（裸年份叙述不要求锚点）
                for a in strict:
                    _fail(failures, "anchor:bare",
                          f"游离数据断言「{a['raw'].strip()}」未挂事实 ID（〔F-xxx〕）",
                          i, text, num=a["num"])
                continue

            if len(anchors) > 1:
                _fail(failures, "anchor:multi",
                      f"一个数据分句只能挂一个事实 ID，发现 {len(anchors)} 个：{anchors}",
                      i, text)
                continue

            fid = anchors[0]
            fact = facts_map.get(fid)
            if fact is None:
                _fail(failures, "anchor:unknown", f"锚点 {fid} 不在事实注册表中", i, text, fid)
                continue
            if allowed_ids and fid not in allowed_ids:
                _fail(failures, "anchor:scope", f"锚点 {fid} 不在本次事实包内（越权引用）", i, text, fid)
                continue

            fvals, fyears, ftags = val_cache[fid], year_cache[fid], tag_cache[fid]
            n_fail_before = len(failures)

            # 1) 数值 + 单位必须在所挂事实内
            for a in strict:
                if (round(a["num"], 4), a["unit"]) not in fvals:
                    _fail(failures, "anchor:value",
                          f"「{a['raw'].strip()}」与 {fid} 的数值/单位不符（值对但挂错 ID 也在此拦截）",
                          i, text, fid, num=a["num"])

            # 2) 年份：事实有年份则分句或同段前文必须出现；分句年份不得越界
            if fyears:
                if not (clause_years & fyears) and not (para_years & fyears):
                    _fail(failures, "anchor:year",
                          f"数据句缺少 {fid} 的年份（{sorted(fyears)}），归属年份必须显式或同段承接",
                          i, text, fid)
            allowed_years = fyears | (para_years - clause_years)
            for y in clause_years:
                if fyears and y not in allowed_years:
                    _fail(failures, "anchor:year",
                          f"分句年份 {y} 与 {fid}（{sorted(fyears)}）不符", i, text, fid)

            # 3) 主体（scope）：必须能确认，且与事实主体一致；同段前文可继承
            fact_scope = ftags.get("scope", set())
            if fact_scope:
                effective_scope = clause_scope or ({para_scope} if para_scope else set())
                if not effective_scope:
                    _fail(failures, "anchor:subject-missing",
                          f"无法确认数据句主体（未登录主体表述 FAIL-closed，转人工/LLM 归类）；{fid} 主体为 {'/'.join(sorted(fact_scope))}",
                          i, text, fid)
                else:
                    for s in effective_scope:
                        if s not in fact_scope:
                            _fail(failures, "anchor:subject",
                                  f"主体不一致：分句主体「{s}」≠ {fid} 事实主体「{'/'.join(sorted(fact_scope))}」",
                                  i, text, fid)

            # 4) 细分品类 / 指标：分句明示的标签必须是事实标签的子集
            for dim in ("segment", "metric"):
                fact_dim = ftags.get(dim, set())
                for t in clause_tags.get(dim, set()):
                    if fact_dim and t not in fact_dim:
                        _fail(failures, f"anchor:{dim}",
                              f"{dim} 不符：「{t}」不属于 {fid}（{'/'.join(sorted(fact_dim))}）",
                              i, text, fid)

            if len(failures) == n_fail_before:
                matched.add(fid)

    return {"anchored": True, "failures": failures, "warnings": warnings_,
            "matched_ids": matched}


def render_anchors(body: str, facts_map: dict, files: list = None) -> str:
    """导出渲染：〔F-017〕→（来源：X，年份）。内部锚点稿与对外来源稿一次切换。"""
    from .pipelines.base import source_label

    def repl(m):
        fid = m.group(1)
        f = facts_map.get(fid)
        if not f:
            return m.group(0)
        label = source_label(f.get("source", ""), files or [])
        if f.get("year"):
            return f"（来源：{label}，{f['year']}）"
        return f"（来源：{label}）"

    return ANCHOR_RE.sub(repl, body)
