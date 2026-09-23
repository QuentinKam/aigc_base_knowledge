"""锚点违规自动回炉重生成（spec §6.1 兜底之二）。

流程：确定性验签 → 违规清单（机器生成）→ LLM 只修违规分句、逐字保留其余
→ 修复稿重跑「完整」确定性验签（防止改坏别处）→ 通过才覆盖原稿。

硬约束：
- 最多修 max_rounds 轮（默认 1），修不好转人工，不做多轮自我修复
- LLM 异常 = 修复失败，原稿保留，流水线不中断
- 修复失败时修复稿存 runs/<id>-repair<n>.md 供人工参考，不覆盖原文
- 每轮审计写入 front matter repairs（轮次/模型/前后失败数/规则/时间/结果）
"""
import re
from datetime import datetime
from pathlib import Path

from . import registry
from .checks import run_checks
from .checks.fact_checker import check_item
from .pipelines.base import dump_front_matter, factpack_text, load_item, load_meta, update_item

# 只有这五类违规属于「模型可自行修复」；anchor:unknown / anchor:scope（越权 ID）
# 多是事实包本身问题，回炉也修不对，直接转人工。
REPAIRABLE_RULES = {"anchor:bare", "anchor:value", "anchor:year",
                    "anchor:subject", "anchor:multi"}

_DOC_FENCE_RE = re.compile(r"^\s*```(?:markdown|md)?\s*(.*?)\s*```\s*$", re.S)

REPAIR_SYSTEM = """你是事实锚点文稿修复器。用户会给你一份未通过确定性校验的 Markdown 文稿和机器生成的违规清单。
硬性规则：
1. 只修复列出的违规分句：补上/改正事实 ID 锚点（形如〔F-017〕）、修正主体或年份使其与锚点事实一致、删除无法溯源的数字。
2. 其余所有文字逐字保留，禁止改写、删减、新增任何数字或事实。
3. ID 只能取自事实包第一列；一个数据分句只挂一个锚点；两个主体必须拆成两个分句各挂各的。
4. 直接输出修复后的完整 Markdown，不要解释，不要代码块包裹。"""


def _strip_doc_fence(text: str) -> str:
    m = _DOC_FENCE_RE.match(text.strip())
    return m.group(1).strip() if m else text.strip()


def _violations_text(failures: list) -> str:
    lines = []
    repairable = [f for f in failures if f["rule"] in REPAIRABLE_RULES]
    for n, f in enumerate(repairable, 1):
        loc = f"L{f['line']}" if f.get("line") else "?"
        lines.append(f"{n}. {loc} {f['rule']}：{f['msg']}\n   原句：{f.get('clause') or f.get('snippet', '')}")
    return "\n".join(lines)


def _build_repair_prompt(ws, item: dict, failures: list, files: list) -> str:
    meta = item["meta"]
    fmap = {f["id"]: f for f in registry.load_facts(ws)}
    pack = [fmap[i] for i in (meta.get("facts") or []) if i in fmap]
    return f"""【事实包】（ID | 断言 | 来源 | 年份；锚点只能引用这里的 ID）
{factpack_text(pack, files)}

【违规清单】（机器生成，只许修这些）
{_violations_text(failures)}

【待修复文稿】
{item['body']}"""


def _write_body(path: Path, item: dict, **meta_fields) -> None:
    meta = {**item["meta"], **meta_fields}
    path.write_text(dump_front_matter(meta) + "\n\n" + item["body"].strip() + "\n",
                    encoding="utf-8")


