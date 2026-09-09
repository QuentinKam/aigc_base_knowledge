"""P3 短视频物料包：口播稿 + 钩子 + 分镜 + 封面标题 + 发布文案 + 拍摄清单。"""


def mock(ctx) -> str:
    t, pack = ctx["topic"], ctx["pack"]
    faq_item = None
    if t.get("faq_ref"):
        faq_item = next((q for q in ctx["faq"] if q["id"] == t["faq_ref"]), None)
    title = t["title"]
    question = title if title.endswith(("？", "?")) else title + "？"

    # 答案要点：优先 FAQ 直接答案，否则取前 3 条事实（截短）
    if faq_item:
        lead = faq_item["a_direct"]
        points = _split_sentences(faq_item["a"])[:3]
    else:
        lead = next((f["claim"] for f in pack if f["numbers"]), title)
        points = [f["claim"] for f in pack if f["numbers"]][:3]

    top_fact = next((f for f in pack if f["numbers"] and f["cat"] == "market_data"),
                    pack[0] if pack else None)
    hook3 = f"{top_fact['claim'].split('：')[0]}，很多采购都理解错了" if top_fact else f"{question}"

    scenes = [("0-3s", "板子特写 + 大字幕抛问题", question),
              ("3-20s", "字幕卡逐条出要点", lead)]
    for i, p in enumerate(points, 1):
        scenes.append((f"{18 + i * 15}-33s", _visual(i), p))
    scenes.append(("70-90s", "厂家实拍 + 品牌字幕", ctx["brand_sentence"]))

    out = [f"# 短视频物料包｜{title}", ""]
    out += ["## 钩子备选", "",
            f"1. {question}",
            "2. 同样是打样，报价为什么能差出一个数量级？",
            f"3. {hook3}", ""]
    src = "（来源：知识库问答库）"
    out += ["## 口播稿（60-90 秒）", ""]
    out += [f"[0-3s] 钩子：{question}", ""]
    out += [f"[3-20s] 直接给答案：{lead}{src}", ""]
    for i, p in enumerate(points, 1):
        out += [f"[20-70s] 第{'一二三'[i - 1]}点：{p}{src}（画面：{_visual(i)}）", ""]
    out += [f"[70-90s] {ctx['brand_sentence']} 关注我，每周拆解 PCB 采购与工艺的硬知识。", ""]
    out += ["## 分镜表", "",
            "| 镜号 | 时间 | 画面/B-roll 建议 | 口播句 | 字幕 |",
            "|------|------|------------------|--------|------|"]
    for i, (time_, visual, spoken) in enumerate(scenes, 1):
        sub = spoken if len(spoken) <= 18 else spoken[:15] + "…"
        out.append(f"| {i} | {time_} | {visual} | {spoken[:40]} | {sub} |")
    out += ["", "## 封面与标题", "",
            f"- 封面文案：{_cover(title)}",
            f"- 视频标题：{question}", ""]
    out += ["## 发布文案", "",
            f"抖音版：{question} 一条视频讲清楚。#PCB #电路板 #电子制造 #采购避坑",
            "",
            "视频号版：打样的价格与交期门道，一条视频看懂。#PCB打样 #硬件工程师", ""]
    out += ["## 拍摄清单", "",
            "- PCB 成品板特写（正反面、边缘细节）",
            "- 车间/产线画面（钻孔、阻焊印刷）",
            "- 字幕卡（要点逐条）",
            "- 数据图卡（引用数据做成大字版）", ""]
    return "\n".join(out)


def _split_sentences(text: str) -> list:
    import re
    s = [x.strip() for x in re.split(r"(?<=[。！？])", text.replace("\n", "")) if len(x.strip()) > 6]
    return [x[:60] for x in s]


def _visual(i: int) -> str:
    return ["拆解动画/板材叠层示意", "车间工序实拍", "对比图（好板 vs 问题板）"][i - 1] if i <= 3 else "数据字幕卡"


def _cover(title: str) -> str:
    t = title.replace("PCB", "").strip("？?：: ")
    return (t[:8] + "，一次讲清")[:12]
