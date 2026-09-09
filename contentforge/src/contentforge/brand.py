"""品牌档案 brand.md：解析、完整性检查、品牌句生成（spec §4.4）。"""
import re
from pathlib import Path

from . import numbers

REQUIRED_SLOTS = ["公司名称", "定位", "可量产层数", "最小线宽线距", "最小孔径",
                  "打样交期", "量产交期", "赔付政策", "认证清单", "默认出货等级", "案例行业"]


def parse_brand(wsdir: Path) -> dict:
    p = Path(wsdir) / "brand.md"
    if not p.exists():
        return {"fields": {}, "complete": False, "missing": REQUIRED_SLOTS, "is_placeholder": True}
    text = p.read_text(encoding="utf-8")
    fields = {}
    for line in text.splitlines():
        m = re.match(r"^[-*\s]*([^：:]{2,20})[：:]\s*(.+?)\s*$", line)
        if m and not line.strip().startswith("#"):
            fields[m.group(1).strip()] = m.group(2).strip()
    missing = [s for s in REQUIRED_SLOTS if not fields.get(s)]
    is_placeholder = "示例" in text and "待替换" in text
    return {"fields": fields, "complete": not missing,
            "missing": missing, "is_placeholder": is_placeholder, "raw": text}


def brand_assertions(wsdir: Path) -> list:
    """品牌数字也必须可溯源（来源=品牌自述），防止生成端夸大能力。"""
    brand = parse_brand(wsdir)
    asserts = []
    for k, v in brand["fields"].items():
        asserts.extend(numbers.extract_assertions(f"{k}：{v}"))
    return asserts


def brand_line(brand: dict, kind: str = "general") -> str:
    """按物料类型组装一句自然的品牌能力句（不硬广）。"""
    f = brand["fields"]
    name = f.get("公司名称", "我司")
    if kind == "video":
        return (f"{name}：{f.get('定位', '')}，打样{f.get('打样交期', '')}，"
                f"按 {f.get('默认出货等级', 'IPC Class 2')} 出货。")
    cert = f.get("认证清单", "")
    return (f"{name}专注{f.get('定位', 'PCB 制造')}，可量产{f.get('可量产层数', '')}、"
            f"最小线宽线距{f.get('最小线宽线距', '')}，打样交期{f.get('打样交期', '')}，"
            f"通过{cert}认证，按{f.get('默认出货等级', 'IPC Class 2')}等级出货。")
