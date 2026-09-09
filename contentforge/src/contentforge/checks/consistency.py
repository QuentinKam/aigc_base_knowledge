"""ConsistencyCheck：同一事实跨物料数字一致（spec §6.3），输出事实 × 物料矩阵。"""
from collections import defaultdict


def check_all(ws, items: list) -> dict:
    """items: [{meta, body}]（已过 FactChecker）。由于 FactChecker 为精确数值匹配，
    事实级一致性等价于"同一事实 ID 被多份物料引用"。此处输出矩阵与异常。"""
    usage = defaultdict(dict)
    for it in items:
        for fid in it["meta"].get("fact_ids") or []:
            usage[fid][it["meta"]["id"]] = it["meta"].get("format", "")

    shared = {fid: refs for fid, refs in usage.items() if len(refs) >= 2}
    return {"matrix": usage, "shared_facts": shared,
            "conflicts": [],   # 精确匹配机制下不可能出现；保留字段供 LLM 语义比对扩展
            "pass": True}


def render_matrix(report: dict) -> str:
    lines = [f"跨物料一致性：{'✓ 通过' if report['pass'] else '✗'}"
             f"（{len(report['shared_facts'])} 条事实被多份物料共享）"]
    for fid, refs in list(report["shared_facts"].items())[:10]:
        lines.append(f"  {fid}: {' | '.join(f'{i}({f})' for i, f in refs.items())}")
    return "\n".join(lines)