def repair_item(ws, item_path: Path, max_rounds: int = 1,
                chat_fn=None, chat_json_fn=None, use_classify: bool = True,
                threshold: float = 0.9, save_report: bool = True) -> dict:
    """对单份物料执行回炉修复。chat_fn(messages, temperature) -> str（注入便于测试）。

    返回 {outcome: fixed|still_failing|llm_error|nothing_to_repair|not_contract,
          report, audits, draft_path}。
    """
    path = Path(item_path)
    item = load_item(path)
    files = load_meta(ws)["files"]
    audits = list(item["meta"].get("repairs") or [])

    def envelope(fact_report):
        return {"id": item["meta"].get("id"), "format": item["meta"].get("format", ""),
                "status": item["meta"].get("status", ""),
                "fact": fact_report, "geo": {"failures": [], "warnings": []}}

    # 先纯确定性预检：非契约稿 / 无违规 / 只有不可修复违规时直接返回，不要求 API key
    before = check_item(item, ws, llm_assist=False, chat_json_fn=None)
    if before["mode"] != "anchor":
        return {"outcome": "not_contract", "report": envelope(before), "audits": audits,
                "draft_path": None}
    if not before["failures"]:
        return {"outcome": "nothing_to_repair", "report": envelope(before), "audits": audits,
                "draft_path": None}
    if not any(f["rule"] in REPAIRABLE_RULES for f in before["failures"]):
        return {"outcome": "nothing_to_repair", "report": envelope(before), "audits": audits,
                "draft_path": None}

    # 确有可修复违规才绑定 LLM
    model = ""
    if chat_fn is None:
        from . import llm
        from .config import llm_config
        cfg = llm_config()
        if not cfg["has_key"]:
            raise SystemExit("未配置 API key：无法执行 LLM 回炉（设置 CF_API_KEY 或 llm.json）")
        model = cfg["model"]
        chat_fn = lambda messages, temperature=0.2: llm.chat(cfg, messages, temperature)
        chat_json_fn = lambda messages: llm.chat_json(cfg, messages)
    before = check_item(item, ws, llm_assist=use_classify, chat_json_fn=chat_json_fn,
                        threshold=threshold, model=model)

    outcome, draft_path = "still_failing", None
    for round_n in range(1, max_rounds + 1):
        rules = sorted({f["rule"] for f in before["failures"] if f["rule"] in REPAIRABLE_RULES})
        n_before = len(before["failures"])
        try:
            fixed = _strip_doc_fence(chat_fn(
                [{"role": "system", "content": REPAIR_SYSTEM},
                 {"role": "user", "content": _build_repair_prompt(ws, item, before["failures"], files)}],
                0.2))
        except Exception as e:                              # noqa: BLE001
            audit = {"round": round_n, "model": model, "failures_before": n_before,
                     "failures_after": n_before, "rules": rules,
                     "ts": datetime.now().isoformat(timespec="seconds"),
                     "outcome": "llm_error", "error": str(e)[:120]}
            audits.append(audit)
            update_item(path, repairs=audits)
            return {"outcome": "llm_error", "report": envelope(before), "audits": audits,
                    "draft_path": None}

        cand = {**item, "body": fixed}
        after = check_item(cand, ws, llm_assist=use_classify, chat_json_fn=chat_json_fn,
                           threshold=threshold, model=model)
        audit = {"round": round_n, "model": model, "failures_before": n_before,
                 "failures_after": len(after["failures"]), "rules": rules,
                 "ts": datetime.now().isoformat(timespec="seconds"),
                 "outcome": "fixed" if not after["failures"] else "still_failing"}
        audits.append(audit)

        if not after["failures"]:
            item["body"] = fixed
            _write_body(path, item, repairs=audits)
            report = run_checks(ws, path, save_report=save_report,
                                llm_assist=use_classify, chat_json_fn=chat_json_fn,
                                threshold=threshold, model=model)
            return {"outcome": "fixed", "report": report, "audits": audits,
                    "draft_path": None}

        # 仍失败：修复稿存 runs/ 供人工参考，原稿不动
        runs_dir = Path(ws["dir"]) / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        draft_path = runs_dir / f"{item['meta']['id']}-repair{round_n}.md"
        draft_path.write_text(fixed + "\n", encoding="utf-8")
        before = after

    update_item(path, repairs=audits)
    return {"outcome": outcome, "report": envelope(before), "audits": audits,
            "draft_path": str(draft_path) if draft_path else None}
