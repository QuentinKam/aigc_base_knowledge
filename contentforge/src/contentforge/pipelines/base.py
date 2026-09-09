"""流水线基座：上下文组装、fact pack、生成、落盘（spec §4.3、§5）。"""
import json
import re
from datetime import date
from pathlib import Path

from .. import registry, mdutil
from ..brand import parse_brand, brand_line

STATUSES = ["generated", "fact_pass", "geo_pass", "approved", "published"]
FORMATS = ["faq_page", "article", "video", "data_article"]
FORMAT_LABEL = {"faq_page": "官网 FAQ 页", "article": "知乎/公众号长文",
                "video": "短视频物料包", "data_article": "行业数据长文"}

# 写入 system prompt 的第一道防线（spec §5 模型约束）
SYSTEM_CONSTRAINT = """你是 B2B 行业内容工程师，负责把知识库事实改写成面向采购/工程师的发布内容。硬性规则：
1. 只能使用【事实包】中的数据（数字、价格、时长、占比、参数、标准编号、认证名）。事实包中没有的数据，一律原样写 [数据缺口：需要XX]，禁止编造，禁止使用你记忆中的任何数字。
2. 【知识素材】中的观点与方法可以转述，但不得引入其中出现过的数字之外的新数字。
3. 品牌信息只能来自【品牌档案】，且只在指定位置出现一次；禁止"最好/第一/顶级/行业领先/绝对"等夸大词，不硬广。
4. 引用数据时在句末标注（来源，年份），来源与年份必须照抄事实包。
5. 直接输出正文 Markdown，不要任何解释、不要代码块包裹。"""


def load_meta(ws) -> dict:
    d = Path(ws["dir"])
    return {
        "facts": registry.load_facts(ws),
        "faq": registry.load_json(d, "kbmeta/faq.json", {}).get("items", []),
        "templates": registry.load_json(d, "kbmeta/templates.json", {}).get("templates", {}),
        "rules": registry.load_json(d, "kbmeta/rules.json", {}),
        "files": registry.load_json(d, "kbmeta/files.json", {}).get("files", []),
    }


def find_topic(ws, topic_id: str) -> dict:
    topics = registry.load_json(Path(ws["dir"]), "topics.json", {}).get("topics", [])
    for t in topics:
        if t["id"] == topic_id:
            return t
    raise SystemExit(f"选题不存在：{topic_id}（topic list 查看）")


def resolve_kb_files(ws, topic) -> list:
    """把选题 kb_refs（'01'、'01/PCB类型与板材'、'04_'）解析成实际文件路径。"""
    kb = Path(ws["kb_path"])
    out = []
    for ref in topic.get("kb_refs") or []:
        p = kb / ref
        if p.is_file():
            out.append(p)
            continue
        matches = [f for f in kb.rglob("*.md")
                   if str(f.relative_to(kb)).startswith(ref) or f.stem.startswith(ref)]
        out.extend(matches[:2])
    return list(dict.fromkeys(out))[:3]


def build_factpack(topic, facts, faq_items, cap: int = 30) -> list:
    """选题相关事实：FAQ 关联 > 素材目录匹配 > 标题关键词重叠。"""
    selected, seen = [], set()

    def take(fs):
        for f in fs:
            if f["id"] not in seen:
                seen.add(f["id"])
                selected.append(f)

    if topic.get("faq_ref"):
        take([f for f in facts if f["cat"] == "qa"
              and f["claim"].startswith(f"FAQ {topic['faq_ref']} ")])
    take(registry.facts_for_kb_refs(facts, topic.get("kb_refs")))
    # 关键词兜底：选题标题里的 2 字词命中事实断言
    kws = [w for w in re.findall(r"[\u4e00-\u9fff]{2,4}", topic["title"])][:8]
    scored = []
    for f in facts:
        s = sum(1 for w in kws if w in f["claim"])
        if s:
            scored.append((s, f))
    take([f for _, f in sorted(scored, key=lambda x: -x[0])])
    return selected[:cap]


def build_material(ws, topic) -> str:
    """知识素材块：kb_ref 文件的摘要 + 定性列表内容（数字已尽入事实包）。"""
    parts = []
    for p in resolve_kb_files(ws, topic):
        text = mdutil.read(p)
        m = re.search(r"^>\s*摘要[：:]\s*(.+)$", text, re.M)
        lines = []
        if m:
            lines.append(f"摘要：{m.group(1)}")
        for b in mdutil.bullets(text):
            t = b["text"]
            if "http" in t or len(t) > 150 or any(ch.isdigit() for ch in t):
                continue
            lines.append(f"- {t}")
        parts.append(f"◆ 素材《{p.stem}》\n" + "\n".join(lines[:18]))
    return "\n\n".join(parts) or "（无）"


def factpack_text(pack) -> str:
    rows = []
    for f in pack:
        year = f.get("year") or ""
        rows.append(f"{f['id']} | {f['claim']} | 来源：{f['source']} | {year}")
    return "\n".join(rows) or "（无）"


def next_content_id(wsdir: Path) -> str:
    content = Path(wsdir) / "content"
    ids = []
    for p in content.glob("C-*.md"):
        m = re.match(r"C-(\d{4})", p.stem)
        if m:
            ids.append(int(m.group(1)))
    return f"C-{max(ids or [0]) + 1:04d}"


def dump_front_matter(meta: dict) -> str:
    def fmt(v):
        if isinstance(v, list):
            return "[" + ", ".join(json.dumps(x, ensure_ascii=False) for x in v) + "]"
        if v is None:
            return ""
        if isinstance(v, bool):
            return "true" if v else "false"
        return json.dumps(v, ensure_ascii=False)
    lines = ["---"]
    for k, v in meta.items():
        lines.append(f"{k}: {fmt(v)}")
    lines.append("---")
    return "\n".join(lines)


