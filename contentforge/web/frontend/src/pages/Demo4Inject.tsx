import { useEffect, useState } from "react";
import { getWorkspace, injectFabrication } from "../api";
import type { WorkspaceInfo, ItemResponse } from "../types";
import MarkdownView from "../components/MarkdownView";
import FactReport from "../components/FactReport";

const PRESET_INJECTS = [
  "1000 亿美元",
  "市场占有率 80%",
  "最快 1 小时交货",
  "通过 ISO 99999 认证",
];

export default function Demo4Inject() {
  const [ws, setWs] = useState<WorkspaceInfo | null>(null);
  const [topicId, setTopicId] = useState("");
  const [inject, setInject] = useState(PRESET_INJECTS[0]);
  const [loading, setLoading] = useState(false);
  const [item, setItem] = useState<ItemResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getWorkspace().then((d) => {
      setWs(d);
      // 选个市场类的，容易展示编造
      const insight = d.topics.find((t) => t.pillar === "insight") || d.topics[0];
      setTopicId(insight.id);
    });
  }, []);

  const handleInject = async () => {
    if (!topicId || !inject.trim()) return;
    setLoading(true);
    setError("");
    setItem(null);
    try {
      const r = await injectFabrication(topicId, inject, "faq_page", true);
      setItem(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  if (!ws) return <div>加载中…</div>;

  return (
    <div>
      <h2 className="text-2xl font-bold mb-1">④ 防编造注入演示</h2>
      <p className="text-slate-600 mb-4 text-sm">
        故意向 prompt 注入虚构数字 → 系统强制输出 <code className="bg-amber-100 px-1">[数据缺口]</code> → FactChecker 红框拦截。
        这是 ContentForge 防止 LLM 编造数据的核心防线。
      </p>

      <div className="bg-amber-50 border border-amber-300 rounded-lg p-4 mb-6">
        <div className="text-sm text-amber-800 mb-2">
          🛡️ <strong>防线原理：</strong>
          生成 prompt 只注入知识库事实包 + system 约束「事实包中没有的数据一律写 [数据缺口]」。
          FactChecker 二次校验每个数字，未在注册表中的（包括舍入值如 851.5 ≠ 851.52）一律拦下。
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
          <div>
            <label className="block text-xs text-slate-500 mb-1">选题（建议市场类）</label>
            <select
              value={topicId}
              onChange={(e) => setTopicId(e.target.value)}
              className="w-full border border-slate-300 rounded px-2 py-1.5 text-sm"
            >
              {ws.topics.map((t) => (
                <option key={t.id} value={t.id}>
                  [{t.id}] {t.title}（{t.pillar}）
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">注入虚构数据</label>
            <input
              value={inject}
              onChange={(e) => setInject(e.target.value)}
              className="w-full border border-red-300 rounded px-2 py-1.5 text-sm bg-red-50"
              placeholder="输入一个知识库中不存在的数字"
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={handleInject}
              disabled={loading || !topicId || !inject.trim()}
              className="bg-red-600 text-white px-4 py-2 rounded text-sm disabled:opacity-50 hover:bg-red-700"
            >
              {loading ? "生成中…" : "⚠ 注入并生成"}
            </button>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="text-xs text-slate-500">建议尝试：</span>
          {PRESET_INJECTS.map((q) => (
            <button
              key={q}
              onClick={() => setInject(q)}
              className="text-xs px-2 py-1 border border-slate-300 rounded hover:bg-slate-50"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 p-3 rounded mb-4 text-sm">
          错误：{error}
        </div>
      )}

      {item && (
        <div>
          <div className="bg-red-50 border border-red-300 rounded-lg p-3 mb-4 text-sm">
            <div className="text-red-800 font-semibold mb-1">
              🎯 演示结果
            </div>
            <div className="text-red-700">
              注入的虚构数据 <code className="bg-white px-1 mx-1">{item.inject}</code>
              {item.highlight_gaps && item.highlight_gaps.length > 0 ? (
                <>
                  {" "}→ 系统拦截，成稿出现 <code className="bg-white px-1 mx-1">{item.highlight_gaps.length}</code> 处数据缺口标记：
                  <ul className="mt-1 ml-4 list-disc">
                    {item.highlight_gaps.map((g, i) => (
                      <li key={i} className="text-red-700 font-mono text-xs">{g}</li>
                    ))}
                  </ul>
                </>
              ) : (
                <>
                  {" "}→ FactChecker 是否拦截？查看右侧报告 ↓
                </>
              )}
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
            <div className="bg-slate-100 px-4 py-2">
              <span className="font-mono text-sm text-slate-700">{item.id}</span>
              <span className="ml-2 text-xs text-slate-500">[{item.format}]</span>
              <span className="ml-2 text-xs text-slate-500">{item.title}</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-0">
              <div className="md:col-span-2 p-4 border-r border-slate-100 max-h-[600px] overflow-y-auto">
                <MarkdownView highlightGaps>{item.body}</MarkdownView>
              </div>
              <div className="p-4 bg-slate-50">
                <FactReport report={item.report} />
                <div className="mt-3 text-xs bg-amber-50 border border-amber-200 rounded p-2">
                  <div className="font-semibold text-amber-800 mb-1">💡 说明</div>
                  <p className="text-amber-700">
                    红色高亮即 [数据缺口：xxx] 标记，是系统对 LLM 输出虚构数字的强制拦截输出。
                    FactChecker 红框则是对成稿中出现的事实包外数字的二次防线。
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
