"""单元测试：数字抽取 / 防编造（验收 A3）/ 年份 / 一致性（A5）。
运行：cd contentforge && python3 -m unittest tests.test_all -v
"""
import json
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


class TestProductionSections(unittest.TestCase):
    """视频物料的「分镜表/拍摄清单」是拍摄执行指令，其中的画面示意数字与道具数量不参与溯源。"""

    def setUp(self):
        from contentforge.config import load_workspace
        self.ws = load_workspace("pcb")

    def test_storyboard_and_props_ignored(self):
        from contentforge.checks.fact_checker import check_item
        body = ("## 口播稿\n\nPCB 打样 50 块和 500 块的板，差别在哪？\n\n"
                "## 分镜表\n\n| 1 | 0-3s | 左侧标\"50\"，右侧标\"500\" | 钩子句 | 字幕 |\n\n"
                "## 拍摄清单\n\n- 双面板、4 层板各 1 片\n")
        self.assertEqual(check_item({"body": body}, self.ws)["failures"], [])

    def test_fabricated_number_in_prose_still_fails(self):
        from contentforge.checks.fact_checker import check_item
        r = check_item({"body": "## 口播稿\n\n2025 年全球 PCB 产值约 9999 亿美元\n"}, self.ws)
        self.assertIn(9999.0, {a["num"] for a in r["failures"]})


class TestGeoNonDataSections(unittest.TestCase):
    """G4：钩子/封面/发布文案/分镜/拍摄清单属营销文案与拍摄指令，不要求来源标注；正文数据段仍要求。"""

    def setUp(self):
        from contentforge.config import load_workspace
        self.ws = load_workspace("pcb")

    def _g4(self, body):
        from contentforge.checks.geo_checker import check_item
        r = check_item({"body": body, "meta": {"format": "video"}}, self.ws)
        return [f for f in r["failures"] if f["rule"] == "G4"]

    def test_marketing_sections_exempt(self):
        body = ("## 钩子备选（3 个，每个一句）\n\n1. 打样 50 块和 500 块差在哪？\n\n"
                "## 口播稿（60-90 秒）\n\n[0-3s]\n\n打样多少钱？\n\n"
                "## 分镜表\n\n| 1 | 0-3s | 左侧标\"500\" | 钩子 | 字幕 |\n\n"
                "## 封面与标题\n\n主标题：10 片 4 层板报价\n\n"
                "## 发布文案\n\n抖音版：打样 3-7 天交货\n\n"
                "## 拍摄清单\n\n- 样板各 1 片\n")
        self.assertEqual(self._g4(body), [])

    def test_prose_without_source_still_flagged(self):
        body = ("## 口播稿（60-90 秒）\n\n"
                "常规交期 3-7 天，加急可 24-48 小时。\n\n"
                "加急通常上浮 30%-100%。\n\n"
                "多层板占全球 PCB 市场约 48.9%。\n")
        self.assertTrue(self._g4(body))


class TestSourceLabel(unittest.TestCase):
    """事实来源对外可读：知识库文件路径 → 文档标题，外部机构名原样保留。"""

    FILES = [{"path": "04_FAQ/高频问答库.md", "title": "高频问答库"}]

    def test_kb_path_mapped_to_title(self):
        from contentforge.pipelines.base import source_label
        self.assertEqual(source_label("04_FAQ/高频问答库.md", self.FILES), "《高频问答库》")
        self.assertEqual(source_label("华经产业研究院", self.FILES), "华经产业研究院")

    def test_factpack_uses_label(self):
        from contentforge.pipelines.base import factpack_text
        pack = [{"id": "F-050", "claim": "打样 3-7 天", "source": "04_FAQ/高频问答库.md", "year": None}]
        text = factpack_text(pack, self.FILES)
        self.assertIn("来源：《高频问答库》", text)
        self.assertNotIn(".md", text)


class TestConsistency(unittest.TestCase):
    """验收 A5：同一事实跨物料共享，矩阵输出。"""

    def test_matrix(self):
        from contentforge.checks.consistency import check_all
        items = [{"meta": {"id": "C-0001", "format": "faq_page", "fact_ids": ["F-016"]}, "body": ""},
                 {"meta": {"id": "C-0002", "format": "article", "fact_ids": ["F-016"]}, "body": ""}]
        r = check_all(None, items)
        self.assertTrue(r["pass"])
        self.assertIn("F-016", r["shared_facts"])


