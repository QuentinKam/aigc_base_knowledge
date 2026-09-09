import { NavLink, Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { getWorkspace } from "../api";
import type { WorkspaceInfo } from "../types";

const DEMOS = [
  { path: "/", label: "首页", icon: "🏠" },
  { path: "/demo1", label: "单选题三形态", icon: "①" },
  { path: "/demo2", label: "客户自带问题", icon: "②" },
  { path: "/demo3", label: "一键批量排产", icon: "③" },
  { path: "/demo4", label: "防编造注入", icon: "④" },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const [ws, setWs] = useState<WorkspaceInfo | null>(null);

  useEffect(() => {
    getWorkspace().then(setWs).catch(() => {});
  }, []);

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-slate-900 text-white shadow-md">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <span className="text-2xl">🔧</span>
            <div>
              <h1 className="text-lg font-bold">ContentForge</h1>
              <p className="text-xs text-slate-300">AI 内容物料生产线</p>
            </div>
          </Link>
          <div className="flex gap-1">
            {DEMOS.map((d) => (
              <NavLink
                key={d.path}
                to={d.path}
                end={d.path === "/"}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded text-sm transition-colors ${
                    isActive ? "bg-blue-600" : "hover:bg-slate-700"
                  }`
                }
              >
                <span className="mr-1">{d.icon}</span>
                {d.label}
              </NavLink>
            ))}
          </div>
        </div>
        {ws && !ws.has_llm_key && (
          <div className="bg-amber-500 text-amber-900 text-sm px-4 py-1.5 text-center">
            ⚠ 当前为 Mock 模式（未配置 LLM API key）。设置 <code>CF_API_KEY</code> 环境变量可启用真 LLM 流式生成。
          </div>
        )}
        {ws && ws.has_llm_key && (
          <div className="bg-emerald-600 text-white text-sm px-4 py-1.5 text-center">
            ✓ LLM 已启用：{ws.model} · 知识库 {ws.stats.topics} 选题 / {ws.stats.facts} 事实
          </div>
        )}
      </header>
      <main className="flex-1 max-w-7xl mx-auto px-4 py-6 w-full">{children}</main>
      <footer className="bg-slate-100 text-slate-500 text-xs text-center py-3">
        ContentForge Web Demo · 演示用，所有内容基于 {ws?.name || "pcb"} 知识库
      </footer>
    </div>
  );
}
