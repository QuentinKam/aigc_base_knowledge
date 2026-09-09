import { useEffect, useState } from "react";
import { getWorkspace, batchGenerate, batchDownloadUrl } from "../api";
import type { WorkspaceInfo } from "../types";

export default function Demo3Batch() {
  const [ws, setWs] = useState<WorkspaceInfo | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<{ job_id: string; items: any[]; total: number } | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getWorkspace().then((d) => {
      setWs(d);
      // 默认勾选前 5 个
      setSelected(new Set(d.topics.slice(0, 5).map((t) => t.id)));
    });
  }, []);

  const toggleTopic = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleBatch = async () => {
    if (selected.size === 0) return;
    setRunning(true);
    setError("");
    setResult(null);
    try {
      const r = await batchGenerate(Array.from(selected), true);
      setResult(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  if (!ws) return <div>加载中…</div>;

  return (
    <div>
      <h2 className="text-2xl font-bold mb-1">③ 一键批量排产 + 导出 zip</h2>
      <p className="text-slate-600 mb-4 text-sm">
        勾选 5+ 选题 → 一键批量生成（每题 3 形态 = 15+ 份物料）→ 下载完整 zip 包
      </p>

      <div className="bg-white border border-slate-200 rounded-lg p-4 mb-6">
        <div className="flex items-center justify-between mb-3">
          <div>
            <span className="text-sm font-medium">已选 {selected.size} 个选题</span>
            <span className="text-xs text-slate-500 ml-2">
              → 预计生成 {selected.size * 3} 份物料
            </span>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setSelected(new Set(ws.topics.map((t) => t.id)))}
              className="text-xs px-2 py-1 border border-slate-300 rounded hover:bg-slate-50"
            >
              全选
            </button>
            <button
              onClick={() => setSelected(new Set())}
              className="text-xs px-2 py-1 border border-slate-300 rounded hover:bg-slate-50"
            >
              清空
            </button>
            <button
              onClick={handleBatch}
              disabled={running || selected.size === 0}
              className="bg-blue-600 text-white px-4 py-2 rounded text-sm disabled:opacity-50 hover:bg-blue-700"
            >
              {running ? "批量生成中…" : "一键排产"}
            </button>
          </div>
        </div>

        {running && (
          <div className="bg-blue-50 border border-blue-200 rounded p-3 text-sm text-blue-700">
            ⏳ 后端串行生成中，{selected.size} 个选题 × 3 形态 = {selected.size * 3} 份物料。
            <div className="mt-1 text-xs text-blue-500">每份约 2-5 秒（mock），完成后自动出 zip 下载按钮</div>
          </div>
        )}

        <div className="max-h-72 overflow-y-auto border border-slate-200 rounded">
          {ws.topics.map((t) => (
            <label
              key={t.id}
              className={`flex items-center gap-2 px-3 py-1.5 border-b border-slate-100 hover:bg-slate-50 cursor-pointer ${
                selected.has(t.id) ? "bg-blue-50" : ""
              }`}
            >
              <input
                type="checkbox"
                checked={selected.has(t.id)}
                onChange={() => toggleTopic(t.id)}
                className="rounded"
              />
              <span className="font-mono text-xs text-slate-500 w-12">{t.id}</span>
              <span className="text-xs px-1.5 py-0.5 bg-slate-200 rounded text-slate-700">
                {t.pillar}
              </span>
              <span className="text-sm text-slate-700 flex-1">{t.title}</span>
            </label>
          ))}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-300 text-red-700 p-3 rounded mb-4 text-sm">
          错误：{error}
        </div>
      )}

      {result && (
        <div className="bg-emerald-50 border border-emerald-300 rounded-lg p-5">
          <h3 className="font-semibold text-emerald-800 mb-2">
            ✓ 批量完成：{result.total} 份物料
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs mb-4 max-h-60 overflow-y-auto">
            {result.items.map((it, i) => (
              <div key={i} className="bg-white border border-emerald-200 rounded p-2">
                <div className="font-mono text-emerald-700">{it.id}</div>
                <div className="text-slate-600">
                  [{it.format}] {it.title?.slice(0, 20)}…
                </div>
                <div className="text-slate-400">{it.status}</div>
              </div>
            ))}
          </div>
          <a
            href={batchDownloadUrl(result.job_id)}
            className="inline-flex items-center gap-2 bg-emerald-600 text-white px-4 py-2 rounded text-sm hover:bg-emerald-700"
          >
            📦 下载 zip（含 manifest.json）
          </a>
        </div>
      )}
    </div>
  );
}
