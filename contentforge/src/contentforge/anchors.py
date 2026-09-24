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
        self.dimensions = dimensions
        # [(dim, canonical, alias)]，别名长的优先
        self.entries = []
        for dim, groups in dimensions.items():
            for canonical, aliases in groups.items():
                for alias in aliases:
                    self.entries.append((dim, canonical, alias))
        self.entries.sort(key=lambda e: -len(e[2]))

    def with_aliases(self, dim: str, mapping: dict) -> "Tagger":
        """返回注入临时别名的新 Tagger（LLM 归类经确定性闸复验前的一次性词表）。

        mapping = {canonical: [新别名, ...]}；canonical 不存在时也可新建标签组。
        """
        newdims = {d: {c: list(a) for c, a in groups.items()}
                   for d, groups in self.dimensions.items()}
        newdims.setdefault(dim, {})
        for canonical, phrases in mapping.items():
            newdims[dim].setdefault(canonical, [])
            for p in phrases:
                if p and p not in newdims[dim][canonical]:
                    newdims[dim][canonical].append(p)
        return Tagger(newdims)

    def scan(self, text: str, adjacent_merge: bool = True) -> dict:
        """返回 {dim: {canonical, ...}}。

        规则：命中区间不重叠（长别名优先）。adjacent_merge=True（分句侧默认）时，
        同一维度内相邻命中按中文左修饰结构合并——「产值增速」「产值占比」中心语
        在右，只保留右侧标签，避免复合词把两个 metric 标签同时打到分句上造成误杀。
        事实侧扫描必须传 False：一条事实可合法承载多个指标
        （「占比 56.1%（约 412.13 亿美元）」= 占比份额+产值规模）。
        跨维度相邻（如「汽车产值」=segment+metric）始终各自保留。
        """
        hits = []   # (start, end, dim, canonical)
        for dim, canonical, alias in self.entries:
            start = 0
            while True:
                i = text.find(alias, start)
                if i < 0:
                    break
                start = i + len(alias)
                hits.append((i, i + len(alias), dim, canonical))
        # 长别名优先占位；同长按词典序（确定性）
        hits.sort(key=lambda h: (-(h[1] - h[0]), h[0], h[2]))
        occupied = []
        kept = []
        for h in hits:
            if any(not (h[1] <= s or h[0] >= e) for s, e in occupied):
                continue
            occupied.append((h[0], h[1]))
            kept.append(h)
        # 同维度相邻合并（仅分句侧）：左邻是修饰语，丢弃保留右侧中心语（迭代到稳定）
        if adjacent_merge:
            changed = True
            while changed:
                changed = False
                kept.sort(key=lambda h: h[0])
                for a_i in range(len(kept)):
                    for b_i in range(a_i + 1, len(kept)):
                        a, b = kept[a_i], kept[b_i]
                        if a[2] == b[2] and a[1] == b[0]:
                            kept.pop(a_i)
                            changed = True
                            break
                    if changed:
                        break
        out: dict[str, set] = {}
        for _, _, dim, canonical in kept:
            out.setdefault(dim, set()).add(canonical)
        return out


def _subjects_path(ws) -> Path:
    return Path(ws["dir"]) / "kbmeta" / "subjects.json"


def load_dimensions(ws) -> dict:
    p = _subjects_path(ws)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("dimensions", {})


def load_tagger(ws) -> Tagger:
    return Tagger(load_dimensions(ws))


def fact_tags(fact: dict, tagger: Tagger) -> dict:
    """事实的实体标签：显式 tags 覆盖，否则扫描 claim（不做相邻合并——事实可含多指标）。"""
    if fact.get("tags"):
        return {dim: set(v) for dim, v in fact["tags"].items()}
    return tagger.scan(fact.get("claim", ""), adjacent_merge=False)


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
                skip_lines: set = None, allowed_ids: set = None,
                extra_aliases: dict = None) -> dict:
    """对正文做锚点验签。

    返回 {anchored, failures, warnings, matched_ids}。
    - 全文（非豁免区）无锚点 → anchored=False，调用方走旧版裸值规则。
    - 有锚点 → 契约模式：未挂锚点的严格数字一律 FAIL。
    - extra_aliases：{canonical: [别名]} 临时并入 scope 词表（LLM 归类复验用，不落盘）。
    """
    if extra_aliases:
        tagger = tagger.with_aliases("scope", extra_aliases)
    skip_lines = skip_lines or set()
    facts_map = {f["id"]: f for f in facts}
    tag_cache = {f["id"]: fact_tags(f, tagger) for f in facts}
    val_cache = {f["id"]: fact_value_set(f) for f in facts}
    year_cache = {f["id"]: fact_years(f) for f in facts}
    # 数值级主体约束：(fid, (n,u)) → scope 集合（一条事实内含多组「地区↔数值」时用，如 F-131）
    num_scope_cache = {}
    for f in facts:
        for n in f.get("numbers", []):
            if n.get("scope"):
                num_scope_cache.setdefault(
                    f["id"], {}).setdefault(
                    (round(n["n"], 4), n["u"]), set()).add(n["scope"])

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
            matched_num_scopes: set = set()   # 本分句命中的数值自带的主体约束

            # 1) 数值 + 单位必须在所挂事实内
            for a in strict:
                key = (round(a["num"], 4), a["unit"])
                if key not in fvals:
                    _fail(failures, "anchor:value",
                          f"「{a['raw'].strip()}」与 {fid} 的数值/单位不符（值对但挂错 ID 也在此拦截）",
                          i, text, fid, num=a["num"])
                else:
                    matched_num_scopes |= num_scope_cache.get(fid, {}).get(key, set())

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

            # 3) 主体（scope）：必须能确认，且与事实主体一致；同段前文可继承。
            #    若命中的具体数值自带 scope（一事实多组地区↔数值），约束细化到数值级。
            fact_scope = ftags.get("scope", set())
            if fact_scope:
                effective_scope = clause_scope or ({para_scope} if para_scope else set())
                if not effective_scope:
                    rec = {"rule": "anchor:subject-missing",
                           "msg": f"无法确认数据句主体（未登录主体表述 FAIL-closed，转人工/LLM 归类）；{fid} 主体为 {'/'.join(sorted(fact_scope))}",
                           "line": i, "snippet": text[:60], "fid": fid,
                           "clause": text}
                    failures.append(rec)
                else:
                    allowed_scope = matched_num_scopes or fact_scope
                    scope_label = '/'.join(sorted(matched_num_scopes)) if matched_num_scopes \
                        else '/'.join(sorted(fact_scope))
                    for s in effective_scope:
                        if s not in allowed_scope:
                            _fail(failures, "anchor:subject",
                                  f"主体不一致：分句主体「{s}」≠ {fid} 该数值主体「{scope_label}」",
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
