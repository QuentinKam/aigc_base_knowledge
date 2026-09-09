"""P4 行业数据长文：核心数据表 + 判断 + 动作建议 + 来源列表。AI 引用率最高的形态。"""


def mock(ctx) -> str:
    t, pack = ctx["topic"], ctx["pack"]
    market = [f for f in pack if f["cat"] == "market_data"] or pack[:5]
    others = [f for f in pack if f not in market][:4]

    out = [f"# {t['title']}", ""]
    out += ["## 核心数据", "",
            "| 数据 | 数值 | 来源 | 时间 |", "|------|------|------|------|"]
    for f in market[:6]:
        name, _, value = f["claim"].partition("：")
        out.append(f"| {name} | {value or name} | {f['source']} | {f.get('year') or ''} |")
    out += ["", "## 数据说明了什么", ""]
    for i, f in enumerate(others[:3], 1):
        src = f"（{f['source']}，{f['year']}）" if f.get("year") else f"（来源：{_src(f)}）"
        out += [f"### 判断{'一二三'[i - 1]}", "", f["claim"].replace("**", "") + "。" + src, ""]
    if not others:
        out += ["### 结构性增长", "", "增量集中在高多层板、HDI 与 IC 载板等高附加值品类。", ""]
    advice = _material_bullets(ctx)[:3]
    out += ["## 对采购/工程师意味着什么", ""]
    for a in advice:
        out.append(f"- {a}")
    if not advice:
        out.append("- 把市场增量方向转化为选型语言：层数、材料等级、验收标准写进询价单。")
    out += ["", ctx["brand_sentence"], "", "## 来源列表", ""]
    for s in dict.fromkeys(f["source"] for f in market):
        out.append(f"- {s}")
    out.append("")
    return "\n".join(out)


def _src(f):
    return f["source"].split("/")[-1].replace(".md", "")


def _material_bullets(ctx):
    out = []
    for line in ctx["material"].splitlines():
        if line.startswith("- "):
            out.append(line[2:].strip())
    return out
