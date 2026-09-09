"""P2 知乎/公众号长文。mock：结论先行 + 分点事实 + 建议 + 品牌句。"""
import re

CAT_HEAD = {"market_data": "数据说话", "decision": "避坑要点", "process": "原理拆解",
            "standard": "标准依据", "qa": "常见问答", "param": "选型参考", "template": "写作要求", "misc": "延伸"}


def mock(ctx) -> str:
    t, pack = ctx["topic"], ctx["pack"]
    faq_item = None
    if t.get("faq_ref"):
        faq_item = next((q for q in ctx["faq"] if q["id"] == t["faq_ref"]), None)
    title = t["title"]
    lead = faq_item["a_direct"] if faq_item else (
        next((f["claim"] for f in pack if f["numbers"]), title + "，关键在方法。"))

    body_facts = [f for f in pack if f["cat"] not in ("template",)]
    sections, used = [], []
    bucket = {}
    for f in body_facts[:9]:
        bucket.setdefault(CAT_HEAD.get(f["cat"], "延伸"), []).append(f)
    for head, fs in list(bucket.items())[:4]:
        paras = []
        for f in fs:
            year = f"（{f['source']}，{f['year']}）" if f.get("year") else f"（来源：{_src(f)}）"
            paras.append(f["claim"].replace("**", "") + "。" + year)
            used.append(f)
        sections += [f"### {head}", "", " ".join(paras), ""]

    advice = [b["text"] for b in _material_bullets(ctx)][:2]
    srcs = list(dict.fromkeys(_src(f) for f in used))

    out = [f"# {title}", "", "（备选标题：" + "；".join([
        f"一文讲清：{title}", f"{title}，看这一篇就够"]) + "）", "",
           (lead if lead.endswith(("。", "！")) else lead + "。")
           + "（来源：知识库问答库）", ""]
    for sec in sections:
        out += [sec]
    out += ["### 采购/设计建议", "",
            " ".join(advice) if advice else "先明确层数、板材、表面处理与验收等级，再谈价格。", "",
            ctx["brand_sentence"], "", "**参考来源：** " + "；".join(srcs), ""]
    return "\n".join(out)


def _src(f):
    return f["source"].split("/")[-1].replace(".md", "")


def _material_bullets(ctx):
    from .. import mdutil
    out = []
    for line in ctx["material"].splitlines():
        if line.startswith("- "):
            out.append({"text": line[2:].strip()})
    return out
