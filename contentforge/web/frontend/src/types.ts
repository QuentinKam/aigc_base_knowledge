// 共享类型定义

export interface Topic {
  id: string;
  title: string;
  pillar: "trust" | "insight" | "decision" | "faq";
  kb_refs: string[];
  first_seen?: string;
}

export interface WorkspaceInfo {
  name: string;
  kb_path: string;
  has_llm_key: boolean;
  model: string;
  stats: { topics: number; facts: number; items: number };
  topics: Topic[];
}

export interface FactRef {
  id: string;
  claim: string;
  kb_ref: string;
  source?: string;
  year?: number | null;
}

export interface CheckFailure {
  line?: number;
  rule?: string;
  note?: string;
  msg?: string;
  snippet?: string;
}

export interface CheckReport {
  id: string;
  format: string;
  status: string;
  fact: {
    total?: number;
    failures: CheckFailure[];
    warnings: CheckFailure[];
    gaps: string[];
    matched_ids?: string[];
  };
  geo: {
    failures: CheckFailure[];
    warnings: CheckFailure[];
  };
}

export interface ItemResponse {
  id: string;
  format: string;
  topic?: string;
  title?: string;
  status: string;
  body: string;
  facts_used: FactRef[];
  gaps: string[];
  report: CheckReport;
  inject?: string;
  highlight_gaps?: string[];
}
