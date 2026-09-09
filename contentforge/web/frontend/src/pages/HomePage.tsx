import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { getWorkspace } from "../api";
import type { WorkspaceInfo } from "../types";

const DEMOS = [
  {
    path: "/demo1",
    no: 1,
    title: "单选题 → 三形态现场生成",
    desc: "从选题池选 1 条，实时生成 FAQ 页 / 知乎长文 / 短视频物料包三份，每份带 FactChecker 红绿报告。",
    icon: "①",
  },
  {
    path: "/demo2",
    no: 2,
    title: "客户自带问题 → 现场生成",
    desc: "客户输入关心的问题（如「PCB 打样最快多久」），从知识库自动找事实生成，可对照原文核验。",
    icon: "②",
  },
  {
    path: "/demo3",
    no: 3,
    title: "一键批量排产 + 导出 zip",
    desc: "勾选 5+ 选题 → 一键批量生成 15+ 份物料 → 下载完整 zip 包 + 一致性矩阵。",
    icon: "③",
  },
  {
    path: "/demo4",
    no: 4,
    title: "防编造注入演示",
    desc: "故意向 prompt 注入「1000 亿美元」→ 系统输出 [数据缺口] + FactChecker 红框拦截。",
    icon: "④",
  },
];

export default function HomePage() {
  const [ws, setWs] = useState<WorkspaceInfo | null>(null);
  useEffect(() => {
    getWorkspace().then(setWs).catch(() => {});
  }, []);

  return (
    <div>
      <div className="bg-gradient-to-r from-blue-600 to-indigo-700 text-white p-8 rounded-xl mb-8">
        <h2 className="text-3xl font-bold mb-2">把知识库变成可发布内容</h2>
        <p className="text-blue-100 max-w-2xl">
          演示把 PCB 知识库（{ws?.stats.topics || 0} 选题、{ws?.stats.facts || 0} 事实）自动生成多平台物料：
          每个数字可回溯知识库文件，FactChecker + GEOChecker 双重门禁，未通过禁止导出。
        </p>
        {ws && (
          <div className="mt-4 flex gap-4 text-sm">
            <div className="bg-white/10 px-3 py-1 rounded">
              知识库：<code className="font-mono">{ws.name}</code>
            </div>
            <div className="bg-white/10 px-3 py-1 rounded">
              LLM：<code className="font-mono">{ws.has_llm_key ? ws.model : "mock-skeleton"}</code>
            </div>
            <div className="bg-white/10 px-3 py-1 rounded">
              已生成物料：<code className="font-mono">{ws.stats.items}</code>
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {DEMOS.map((d) => (
          <Link
            key={d.path}
            to={d.path}
            className="border border-slate-200 rounded-lg p-5 hover:shadow-md hover:border-blue-400 transition-all bg-white"
          >
            <div className="flex items-start gap-3">
              <div className="text-3xl text-blue-600 font-bold">{d.icon}</div>
              <div>
                <h3 className="font-semibold text-lg text-slate-900 mb-1">{d.title}</h3>
                <p className="text-sm text-slate-600 leading-relaxed">{d.desc}</p>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