class TestAnchorVerification(unittest.TestCase):
    """事实锚点验签：主体张冠李戴、错挂 ID、游离断言、年份缺失。"""

    def setUp(self):
        from contentforge.config import load_workspace
        from contentforge import anchors, registry
        self.ws = load_workspace("pcb")
        self.facts = registry.load_facts(self.ws)
        self.fmap = {f["id"]: f for f in self.facts}
        self.tagger = anchors.load_tagger(self.ws)
        self.allowed = {"F-016", "F-017", "F-018"}

    def verify(self, body):
        from contentforge.anchors import verify_body
        return verify_body(body, self.facts, self.tagger, allowed_ids=self.allowed)

    def rules(self, result):
        return [f["rule"] for f in result["failures"]]

    def test_fact_entities_derived_from_claim(self):
        from contentforge.anchors import fact_tags
        self.assertEqual(fact_tags(self.fmap["F-017"], self.tagger)["scope"], {"全球"})
        self.assertEqual(fact_tags(self.fmap["F-018"], self.tagger)["scope"], {"中国大陆"})

    def test_correct_anchor_passes(self):
        r = self.verify("2024 年全球 PCB 产值约 735 亿美元〔F-017〕")
        self.assertTrue(r["anchored"])
        self.assertEqual(r["failures"], [])
        self.assertIn("F-017", r["matched_ids"])

    def test_subject_misattribution_fails(self):
        """735 亿是全球（F-017），写成大陆必须 FAIL。"""
        r = self.verify("2024 年中国大陆 PCB 产值约 735 亿美元〔F-017〕")
        self.assertIn("anchor:subject", self.rules(r))

    def test_wrong_value_for_anchor_fails(self):
        """值对但挂错 ID：F-018（412.13/437.34 亿）下挂 735 亿 → FAIL。"""
        r = self.verify("2024 年全球 PCB 产值约 735 亿美元〔F-018〕")
        self.assertIn("anchor:value", self.rules(r))

    def test_missing_year_fails(self):
        r = self.verify("全球 PCB 产值约 735 亿美元〔F-017〕")
        self.assertIn("anchor:year", self.rules(r))

    def test_bare_assertion_in_contract_body_fails(self):
        body = ("2024 年全球 PCB 产值约 735 亿美元〔F-017〕。\n\n"
                "大陆占比很高，约 70%。")
        r = self.verify(body)
        bare = [f for f in r["failures"] if f["rule"] == "anchor:bare"]
        self.assertTrue(bare)
        self.assertEqual({f["num"] for f in bare}, {70.0})

    def test_multi_clause_split_with_inheritance_passes(self):
        """全球/大陆两个主体拆成两个分句各挂各的 ID，年份沿同段承接。"""
        r = self.verify("2024 年全球 PCB 产值约 735 亿美元〔F-017〕，其中中国大陆占 56.1%〔F-018〕")
        self.assertEqual(r["failures"], [])
        self.assertEqual(r["matched_ids"], {"F-017", "F-018"})

    def test_unknown_and_out_of_pack_anchor_fail(self):
        self.assertIn("anchor:unknown",
                      self.rules(self.verify("2024 年全球 PCB 产值约 735 亿美元〔F-999〕")))
        # F-020 存在但不在本次事实包 → 越权引用
        r = self.verify("2024 年全球多层 PCB 市场规模 367 亿美元〔F-020〕")
        self.assertIn("anchor:scope", self.rules(r))

    def test_two_anchors_one_clause_fails(self):
        r = self.verify("2024 年全球 PCB 产值约 735 亿美元〔F-017〕〔F-018〕")
        self.assertIn("anchor:multi", self.rules(r))

    def test_non_anchor_body_stays_legacy(self):
        r = self.verify("2024 年全球 PCB 产值约 735 亿美元")
        self.assertFalse(r["anchored"])

    def test_render_anchor_to_source(self):
        from contentforge.anchors import render_anchors
        out = render_anchors("2024 年全球 PCB 产值约 735 亿美元〔F-017〕", self.fmap, [])
        self.assertIn("（来源：Prismark / 艾媒咨询转引，2024）", out)
        self.assertNotIn("〔", out)

    def test_check_item_contract_mode_blocks_chetao_case(self):
        from contentforge.checks.fact_checker import check_item
        item = {"body": "2024 年中国大陆 PCB 产值约 735 亿美元〔F-017〕",
                "meta": {"facts": ["F-017"]}}
        r = check_item(item, self.ws)
        self.assertEqual(r["mode"], "anchor")
        self.assertIn("anchor:subject", [f["rule"] for f in r["failures"]])


