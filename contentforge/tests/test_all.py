"""单元测试：数字抽取 / 防编造（验收 A3）/ 年份 / 一致性（A5）。
运行：cd contentforge && python3 -m unittest tests.test_all -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from contentforge import numbers
from contentforge.numbers import extract_assertions, build_index, check_assertions


def pairs(text):
    return [(a["num"], a["unit"]) for a in extract_assertions(text)]


class TestExtraction(unittest.TestCase):
    def test_market_numbers(self):
        ps = pairs("2025 年全球 PCB 产值约 851.52 亿美元，同比 +15.8%")
        self.assertIn((851.52, "亿美元"), ps)
        self.assertIn((15.8, "%"), ps)

    def test_ranges(self):
        ps = pairs("常规交期 3-7 天，加急上浮 30%-100%，量产 2-4 周")
        self.assertIn((3.0, "天"), ps)
        self.assertIn((7.0, "天"), ps)
        self.assertIn((30.0, "%"), ps)
        self.assertIn((100.0, "%"), ps)
        self.assertIn((2.0, "周"), ps)

    def test_params(self):
        ps = pairs("孔径通常 ≤0.15mm，线宽 3/3mil，高 Tg ≥170℃")
        self.assertIn((0.15, "mm"), ps)
        self.assertIn((3.0, "mil"), ps)
        self.assertIn((170.0, "℃"), ps)

    def test_masks(self):
        self.assertEqual([p for p in pairs("2026-09-05 发布 [0-3s] 钩子，来源 21 财经")], [])
        self.assertEqual([p for p in pairs("按 IPC-A-600 Class 2 验收，FR-4 基材")], [])

    def test_counters_and_small(self):
        kinds = {a["kind"] for a in extract_assertions("3 个要点，5 层板")}
        self.assertIn("counter", kinds)
        self.assertIn("strict", kinds)   # 层 是严格单位


class TestAntiFabrication(unittest.TestCase):
    """验收 A3：成稿出现注册表之外的数字必须 FAIL。"""

    def setUp(self):
        fact_asserts = extract_assertions("2025 年全球 PCB 产值约 851.52 亿美元，同比 +15.8%")
        self.index = build_index({"F-001": fact_asserts})

    def test_registered_number_passes(self):
        checked = check_assertions(extract_assertions("2025 年全球 PCB 产值约 851.52 亿美元（Prismark，2025）"),
                                    self.index)
        self.assertTrue(all(a["verdict"] == "pass" for a in checked))

    def test_fabricated_number_fails(self):
        checked = check_assertions(extract_assertions("2025 年市场规模达 1000 亿美元，同比增长 20%"),
                                   self.index)
        fails = [a for a in checked if a["verdict"] == "FAIL"]
        self.assertEqual({a["num"] for a in fails}, {1000.0, 20.0})

    def test_slightly_rounded_fails(self):
        checked = check_assertions(extract_assertions("产值约 851.5 亿美元"), self.index)
        self.assertTrue(any(a["verdict"] == "FAIL" for a in checked))

    def test_counter_words_ignored(self):
        checked = check_assertions(extract_assertions("下面给 3 个要点"), self.index)
        self.assertTrue(all(a["verdict"] == "pass" for a in checked))


class TestConsistency(unittest.TestCase):
    """验收 A5：同一事实跨物料共享，矩阵输出。"""

    def test_matrix(self):
        from contentforge.checks.consistency import check_all
        items = [{"meta": {"id": "C-0001", "format": "faq_page", "fact_ids": ["F-016"]}, "body": ""},
                 {"meta": {"id": "C-0002", "format": "article", "fact_ids": ["F-016"]}, "body": ""}]
        r = check_all(None, items)
        self.assertTrue(r["pass"])
        self.assertIn("F-016", r["shared_facts"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
