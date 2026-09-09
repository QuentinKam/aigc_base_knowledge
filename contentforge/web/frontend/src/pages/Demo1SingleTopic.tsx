import { useEffect, useState } from "react";
import { getWorkspace, generateStream } from "../api";
import type { WorkspaceInfo, ItemResponse } from "../types";
import MarkdownView from "../components/MarkdownView";
import FactReport from "../components/FactReport";

const ALL_FORMATS = [
  { id: "faq_page", label: "官网 FAQ 页" },
  { id: "article", label: "知乎/公众号长文" },
  { id: "video", label: "短视频物料包" },
  { id: "data_article", label: "行业数据长文" },
];

export default function Demo1SingleTopic() {
  const [ws, setWs] = useState<WorkspaceInfo | null>(null);
  const [topicId, setTopicId] = useState("");
  const [formats, setFormats] = useState<string[]>(["faq_page", "article", "video"]);
  const [streaming, setStreaming] = useState(false);
  // 流式累积的 token（按 format 分组）
  const [streamBuffers, setStreamBuffers] = useState<Record<string, string>>({});
  // 已完成的物料
  const [items, setItems] = useState<ItemResponse[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    getWorkspace().then((d) => {
      setWs(d);
      if (d.topics.length) setTopicId(d.topics[0].id);
    });
  }, []);

  const toggleFormat = (id: string) => {
    setFormats((prev) =>
      prev.includes(id) ? prev.filter((f) => f !== id) : [...prev, id]
    );
  };

  const handleGenerate = async () => {
    if (!topicId || formats.length === 0) return;
    setStreaming(true);
    setError("");
    setStreamBuffers({});
    setItems([]);

    const useLlm = ws?.has_llm_key ?? false;

    await generateStream(topicId, formats, useLlm, {
      onFormatStart: (fmt) => {
        setStreamBuffers((prev) => ({ ...prev, [fmt]: "" }));
      },
      onToken: (fmt, token) => {
        setStreamBuffers((prev) => ({
          ...prev,
          [fmt]: (prev[fmt] || "") + token,
        }));
      },
      onItem: (item) => {
        setItems((prev) => [...prev, item]);
        setStreamBuffers((prev) => {
          const next = { ...prev };
          delete next[item.format];
          return next;
        });
      },
      onDone: () => {
        setStreaming(false);
      },
      onError: (msg) => {
        setError(msg);
        setStreaming(false);
      },
    });
  };

  if (!ws) return <div>加载中…</div>;

  return (
    <div>
      <h2 className="text-2xl font-bold mb-1">① 单选题 → 三形态现场生成</h2>
      <p className="text-slate-600 mb-4 text-sm">
        选 1 条选题 → 勾选生成格式 → 实时看 LLM 写作（无 key 时走 mock 骨架稿）→ 每份带 FactChecker + GEOChecker 红绿报告
      </p>

      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
          <div>
            <label className="block text-xs text-slate-500 mb-1">选题</label>
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
            <label className="block text-xs text-slate-500 mb-1">格式（多选）</label>
            <div className="flex flex-wrap gap-2">
              {ALL_FORMATS.map((f) => (
                <label
                  key={f.id}
                  className={`px-2 py-1 text-xs border rounded cursor-pointer ${
                    formats.includes(f.id)
                      ? "bg-blue-600 text-white border-blue-600"
                      : "bg-white border-slate-300 text-slate-700"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={formats.includes(f.id)}
                    onChange={() => toggleFormat(f.id)}
                    className="hidden"
                  />
                  {f.label}
                </label>
              ))}
            </div>
          </div>
          <div className="flex items-end">
            <button
              onClick={handleGenerate}
              disabled={streaming || !topicId || formats.length === 0}
              className="bg-blue-600 text-white px-4 py-2 rounded text-sm disabled:opacity-50 hover:bg-blue-700"
            >
              {streaming ? "生成中…" : "开始生成"}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 p-3 rounded mb-4 text-sm">
          错误：{error}
        </div>
      )}

      {/* 流式渲染中 */}
      {Object.keys(streamBuffers).length > 0 && (
        <div className="mb-6">
          <h3 className="text-sm font-semibold text-slate-700 mb-2">⏳ 生成中…</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Object.entries(streamBuffers).map(([fmt, buf]) => (
              <div key={fmt} className="border border-blue-200 bg-blue-50 rounded p-3">
                <div className="text-xs font-semibold text-blue-700 mb-2">
                  {ALL_FORMATS.find((f) => f.id === fmt)?.label || fmt}
                </div>
                <pre className="text-xs text-slate-700 whitespace-pre-wrap max-h-80 overflow-y-auto">
                  {buf}
                  <span className="animate-pulse">▌</span>
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 完成的物料 */}
      {items.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-700 mb-3">✓ 生成的 {items.length} 份物料</h3>
          <div className="space-y-6">
            {items.map((item) => (
              <div key={item.id} className="bg-white border border-slate-200 rounded-lg overflow-hidden">
                <div className="bg-slate-100 px-4 py-2 flex items-center justify-between">
                  <div>
                    <span className="font-mono text-sm text-slate-700">{item.id}</span>
                    <span className="ml-2 text-xs text-slate-500">
                      [{ALL_FORMATS.find((f) => f.id === item.format)?.label || item.format}]
                    </span>
                    <span className="ml-2 text-xs text-slate-500">{item.title}</span>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    item.status === "geo_pass" ? "bg-emerald-100 text-emerald-700" :
                    item.status === "approved" ? "bg-blue-100 text-blue-700" : "bg-slate-200 text-slate-700"
                  }`}>
                    {item.status}
                  </span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-0">
                  <div className="md:col-span-2 p-4 border-r border-slate-100 max-h-[600px] overflow-y-auto">
                    <MarkdownView>{item.body}</MarkdownView>
                  </div>
                  <div className="p-4 bg-slate-50">
                    <FactReport report={item.report} />
                    {item.facts_used.length > 0 && (
                      <div className="mt-3 text-xs">
                        <div className="text-slate-700 font-medium mb-1">引用事实（可回溯）</div>
                        {item.facts_used.map((f) => (
                          <div key={f.id} className="text-slate-600 mb-1">
                            <code className="text-blue-700">{f.id}</code>{" "}
                            <span>{f.claim.slice(0, 60)}…</span>
                            <div className="text-slate-400 text-[10px] font-mono">{f.kb_ref}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