class TestLLMAssistAndRepair(unittest.TestCase):
    """LLM 兜底：主体归类（裁决权仍在确定性闸）+ 一轮回炉修复。全程注入 fake LLM。"""

    def setUp(self):
        import tempfile
        from pathlib import Path as P
        from contentforge.pipelines.base import dump_front_matter
        self.d = P(tempfile.mkdtemp())
        for sub in ("registry", "kbmeta", "content", "runs"):
            (self.d / sub).mkdir()
        self.facts = [
            {"id": "F-017", "cat": "market_data",
             "claim": "2024 年全球 PCB 产值：约 735 亿美元",
             "source": "Prismark", "year": 2024,
             "numbers": [{"n": 735, "u": "亿美元", "k": "strict"},
                         {"n": 2024, "u": "年", "k": "year"}]},
            {"id": "F-018", "cat": "market_data",
             "claim": "2024 年中国大陆 PCB 产值：约 412.13 亿美元；占全球比重 56.1%",
             "source": "Prismark", "year": 2024,
             # claim 含「全球」（分母），显式 tags 锚定归属主体，避免 claim 扫描多标
             "tags": {"scope": ["中国大陆"]},
             "numbers": [{"n": 412.13, "u": "亿美元", "k": "strict"},
                         {"n": 56.1, "u": "%", "k": "strict"},
                         {"n": 2024, "u": "年", "k": "year"}]},
        ]
        (self.d / "registry" / "facts.json").write_text(
            json.dumps({"facts": self.facts}, ensure_ascii=False), encoding="utf-8")
        # 注意：「国内」故意不收进词表，作为未登录表述
        subjects = {"dimensions": {"scope": {
            "全球": ["全球", "世界"],
            "中国大陆": ["中国大陆", "大陆", "中国"]}}}
        (self.d / "kbmeta" / "subjects.json").write_text(
            json.dumps(subjects, ensure_ascii=False), encoding="utf-8")
        self.ws = {"dir": str(self.d), "name": "t", "kb_path": str(self.d)}

        meta = {"id": "C-0001", "format": "data_article", "title": "测试",
                "status": "generated", "facts": ["F-017", "F-018"],
                "checks": {"fact": "pending", "geo": "pending"}}
        self.item_path = self.d / "content" / "C-0001.md"
        self._meta = meta
        self._dump = dump_front_matter

    def _write_item(self, body):
        self.item_path.write_text(self._dump(self._meta) + "\n\n" + body, encoding="utf-8")

    def _check(self, body, chat_json_fn):
        from contentforge.checks.fact_checker import check_item
        self._write_item(body)
        item = {"meta": self._meta, "body": body}
        return check_item(item, self.ws, llm_assist=True,
                          chat_json_fn=chat_json_fn, threshold=0.9)

    # ---------- chat_json ----------
    def test_chat_json_strips_fence_and_parses(self):
        from unittest.mock import patch
        from contentforge import llm
        with patch.object(llm, "chat", return_value='```json\n{"canonical": "全球"}\n```'):
            self.assertEqual(llm.chat_json({"model": "x"}, []), {"canonical": "全球"})

    # ---------- 主体归类 ----------
    def test_classify_hit_passes_deterministic_gate(self):
        fn = lambda ms: {"phrase": "国内", "canonical": "全球",
                         "new_alias": None, "confidence": 0.95, "reason": "同义"}
        r = self._check("2024 年国内 PCB 产值约 735 亿美元〔F-017〕", fn)
        self.assertEqual(r["failures"], [])
        self.assertTrue(any(w["rule"] == "classify:hit" for w in r["warnings"]))

    def test_classify_wrong_mapping_still_fails(self):
        """LLM 把「国内」硬归成全球，但事实 F-018 归属大陆 → 确定性闸必须仍 FAIL。"""
        fn = lambda ms: {"phrase": "国内", "canonical": "全球",
                         "new_alias": None, "confidence": 0.99, "reason": "乱归"}
        r = self._check("2024 年国内 PCB 产值约 412.13 亿美元〔F-018〕", fn)
        self.assertIn("anchor:subject", [f["rule"] for f in r["failures"]])

    def test_classify_new_subject_goes_to_queue_and_fails(self):
        fn = lambda ms: {"phrase": "国内", "canonical": None,
                         "new_alias": "国内市场", "label": "国内市场", "confidence": 0.9}
        r = self._check("2024 年国内 PCB 产值约 735 亿美元〔F-017〕", fn)
        self.assertTrue(any(f["rule"] == "anchor:subject-missing" for f in r["failures"]))
        sug = json.loads((self.d / "kbmeta" / "subjects_suggestions.json")
                         .read_text(encoding="utf-8"))
        self.assertEqual(len(sug["suggestions"]), 1)
        self.assertEqual(sug["suggestions"][0]["fid"], "F-017")

    def test_classify_bad_json_fails_closed(self):
        def fn(ms):
            raise ValueError("不是 JSON")
        r = self._check("2024 年国内 PCB 产值约 735 亿美元〔F-017〕", fn)
        self.assertTrue(any(f["rule"] == "anchor:subject-missing" for f in r["failures"]))
        self.assertTrue(any(w["rule"] == "classify:reject" for w in r["warnings"]))

    def test_classify_cache_avoids_second_llm_call(self):
        calls = []

        def fn(ms):
            calls.append(1)
            return {"phrase": "国内", "canonical": "全球", "confidence": 0.95}
        body = "2024 年国内 PCB 产值约 735 亿美元〔F-017〕"
        self._check(body, fn)
        self._check(body, fn)
        self.assertEqual(len(calls), 1)

    # ---------- 回炉修复 ----------
    BODY_BARE = "2024 年全球 PCB 产值约 735 亿美元〔F-017〕，大陆占比约 56.1%。\n"
    BODY_FIXED = ("2024 年全球 PCB 产值约 735 亿美元〔F-017〕，"
                  "其中中国大陆占 56.1%〔F-018〕。\n")

    def test_repair_success_overwrites_and_audits(self):
        from contentforge.repair import repair_item
        self._write_item(self.BODY_BARE)
        r = repair_item(self.ws, self.item_path, max_rounds=1,
                        chat_fn=lambda ms, t=0.2: self.BODY_FIXED,
                        use_classify=False, save_report=False)
        self.assertEqual(r["outcome"], "fixed")
        text = self.item_path.read_text(encoding="utf-8")
        self.assertIn("〔F-018〕", text)
        self.assertEqual(r["audits"][-1]["outcome"], "fixed")
        self.assertEqual(r["report"]["fact"]["failures"], [])

    def test_repair_still_failing_keeps_original_and_saves_draft(self):
        from contentforge.repair import repair_item
        self._write_item(self.BODY_BARE)
        r = repair_item(self.ws, self.item_path,
                        chat_fn=lambda ms, t=0.2: self.BODY_BARE,
                        use_classify=False, save_report=False)
        self.assertEqual(r["outcome"], "still_failing")
        self.assertIn("大陆占比约 56.1%。", self.item_path.read_text(encoding="utf-8"))
        self.assertTrue(Path(r["draft_path"]).exists())

    def test_repair_llm_error_keeps_original(self):
        from contentforge.repair import repair_item
        self._write_item(self.BODY_BARE)

        def boom(ms, t=0.2):
            raise RuntimeError("api down")
        r = repair_item(self.ws, self.item_path, chat_fn=boom,
                        use_classify=False, save_report=False)
        self.assertEqual(r["outcome"], "llm_error")
        self.assertIn("大陆占比约 56.1%。", self.item_path.read_text(encoding="utf-8"))
        self.assertEqual(r["audits"][-1]["error"][:11], "api down")

    def test_repair_regression_fixing_one_breaking_another_fails(self):
        """修复稿把原本合规的锚点改坏 → 全量复验必须 FAIL，不得覆盖原稿。"""
        from contentforge.repair import repair_item
        self._write_item(self.BODY_BARE)
        bad_fix = "2024 年中国大陆 PCB 产值约 735 亿美元〔F-017〕，其中大陆占 56.1%〔F-018〕。\n"
        r = repair_item(self.ws, self.item_path, chat_fn=lambda ms, t=0.2: bad_fix,
                        use_classify=False, save_report=False)
        self.assertEqual(r["outcome"], "still_failing")
        self.assertIn("大陆占比约 56.1%。", self.item_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
