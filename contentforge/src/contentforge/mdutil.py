"""轻量 Markdown 解析：表格 / 章节 / fenced 块 / FAQ 问答块。标准库实现。"""
import re
from pathlib import Path

TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
SEP_ROW_RE = re.compile(r"^\s*\|[\s:\-|]+\|\s*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_RE = re.compile(r"^```")
QA_TITLE_RE = re.compile(r"^\*\*(Q\d+)[：:]\s*(.+?)\*\*\s*$")
BULLET_RE = re.compile(r"^\s*(?:[-*]|\d{1,2}[\.、)]|（?\d{1,2}）?)\s*(.+)$")


def read(md_path) -> str:
    return Path(md_path).read_text(encoding="utf-8")


def parse_tables(text: str) -> list:
    """返回 [{header: [cells], rows: [[cells]], line: int}]"""
    tables, cur_header, cur_rows, cur_line = [], None, [], 0
    lines = text.splitlines()
    for i, line in enumerate(lines, start=1):
        m = TABLE_ROW_RE.match(line)
        if not m:
            if cur_header:
                tables.append({"header": cur_header, "rows": cur_rows, "line": cur_line})
                cur_header, cur_rows = None, []
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if SEP_ROW_RE.match(line):
            continue
        if cur_header is None:
            cur_header, cur_rows, cur_line = cells, [], i
        else:
            cur_rows.append(cells)
    if cur_header:
        tables.append({"header": cur_header, "rows": cur_rows, "line": cur_line})
    return tables


def parse_sections(text: str) -> list:
    """返回 [{level, title, line, text}]，text 为该章节正文（含子级）。
    fenced 代码块内的 # 行不视为标题。"""
    sections, cur = [], None
    lines = text.splitlines()
    in_fence = False
    for i, line in enumerate(lines, start=1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            if cur and not in_fence:
                pass
        m = HEADING_RE.match(line) if not in_fence else None
        if m:
            if cur:
                cur["text"] = "\n".join(lines[cur["line"]:i - 1])
                sections.append(cur)
            cur = {"level": len(m.group(1)), "title": m.group(2).strip(),
                   "line": i, "text": ""}
    if cur:
        cur["text"] = "\n".join(lines[cur["line"]:])
        sections.append(cur)
    return sections


def parse_fenced_blocks(text: str) -> list:
    """返回 [{lang, body, line}]"""
    blocks, inside, buf, lang, start = [], False, [], "", 0
    for i, line in enumerate(text.splitlines(), start=1):
        if FENCE_RE.match(line):
            if inside:
                blocks.append({"lang": lang, "body": "\n".join(buf), "line": start})
                inside, buf = False, []
            else:
                inside, lang, start = True, line[3:].strip(), i
        elif inside:
            buf.append(line)
    return blocks


def parse_qa_blocks(text: str) -> list:
    """解析 **Qn：...** / A：... 问答块（知识库 04 格式）。"""
    items = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = QA_TITLE_RE.match(lines[i])
        if m:
            qid, q = m.group(1), m.group(2).strip()
            i += 1
            answer_lines = []
            while i < len(lines) and lines[i].strip() and not QA_TITLE_RE.match(lines[i]) \
                    and not HEADING_RE.match(lines[i]) and not lines[i].startswith("---"):
                answer_lines.append(lines[i])
                i += 1
            a_full = "\n".join(answer_lines).strip()
            a_full = re.sub(r"^A[：:]\s*", "", a_full)  # 知识库答案行带 A： 前缀
            if a_full:
                items.append({"id": qid, "q": q, "a": a_full, "line": 0})
            continue
        i += 1
    for it in items:
        for i, line in enumerate(lines, start=1):
            if f"**{it['id']}：" in line or f"**{it['id']}:" in line:
                it["line"] = i
                break
    return items


def bullets(text: str) -> list:
    """抽取列表项（含行号与原文）。"""
    out = []
    for i, line in enumerate(text.splitlines(), start=1):
        m = BULLET_RE.match(line)
        if m and not line.lstrip().startswith("|") and not HEADING_RE.match(line):
            out.append({"text": m.group(1).strip(), "line": i, "raw": line.rstrip()})
    return out


def first_sentence(text: str) -> str:
    t = re.sub(r"\s+", "", text)
    for i, ch in enumerate(t):
        if ch in "。！？!?":
            return t[:i + 1]
    return t
