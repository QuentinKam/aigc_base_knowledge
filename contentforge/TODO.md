# TODO — ContentForge（AI 内容物料生产线）

> 本文件记录**简历口径与代码现状之间的差距**，用于后续补齐。
>
> 简历落点：`ai-job-search-cn-master/cv.md`、`ai-job-search-cn-master/cv-PCB外贸AI获客系统.md`、
> `ai-job-search-cn-master/documents/china/profile/evidence.md`
>
> 设计文档见上级目录 `../intent.md`、`../spec.md`。
>
> 复核方法：逐文件统计 + 实跑 `python -m unittest`（2026-09-10）。

---

## 一、简历当前声明与核实结果

| 简历声明 | 核实结果 |
|---|---|
| 四条生成流水线（官网 FAQ / 知乎·公众号长文 / 短视频物料包 / 行业数据长文） | ✅ 属实，`src/contentforge/pipelines/p{1..4}_*.py` |
| 三道质量门禁（FactChecker / GEOChecker / ConsistencyCheck） | ✅ 属实，`src/contentforge/checks/` |
| 状态机 `generated → fact_pass → geo_pass → approved → published`，未过门禁禁止导出 | ✅ 属实 |
| 「29 个选题」 | ✅ 属实（`topics.json`：trust 5 / insight 4 / decision 6 / faq 14） |
| 「38 份物料样例」 | ✅ 属实（`workspaces/pcb/content/C-*.md`） |
| 「10 项自动化测试」 | ✅ 属实且**全部通过**（`python -m unittest` → Ran 10 tests, OK） |
| 「接入 OpenAI 兼容多模型，未配置 API key 时降级为确定性骨架稿」 | ✅ 属实，且当前**正处于骨架稿模式** |

**结论**：本项目简历声明基本准确，主要差距在「真实 LLM 成稿从未跑过」。

## 二、实测现状（2026-09-10）

- **38 份物料全部是 mock 骨架稿**：grep `mock`/`骨架` 命中全部 38 个文件；无 `llm.json`，未配置 API key
- **状态分布**：`approved` 4 份 / `geo_pass` 17 份 / `generated` 14 份 / `fact_pass` 3 份
  → 即真正通过全部门禁并批准的只有 **4 份**，其余仍在中途
- **事实注册表 59 条**（`registry/facts.json`）：market_data 13 / qa 13 / standard 9 / param 8 / process 7 / template 4 / decision 3 / misc 2（template 类在加载时被过滤）
- **导出已跑通**：`workspaces/pcb/export/` 下有 `site/`、`zhihu/`、`wechat/`、`douyin/` + `manifest.json`
- **检查记录已留档**：`workspaces/pcb/runs/C-*.json`
- **测试用 unittest 而非 pytest**：`tests/test_all.py` 用 `unittest`，`.venv` 内**未装 pytest**
  （`python -m pytest` 报 `No module named pytest`）→ 走 README 写的 `python3 -m unittest tests.test_all` 是对的
- **品牌档案未填**：`workspaces/pcb/brand.md` 仍是占位
- **Web 演示台**：`web/api.py`（FastAPI）+ `web/frontend/`（React/Vite/Tailwind），未部署

---

## 三、待办

### 3.1 配置真实 LLM，产出第一批真成稿（最高优先级）

简历写的是「AI 内容物料生产线」，但至今所有成稿都是骨架稿。这是本项目与简历之间最大的差距。

- [ ] 配置 LLM：仓库根 `llm.json`（`{"api_key","base_url","model"}`）或环境变量 `CF_API_KEY` / `CF_BASE_URL` / `CF_MODEL`
- [ ] 先小样本验证：`./cf generate pcb --topic T-Q08 --formats faq_page,article,video --llm`
- [ ] 人工核对生成稿的事实回溯：每个数字能否在 `facts.json` 找到出处
- [ ] 跑通后批量重生成 38 份，替换现有骨架稿
- [ ] 记录真实 LLM 的**一次通过率**（`intent.md` 定的指标是「AI 初稿一次通过率 ≥ 80%」），验证是否达标
- [ ] 若一次通过率不达标：迭代 system prompt 与事实包注入策略，并记录改进过程

**验收**：至少 10 份真实 LLM 成稿通过 FactChecker + GEOChecker 并进入 `approved`。

### 3.2 把物料推进到 approved

- [ ] 当前 4 份 approved，目标把 38 份全部推进到 `approved`（或明确淘汰不合格的）
- [ ] 对停在 `generated`（14 份）的排查原因：是骨架稿未过门禁，还是流程未跑完
- [ ] 对 `geo_pass`（17 份）跑 `./cf check pcb` 看 FactChecker 是否有 warning
- [ ] 补 `published` 状态的实际登记（需真实发布到平台后回填 URL）

### 3.3 facts.json 契约稳定性（跨项目依赖，已被踩坑）

`../pcb_auto_leadgen/apps/scorer` 通过 `FACTS_JSON_PATH` 读取本项目的 `registry/facts.json`。
该路径目前是**写死的绝对路径**，仓库迁入 `PCB_ALL/` 后已失效，导致对方 4 个单测失败。

- [ ] 明确 facts.json 的路径契约并写进 README：相对谁、迁移时改哪里
- [ ] 提供稳定的解析方式（如环境变量 + 相对路径推导），避免再次因目录迁移断裂
- [ ] 在 README 增加一节「被 pcb_auto_leadgen 复用的事实源接口」
- [ ] 与 `../pcb_knowledge_base` 对齐：知识库扩写后需重跑 `./cf ingest pcb` 刷新注册表

### 3.4 知识库扩写联动

- [ ] `../pcb_knowledge_base` 扩写到 2 万字级后，重跑 `./cf ingest pcb`
- [ ] 确认事实条数从当前 59 条显著增加，且无冲突数字
- [ ] 跑 `./cf check pcb` 确保新增事实未与既有物料冲突

### 3.5 品牌档案

- [ ] 填 `workspaces/pcb/brand.md`（当前占位）——缺失时生成稿降级为通用版并带警示
- [ ] 补齐后重新生成受影响物料，让内容自然带出公司能力

### 3.6 工程化

- [ ] 补 `pytest` 到依赖组（或统一声明只用 unittest），并在 README 明确唯一跑法
- [ ] 把测试纳入 CI（GitHub Actions）
- [ ] `web/api.py` + `web/frontend/` 演示台部署（可选，用于客户演示）
- [ ] 补 `pyproject.toml` / `requirements.txt`（当前依赖靠 `.venv`，无声明文件）

### 3.7 反哺闭环（`intent.md` 的 P1 项）

- [ ] AI 引用监测：月度在 ChatGPT/豆包/Kimi/Perplexity 上查北极星指标（被引用次数），记录到工作区
- [ ] 数据缺口登记回知识库：把生成过程中产生的 `[数据缺口]` 汇总，反哺 `pcb_knowledge_base`
- [ ] 客户咨询的新问题追加进知识库 FAQ

---

## 四、简历措辞同步

- [ ] 真实 LLM 成稿跑通前，简历**不得**声称「已大规模生产并发布内容」或「已产生 GEO 引用/获客结果」
      （`evidence.md`「不应声称的内容」已列此约束）
- [ ] 3.1 完成后，可把「38 份物料样例」升级为「38 份 AI 生成物料，一次通过率 X%」
- [ ] 北极星指标（AI 搜索引用次数）拿到数据前，不得写入任何获客成果
