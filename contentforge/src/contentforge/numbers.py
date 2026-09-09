"""数字/单位断言抽取 —— FactChecker 与事实注册表共用的地基。

设计原则：同一文本两端（知识库事实 / 生成成稿）用同一套抽取规则，
检查 = 成稿的 (数值, 单位) 集合 ⊆ 注册表的 (数值, 单位) 集合。
"""
import re

# 严格单位（出现即必须能在注册表中找到），长词优先
STRICT_UNITS = [
    "亿美元", "万亿元", "亿元", "万元", "万美元", "美元", "元",
    "万平方米", "万平米", "万平方米", "平方米", "平米",
    "个百分点", "百分点", "%", "％",
    "μm", "um", "mil", "mm", "nm", "cm",
    "小时", "分钟", "天", "周", "个月", "月", "年",
    "层", "片", "块", "倍", "℃", "摄氏度", "道",
    "kHz", "MHz", "GHz", "kHz", "kV", "V", "W", "ms",
    "万人", "万人次", "万片", "亿", "万",
    "秒", "G", "M",
]
# 计数单位（结构性小数字，未匹配只告警）
COUNTER_UNITS = ["个", "条", "点", "步", "种", "大", "名", "位", "款", "家", "次", "轮",
                 "版", "句", "段", "页", "行", "项", "维", "条目"]

_UNIT_ALT = "|".join(re.escape(u) for u in sorted(STRICT_UNITS + COUNTER_UNITS, key=len, reverse=True))
_NUM = r"(\d+(?:\.\d+)?)"
_RANGE = _NUM + r"\s*[-–—~～至到]\s*" + _NUM + r"\s*(" + _UNIT_ALT + ")"
_SINGLE = r"[+±约超≥≤]?\s*" + _NUM + r"\s*(" + _UNIT_ALT + ")"
_BARE = _NUM + r"(?![\d.%℃])"
_RATIO = r"(\d+)\s*/\s*(\d+)\s*(mil|mm|μm|um)"

# 抽取前需要屏蔽的上下文
MASK_PATTERNS = [
    re.compile(r"\d{4}-\d{1,2}-\d{1,2}"),                    # 日期 2026-09-05
    re.compile(r"\d{4}年\d{1,2}月\d{1,2}日"),
    re.compile(r"\[\d+\s*[-–]\s*\d+\s*s\]"),                 # 视频时间轴 [0-3s]
    re.compile(r"\b\d+\s*[-–]\s*\d+\s*s\b"),
    re.compile(r"21\s*财经"),                                 # 媒体专名
    re.compile(r"Class\s*\d(?:\.\d)?", re.I),                 # IPC 等级标记
    re.compile(r"(?:IPC|IATF|ISO|AS|AEC|RO|FR|TM|PC|Q|FAQ|CNC|SMT|PTH|AOI|ENIG|OSP|HASL|mSAP|HDI|FPC|PI|PET|PP|PPS|CTE|Tg|Dk|Df)[\w\-\.]*", re.I),  # 标准/材料牌号/缩写代号
]
ENUM_RE = re.compile(r"^\s*(?:\d{1,2}|[一二三四五六七八九十]{1,3})[\.、）\)]\s*")

_RANGE_RE = re.compile(_RANGE)
_SINGLE_RE = re.compile(_SINGLE)
_RATIO_RE = re.compile(_RATIO)
_BARE_RE = re.compile(_BARE)

UNIT_ALIASES = {"um": "μm", "摄氏度": "℃", "％": "%", "s": "秒", "sqm": "平方米"}


def _norm_unit(u: str) -> str:
    u = u.strip()
    return UNIT_ALIASES.get(u, u)


def _mask(text: str) -> str:
    out = text
    for pat in MASK_PATTERNS:
        out = pat.sub(lambda m: "␣" * len(m.group(0)), out)
    return out


