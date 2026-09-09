import type { CheckReport } from "../types";

interface Props {
  report: CheckReport;
}

export default function FactReport({ report }: Props) {
  const factFail = report.fact.failures.length > 0;
  const geoFail = report.geo.failures.length > 0;
  const factPass = !factFail;
  const geoPass = !geoFail;
  const overallPass = factPass && geoPass;

  return (
    <div
      className={`border-l-4 p-4 rounded-r-md mb-4 ${
        overallPass
          ? "bg-emerald-50 border-emerald-500"
          : "bg-red-50 border-red-500"
      }`}
    >
      <h3 className={`font-semibold mb-2 ${overallPass ? "text-emerald-800" : "text-red-800"}`}>
        {overallPass ? "✓ 全部检查通过" : "✗ 检查未通过"}
        <span className="text-sm font-normal text-slate-600 ml-2">
          （状态：{report.status}）
        </span>
      </h3>

      {/* FactChecker */}
      <div className="mb-3">
        <div className={`text-sm font-medium mb-1 ${factPass ? "text-emerald-700" : "text-red-700"}`}>
          {factPass ? "✓ FactChecker" : "✗ FactChecker"}（断言 {report.fact.total ?? "—"}，失败 {report.fact.failures.length}，告警 {report.fact.warnings.length}，数据缺口 {report.fact.gaps.length}）
        </div>
        {report.fact.failures.map((f, i) => (
          <div key={i} className="bg-red-100 border border-red-300 rounded px-2 py-1 my-1 text-sm">
            <span className="font-mono text-red-800">
              {f.line ? `L${f.line}` : ""}
            </span>{" "}
            <span className="text-red-900">{f.note || f.snippet}</span>
            {f.snippet && (
              <div className="mt-0.5 text-xs text-red-700 font-mono">「{f.snippet}」</div>
            )}
          </div>
        ))}
        {report.fact.warnings.map((w, i) => (
          <div key={`w${i}`} className="text-amber-700 text-sm px-2 py-0.5">
            ⚠ {w.line ? `L${w.line} ` : ""}{w.note}
          </div>
        ))}
        {report.fact.gaps.length > 0 && (
          <div className="mt-2 bg-red-100 border border-red-300 rounded p-2">
            <div className="text-red-800 text-sm font-semibold">数据缺口标记：</div>
            {report.fact.gaps.map((g, i) => (
              <div key={i} className="text-red-700 text-sm font-mono">{g}</div>
            ))}
          </div>
        )}
      </div>

      {/* GEOChecker */}
      <div>
        <div className={`text-sm font-medium mb-1 ${geoPass ? "text-emerald-700" : "text-red-700"}`}>
          {geoPass ? "✓ GEOChecker" : "✗ GEOChecker"}（失败 {report.geo.failures.length}，告警 {report.geo.warnings.length}）
        </div>
        {report.geo.failures.map((f, i) => (
          <div key={i} className="bg-red-100 border border-red-300 rounded px-2 py-1 my-1 text-sm">
            <span className="font-mono text-red-800">[{f.rule}]</span>{" "}
            <span className="text-red-900">{f.msg}</span>
          </div>
        ))}
        {report.geo.warnings.map((w, i) => (
          <div key={`gw${i}`} className="text-amber-700 text-sm px-2 py-0.5">
            ⚠ [{w.rule}] {w.msg}
          </div>
        ))}
      </div>
    </div>
  );
}
