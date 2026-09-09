"""OpenAI 兼容 LLM 客户端（标准库 urllib，无第三方依赖）。

配置：环境变量 CF_API_KEY / CF_BASE_URL / CF_MODEL，
或仓库根 llm.json：{"api_key": "...", "base_url": "...", "model": "..."}
默认指向智谱开放平台（OpenAI 兼容端点），可换任意兼容服务。
"""
import json
import time
import urllib.request


def chat(cfg: dict, messages: list, temperature: float = 0.6,
         timeout: int = 180, retries: int = 2) -> str:
    if not cfg.get("api_key"):
        raise RuntimeError("未配置 LLM API key（设置 CF_API_KEY 或 llm.json）")
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {"model": cfg["model"], "messages": messages, "temperature": temperature}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=body, method="POST", headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg['api_key']}",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except Exception as e:                      # noqa: BLE001 —— 网络/API 错误统一重试
            last_err = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"LLM 调用失败（{cfg['model']}）：{last_err}")


def chat_stream(cfg: dict, messages: list, temperature: float = 0.6,
                timeout: int = 180):
    """流式调用 OpenAI 兼容 /chat/completions，逐 token yield。

    用法：
        for token in chat_stream(cfg, messages):
            print(token, end="", flush=True)
    """
    if not cfg.get("api_key"):
        raise RuntimeError("未配置 LLM API key（设置 CF_API_KEY 或 llm.json）")
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    payload = {"model": cfg["model"], "messages": messages,
                "temperature": temperature, "stream": True}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
        "Accept": "text/event-stream",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            try:
                delta = chunk["choices"][0]["delta"].get("content")
            except (KeyError, IndexError):
                continue
            if delta:
                yield delta