def extract_assertions(text: str, source_line: int = 0) -> list:
    """从文本抽取 (数值, 单位) 断言。

    返回元素: {num: float, unit: str, raw: str, kind: strict|counter|year|small,
              line: int, snippet: str}
    """
    results = []
    lines = text.splitlines()
    for i, line in enumerate(lines, start=1):
        lineno = source_line + i - 1 if source_line else i
        clean = ENUM_RE.sub("", line)
        masked = _mask(clean)
        _extract_line(masked, lineno, line.strip(), results)
    return results


def _add(results, num, unit, raw, lineno, snippet, force_kind=None):
    unit = _norm_unit(unit or "")
    if unit in COUNTER_UNITS:
        kind = "counter"
    elif unit == "年" or (not unit and 1900 <= num <= 2100):
        kind = "year"
        unit = unit or "年"
    elif not unit:
        kind = "small" if num <= 12 else "strict_bare"
    else:
        kind = "strict"
    if force_kind:
        kind = force_kind
    results.append({"num": float(num), "unit": unit, "raw": raw,
                    "kind": kind, "line": lineno, "snippet": snippet[:60]})


def _extract_line(masked: str, lineno: int, raw_line: str, results: list):
    consumed = []

    def overlaps(m):
        return any(not (m.end() <= s or m.start() >= e) for s, e in consumed)

    for m in _RATIO_RE.finditer(masked):
        for n in (m.group(1), m.group(2)):
            _add(results, float(n), m.group(3), m.group(0), lineno, raw_line)
        consumed.append((m.start(), m.end()))

    for m in _RANGE_RE.finditer(masked):
        if overlaps(m):
            continue
        unit = m.group(3)
        _add(results, float(m.group(1)), unit, m.group(0), lineno, raw_line)
        _add(results, float(m.group(2)), unit, m.group(0), lineno, raw_line)
        consumed.append((m.start(), m.end()))

    for m in _SINGLE_RE.finditer(masked):
        if overlaps(m):
            continue
        _add(results, float(m.group(1)), m.group(2), m.group(0), lineno, raw_line)
        consumed.append((m.start(), m.end()))

    for m in _BARE_RE.finditer(masked):
        if overlaps(m):
            continue
        n = float(m.group(1))
        rest = masked[m.end():m.end() + 2]
        nxt = rest.lstrip()[:1]
        if nxt and nxt in "个条点步种大名位款家次轮版句段页行项维":
            continue  # 结构性计数，直接忽略
        _add(results, n, "", m.group(1), lineno, raw_line)


# ---------- 注册表索引与比对 ----------

def build_index(assertions_per_fact: dict) -> dict:
    """assertions_per_fact: {fact_id: [assertion, ...]} → 匹配索引。"""
    strict = {}   # unit -> set(num)
    years = set()
    for fid, asserts in assertions_per_fact.items():
        for a in asserts:
            if a["kind"] == "strict":
                strict.setdefault(a["unit"], set()).add(round(a["num"], 4))
            elif a["kind"] == "strict_bare":
                strict.setdefault("", set()).add(round(a["num"], 4))
            elif a["kind"] == "year":
                years.add(int(a["num"]))
    return {"strict": strict, "years": years}


def check_assertions(assertions: list, index: dict, current_year: int = 2026) -> list:
    """对成稿断言逐条裁决。返回带 verdict 字段的新列表。"""
    out = []
    for a in assertions:
        verdict = "pass"
        note = ""
        if a["kind"] == "strict":
            if round(a["num"], 4) not in index["strict"].get(a["unit"], set()):
                verdict = "FAIL"
                note = f"未在事实注册表中找到 {a['raw'].strip()}"
        elif a["kind"] == "strict_bare":
            if round(a["num"], 4) not in index["strict"].get("", set()):
                verdict = "FAIL"
                note = f"无单位数字 {a['raw']} 未能溯源"
        elif a["kind"] == "year":
            if int(a["num"]) not in index["years"] and int(a["num"]) != current_year:
                verdict = "warn"
                note = f"年份 {int(a['num'])} 不在知识库已知年份中"
        elif a["kind"] == "counter":
            verdict = "pass"  # 结构性计数忽略
        elif a["kind"] == "small":
            verdict = "pass"
        out.append({**a, "verdict": verdict, "note": note})
    return out
