import { useState } from "react";
import { customGenerate, kbVerify } from "../api";
import type { ItemResponse, FactRef } from "../types";
import MarkdownView from "../components/MarkdownView";
import FactReport from "../components/FactReport";

const ALL_FORMATS = [
  { id: "faq_page", label: "官网 FAQ 页" },
  { id: "article", label: "知乎/公众号长文" },
];

const PRESET_QUESTIONS = [
  "PCB 打样最快多久能交货？",
  "HDI 板为什么比常规板贵？",
  "PCB 厂家怎么选？看哪些资质？",
  "什么是高 Tg 板材，什么时候必须用？",
];

export default function Demo2CustomQuestion() {
  const [question, setQuestion] = useState(PRESET_QUESTIONS[0]);
  const [formats, setFormats] = useState<string[]>(["faq_page", "article"]);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<ItemResponse[]>([]);
  const [verifyFacts, setVerifyFacts] = useState<Record<string, FactRef[]>>({});
  const [error, setError] = useState("");

  const toggleFormat = (id: string) => {
    setFormats((prev) =>
      prev.includes(id) ? prev.filter((f) => f !== id) : [...prev, id]
    );
  };

  const handleGenerate = async () => {
    if (!question.trim() || formats.length === 0) return;
    setLoading(true);
    setError("");
    setItems([]);
    setVerifyFacts({});
    try {
      const r = await customGenerate(question, formats, true);
      setItems(r.items);
      // 拉每份物料的引用事实
      for (const it of r.items) {
        const v = await kbVerify(it.id);
        setVerifyFacts((prev) => ({ ...prev, [it.id]: v.facts }));
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h2 className="text-2xl font-bold mb-1">② 客户自带问题 → 现场生成</h2>
      <p className="text-slate-600 mb-4 text-sm">
        客户输入关心的问题 → 系统从知识库自动找相关事实 → 现场生成 → 可对照知识库原文核验每个数字
      </p>

      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-6">
        <label className="block text-xs text-slate-500 mb-1">客户问题</label>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={2}
          className="w-full border border-slate-300 rounded px-3 py-2 text-sm mb-3"
          placeholder="输入一个客户常问的问题…"
        />
        <div className="flex flex-wrap gap-2 mb-3">
          {PRESET_QUESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => setQuestion(q)}
              className="text-xs px-2 py-1 border border-slate-300 rounded hover:bg-slate-50"
            >
              {q}
            </button>
          ))}
        </div>
        <div className="flex items-end gap-3">
          <div>
            <label className="block text-xs text-slate-500 mb-1">格式</label>
            <div className="flex gap-2">
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
          <button
            onClick={handleGenerate}
            disabled={loading || !question.trim()}
            className="bg-blue-600 text-white px-4 py-2 rounded text-sm disabled:opacity-50 hover:bg-blue-700"
          >
            {loading ? "生成中…" : "现场生成"}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 p-3 rounded mb-4 text-sm">
          错误：{error}
        </div>
      )}

      {items.length > 0 && (
        <div className="space-y-6">
          {items.map((item) => (
            <div key={item.id} className="bg-white border border-slate-200 rounded-lg overflow-hidden">
              <div className="bg-slate-100 px-4 py-2 flex items-center justify-between">
                <div>
                  <span className="font-mono text-sm text-slate-700">{item.id}</span>
                  <span className="ml-2 text-xs text-slate-500">
                    [{ALL_FORMATS.find((f) => f.id === item.format)?.label || item.format}]
                  </span>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded ${
                  item.status === "geo_pass" ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-700"
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
                  {(verifyFacts[item.id] || []).length > 0 && (
                    <details className="mt-3 text-xs">
                      <summary className="cursor-pointer text-slate-700 font-medium">
                        对照原文（{verifyFacts[item.id].length} 条事实）
                      </summary>
                      <div className="mt-2 space-y-2">
                        {(verifyFacts[item.id] || []).map((f) => (
                          <div key={f.id} className="border-l-2 border-blue-300 pl-2">
                            <code className="text-blue-700 text-[10px]">{f.id}</code>
                            <div className="text-slate-700">{f.claim}</div>
                            <div className="text-slate-400 text-[10px] font-mono">
                              📄 {f.kb_ref}
                              {f.source && ` · 来源：${f.source}`}
                              {f.year && ` · ${f.year}`}
                            </div>
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
