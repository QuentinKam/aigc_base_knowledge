import type { WorkspaceInfo, ItemResponse, FactRef } from "./types";

const API_BASE = "/api";

export async function getWorkspace(): Promise<WorkspaceInfo> {
  const r = await fetch(`${API_BASE}/workspace`);
  if (!r.ok) throw new Error(`workspace: ${r.status}`);
  return r.json();
}

export async function generateSync(
  topicId: string,
  formats: string[],
  useLlm: boolean
): Promise<{ items: ItemResponse[]; used_llm: boolean }> {
  const r = await fetch(`${API_BASE}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic_id: topicId, formats, use_llm: useLlm }),
  });
  if (!r.ok) throw new Error(`generate: ${r.status}`);
  return r.json();
}

export async function customGenerate(
  question: string,
  formats: string[],
  useLlm: boolean
): Promise<{ items: ItemResponse[]; used_llm: boolean }> {
  const r = await fetch(`${API_BASE}/custom`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, formats, use_llm: useLlm }),
  });
  if (!r.ok) throw new Error(`custom: ${r.status}`);
  return r.json();
}

export async function batchGenerate(
  topicIds: string[],
  useLlm: boolean
): Promise<{ job_id: string; items: any[]; total: number }> {
  const r = await fetch(`${API_BASE}/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic_ids: topicIds, use_llm: useLlm }),
  });
  if (!r.ok) throw new Error(`batch: ${r.status}`);
  return r.json();
}

export function batchDownloadUrl(jobId: string): string {
  return `${API_BASE}/batch/download?job_id=${encodeURIComponent(jobId)}`;
}

export async function injectFabrication(
  topicId: string,
  inject: string,
  format: string,
  useLlm: boolean
): Promise<ItemResponse> {
  const r = await fetch(`${API_BASE}/inject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topic_id: topicId, inject, format, use_llm: useLlm }),
  });
  if (!r.ok) throw new Error(`inject: ${r.status}`);
  return r.json();
}

export async function kbVerify(itemId: string): Promise<{ item_id: string; facts: FactRef[] }> {
  const r = await fetch(`${API_BASE}/kb/verify?item_id=${encodeURIComponent(itemId)}`);
  if (!r.ok) throw new Error(`kb/verify: ${r.status}`);
  return r.json();
}

/**
 * 流式生成（SSE）。
 * onToken(format, token) — 每收到一个 token 调用
 * onFormatStart(format) — 一个新格式开始
 * onItem(item) — 一份物料完整生成（含 body + report）
 * onDone() — 全部完成
 */
export async function generateStream(
  topicId: string,
  formats: string[],
  useLlm: boolean,
  handlers: {
    onFormatStart?: (format: string) => void;
    onToken?: (format: string, token: string) => void;
    onItem?: (item: ItemResponse) => void;
    onDone?: () => void;
    onError?: (msg: string) => void;
  }
) {
  const r = await fetch(`${API_BASE}/generate/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ topic_id: topicId, formats, use_llm: useLlm }),
  });
  if (!r.ok || !r.body) {
    handlers.onError?.(`stream: ${r.status}`);
    return;
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "";
  let currentData = "";

  function flush() {
    if (!currentData) return;
    try {
      const d = JSON.parse(currentData);
      if (currentEvent === "format" && d.format) handlers.onFormatStart?.(d.format);
      else if (currentEvent === "token" && d.token) handlers.onToken?.(d.format || "", d.token);
      else if (currentEvent === "item" && d.id) handlers.onItem?.(d as ItemResponse);
      else if (currentEvent === "error" && d.msg) handlers.onError?.(d.msg);
      else if (currentEvent === "done") handlers.onDone?.();
    } catch (e) {
      // 忽略解析错误
    }
    currentData = "";
  }

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (line.startsWith("event:")) {
        // 先把上一组 flush
        flush();
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        currentData = line.slice(5).trim();
        flush();
      } else if (line === "") {
        flush();
      }
    }
  }
  if (buffer) {
    if (buffer.startsWith("data:")) {
      currentData = buffer.slice(5).trim();
      flush();
    }
  }
}
