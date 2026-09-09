# ContentForge · AI 内容物料生产线

把一份行业知识库变成"可发布级"的多平台内容物料：**官网 FAQ 页 / 知乎·公众号长文 / 短视频物料包 / 行业数据长文**。每一份成稿的每个数字都可回溯到知识库文件，未过质量门禁不允许导出。

设计文档见上级目录：`../intent.md`（为什么做）、`../spec.md`（完整规格）。

## 快速开始

```bash
cd contentforge

# 1. 接入知识库（PCB 库已配好，可直接从第 2 步开始）
./cf init myind --kb /path/to/knowledge_base

# 2. 解析知识库 → 事实注册表 / FAQ / 选题池 / 模板 / 规则
./cf ingest pcb

# 3. 看有什么可产
./cf topics pcb                 # 29 个选题（四大支柱）
./cf facts pcb --cat market_data

# 4. 生成（单选题 → 多平台物料，自动过双检查器）
./cf generate pcb --topic T-Q08 --formats faq_page,article,video
./cf generate pcb --topic T-006 --formats data_article

# 5. 审核 → 导出
./cf check pcb                  # 全量复检 + 跨物料一致性矩阵
./cf approve pcb --id C-0001
./cf export pcb                 # 按平台输出到 workspaces/pcb/export/
```

## 接入 LLM（当前为 mock 骨架稿模式）

机器上未配置 API key 时，`generate` 产出**确定性骨架稿**（结构完整、数字全部可溯源，但行文是拼装的）。配置任意 OpenAI 兼容服务后生成成稿：

```bash
export CF_API_KEY="你的key"
export CF_BASE_URL="https://open.bigmodel.cn/api/paas/v4"   # 可换 DeepSeek/Qwen/OpenAI 等
export CF_MODEL="glm-4-flash"
./cf generate pcb --topic T-Q08 --llm
```

或写入仓库根 `llm.json`：`{"api_key": "...", "base_url": "...", "model": "..."}`。

## 防编造机制（工具的核心）

1. **第一道**：生成 prompt 只注入选题相关"事实包"，system 约束"事实包没有的数据一律写 `[数据缺口：…]`"。
2. **第二道**：FactChecker 抽取成稿中全部 (数值, 单位) 断言（含范围、百分比、标准号掩码），逐条比对注册表——`851.52 ≠ 852`，舍入值也会被拦。
3. **GEOChecker**：按知识库 06 规范检查（直接答案前置 / 提问式标题 / 事实密度 / 来源标注 / 品牌绑定与禁词 / 结构完整）。
4. **ConsistencyCheck**：同一事实跨物料共享矩阵，保证多平台口径一致。
5. 状态机 `generated → fact_pass → geo_pass → approved → published`，未到 approved 禁止导出。

## 换一个行业

1. 知识库按四类目录整理：事实源（带"数据|数值|来源|时间"表格或含数字列表）、FAQ（`**Q：**/A：` 块）、选题池（编号行 + `→ 目录`）、模板（fenced 块）；另备品牌档案 `brand.md`（`key: value` 行）。
2. 复制 `src/contentforge/ingest/pcb.py` 改 `DIRS` 目录名配置。
3. `./cf init <name> --kb <path>` → `ingest` → `generate`。

## 目录

```
contentforge/
├── cf                     # 启动器
├── src/contentforge/
│   ├── ingest/            # 知识库解析（PCB 适配器）
│   ├── pipelines/         # P1-P4 生成流水线 + fact pack + mock
│   ├── checks/            # FactChecker / GEOChecker / ConsistencyCheck
│   ├── export/            # 平台导出 + FAQPage JSON-LD
│   └── cli.py             # init/ingest/facts/topics/generate/check/approve/export/status
├── tests/test_all.py      # 单元测试（python3 -m unittest tests.test_all）
└── workspaces/pcb/        # PCB 实例：registry/ kbmeta/ content/ export/
```

## M1 验收状态

| 用例 | 结果 |
|------|------|
| A1 FAQ Q8 → 三形态，数字可回溯 | ✅ 全部 geo_pass |
| A2 851 亿美元 → 数据长文，来源年份齐 | ✅ geo_pass |
| A3 注入编造数字被拦（含舍入 851.5） | ✅ 单测覆盖 |
| A4 品牌档案示例占位 → 生成+导出带警示 | ✅ G5 warning |
| A5 跨物料一致性矩阵 | ✅ 24 条事实共享 |
