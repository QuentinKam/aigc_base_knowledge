"""P1 官网 FAQ 页（GEO 主战场）。LLM 路径见 base._llm_generate；本模块提供 mock 骨架稿。"""
import re


def _short_source(src: str) -> str:
    return re.sub(r"\.md$", "", src.split("/")[-1])


def mock(ctx) -> str:
    t, pack = ctx["topic"], ctx["pack"]
    faq_item = None
    if t.get("faq_ref"):
        faq_item = next((q for q in ctx["faq"] if q["id"] == t["faq_ref"]), None)

    if faq_item:
        title = faq_item["q"]
        direct = faq_item["a_direct"]
        rest = faq_item["a"]
        src_name = _short_source("04_FAQ/高频问答库.md")
    else:
        title = t["title"].rstrip("？?") + "？"
        top = next((f for f in pack if f["numbers"]), pack[0] if pack else None)
        direct = top["claim"] if top else t["title"]
        rest = "。".join(f["claim"] for f in pack[:3]) + "。"
        src_name = _short_source(top["kb_ref"].split(":")[0]) if top else "知识库"

    # 展开段：把答案余文按句分组
    sentences = [s for s in re.split(r"(?<=[。；])", rest.replace("\n", "")) if len(s.strip()) > 4]
    groups = [sentences[i:i + 2] for i in range(1, len(sentences), 2)][:3] or \
             [sentences[:2]] if sentences else []
    heads = ["是什么 / 有哪些", "关键变量", "实操建议"]

    out = [f"# {title}", ""]
    out += [f"**直接回答：** {direct}（来源：{src_name}）", ""]
    out += ["**展开：**", ""]
    if groups:
        for i, g in enumerate(groups):
            gh = heads[i] if i < len(heads) else f"展开{i + 1}"
            out += [f"### {gh}", "",
                    " ".join(x.strip() for x in g if x.strip()) + f"（来源：{src_name}）", ""]
    else:
        for f in pack[:3]:
            out += [f"### {f['claim'][:12]}", "", f["claim"] + f"。（来源：{_short_source(f['kb_ref'].split(':')[0])}）", ""]
    out += [f"**数据来源：** {src_name}（知识库，2025）", ""]
    out += [ctx["brand_sentence"], ""]
    return "\n".join(out)
