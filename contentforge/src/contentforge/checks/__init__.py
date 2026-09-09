"""质量门禁（spec §6）：FactChecker / GEOChecker / ConsistencyCheck。"""
import json
from pathlib import Path

from . import fact_checker, geo_checker, consistency


def run_checks(ws, item_path: Path, save_report: bool = True) -> dict:
    """对单份物料跑 fact + geo 检查，更新状态机与检查报告。"""
    from ..pipelines.base import load_item, update_item
    from ..registry import build_check_index

    item = load_item(item_path)
    fact_r = fact_checker.check_item(item, ws)
    geo_r = geo_checker.check_item(item, ws)

    checks = {"fact": "pass" if not fact_r["failures"] else "fail",
              "geo": "pass" if not geo_r["failures"] else "fail"}
    if checks["fact"] == "fail":
        status = "generated"
    elif checks["geo"] == "fail":
        status = "fact_pass"
    else:
        status = "geo_pass"
    update_item(item_path,
                status=status, checks=checks,
                fact_ids=fact_r["matched_ids"],
                gaps=fact_r["gaps"])

    report = {"id": item["meta"]["id"], "format": item["meta"]["format"],
              "status": status,
              "fact": fact_r, "geo": geo_r}
    if save_report:
        runs = Path(ws["dir"]) / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        (runs / f"{item['meta']['id']}-check.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def print_report(r: dict) -> str:
    lines = [f"[{r['id']}] format={r['format']} → 状态 {r['status']}"]
    f, g = r["fact"], r["geo"]
    lines.append(f"  FactChecker: {'✓' if not f['failures'] else '✗ FAIL'}"
                 f"（断言 {f['total']}，溯源失败 {len(f['failures'])}，告警 {len(f['warnings'])}，数据缺口 {len(f['gaps'])}）")
    for x in f["failures"][:8]:
        lines.append(f"    ✗ L{x['line']} {x['note']}｜「{x['snippet']}」")
    for x in f["warnings"][:5]:
        lines.append(f"    ⚠ L{x['line']} {x['note']}")
    for gp in f["gaps"][:5]:
        lines.append(f"    ◇ 数据缺口标记：{gp}")
    lines.append(f"  GEOChecker: {'✓' if not g['failures'] else '✗ FAIL'}"
                 f"（失败 {len(g['failures'])}，告警 {len(g['warnings'])}）")
    for x in g["failures"][:8]:
        lines.append(f"    ✗ [{x['rule']}] {x['msg']}")
    for x in g["warnings"][:5]:
        lines.append(f"    ⚠ [{x['rule']}] {x['msg']}")
    return "\n".join(lines)


__all__ = ["run_checks", "print_report", "fact_checker", "geo_checker", "consistency"]