def parse_front_matter(text: str) -> tuple:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return {}, text
    meta, body = {}, m.group(2)
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        v = v.strip()
        if (v.startswith("[") and v.endswith("]")) or (v.startswith("{") and v.endswith("}")):
            try:
                meta[k] = json.loads(v.replace("'", '"'))
                continue
            except json.JSONDecodeError:
                pass
        if v in ("true", "false"):
            meta[k] = v == "true"
        elif v == "":
            meta[k] = None
        else:
            meta[k] = v.strip('"')
    return meta, body


def load_item(path: Path) -> dict:
    meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
    return {"path": path, "meta": meta, "body": body}


def save_item(ws, item_id: str, topic: dict, fmt: str, body: str,
              facts_ids: list, model: str, brand_status: str, extra: dict = None) -> Path:
    wsdir = Path(ws["dir"])
    meta = {
        "id": item_id,
        "topic": topic["id"],
        "format": fmt,
        "platform": topic["platforms"][0] if topic.get("platforms") else "site",
        "title": topic["title"],
        "status": "generated",
        "facts": facts_ids,
        "gaps": [],
        "checks": {"fact": "pending", "geo": "pending", "consistency": "pending"},
        "model": model,
        "brand_status": brand_status,
        "generated_at": date.today().isoformat(),
    }
    if extra:
        meta.update(extra)
    path = wsdir / "content" / f"{item_id}.md"
    path.write_text(dump_front_matter(meta) + "\n\n" + body.strip() + "\n", encoding="utf-8")
    return path


def update_item(path: Path, **fields) -> dict:
    item = load_item(path)
    meta = {**item["meta"], **fields}
    path.write_text(dump_front_matter(meta) + "\n\n" + item["body"], encoding="utf-8")
    return meta


def generate_one(ws, topic, fmt: str, meta_ctx: dict, use_llm: bool, llm_cfg: dict) -> Path:
    """生成一份物料：组装上下文 → LLM/mock → 落盘。"""
    from . import p1_faq, p2_article, p3_video, p4_data
    wsdir = Path(ws["dir"])
    brand = parse_brand(wsdir)
    pack = build_factpack(topic, meta_ctx["facts"], meta_ctx["faq"])
    material = build_material(ws, topic)
    ctx = {
        "ws": ws, "topic": topic, "fmt": fmt, "pack": pack, "material": material,
        "brand": brand, "faq": meta_ctx["faq"], "templates": meta_ctx["templates"],
        "rules": meta_ctx["rules"], "brand_sentence": brand_line(brand, "video" if fmt == "video" else "general"),
    }
    if use_llm:
        body = _llm_generate(ctx, llm_cfg)
        model = llm_cfg["model"]
    else:
        mod = {"faq_page": p1_faq, "article": p2_article,
               "video": p3_video, "data_article": p4_data}[fmt]
        body = mod.mock(ctx)
        model = "mock-skeleton"
    item_id = next_content_id(wsdir)
    return save_item(ws, item_id, topic, fmt, body,
                     facts_ids=[f["id"] for f in pack], model=model,
                     brand_status="ok" if brand["complete"] else "incomplete",
                     extra={"gaps": re.findall(r"\[数据缺口[：:][^\]]*\]", body)})


def _llm_generate(ctx, llm_cfg) -> str:
    from .. import llm
    t, fmt = ctx["topic"], ctx["fmt"]
    structure = ctx["templates"].get(fmt, {}).get("structure", "")
    user = f"""【选题】{t['title']}
【目标受众】{t.get('audience', '采购/研发工程师')}
【目标平台】{', '.join(t.get('platforms', []))}
【事实包】（唯一合法数据来源，格式 ID | 断言 | 来源 | 年份）
{factpack_text(ctx['pack'])}

【知识素材】（可转述观点，不得新增数字）
{ctx['material']}

【品牌档案】
{ctx['brand_sentence']}

【结构要求】（严格遵循）
{structure}

【输出要求】
{_format_requirements(fmt)}"""
    return llm.chat(llm_cfg, [{"role": "system", "content": SYSTEM_CONSTRAINT},
                              {"role": "user", "content": user}])


def _format_requirements(fmt: str) -> str:
    if fmt == "faq_page":
        return ("一问一页。H1 标题用用户真实提问原句；'**直接回答**'块 1-2 句、首句即完整答案并含具体数字或标准；"
                "展开 3-5 段带 ### 小标题；末尾'**数据来源：**'列出年份+机构。")
    if fmt == "article":
        return ("首句直接给结论（禁止铺垫）；3-4 个分点，每点 ### 小标题 + 数据支撑；"
                "倒数第二段一句采购/设计建议；最后一段品牌能力句（用品牌档案，一句即可）；"
                "文末'**参考来源：**'列表。开头给出 3 个候选标题（# 主标题 + '备选标题：'行）。")
    if fmt == "video":
        return ("输出短视频物料包，必须包含以下小节（## 级）：\n"
                "## 钩子备选（3 个，每个一句）\n## 口播稿（60-90 秒）—— 按 [0-3s]/[3-20s]/[20-70s]/[70-90s] 时间轴逐句，总字数 240-360 字\n"
                "## 分镜表 —— Markdown 表格：镜号|时间|画面/B-roll 建议|口播句|字幕\n"
                "## 封面与标题\n## 发布文案（抖音版/视频号版 + 话题标签）\n## 拍摄清单")
    if fmt == "data_article":
        return ("标题=数字+观点；开篇核心数据 3-5 个（全部来自事实包，句末注明来源年份）；"
                "中段 2-3 个判断（### 小标题）；落到'对采购/工程师意味着什么'的动作建议；"
                "文末'**来源列表**'。")
    return ""
