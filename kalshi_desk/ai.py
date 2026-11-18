# -*- coding: utf-8 -*-
"""极简 OpenAI 兼容 Chat Completions 客户端（支持自定义 base_url / key / model）。"""
from __future__ import annotations

import requests


def ask(question: str, context: str, provider: dict,
        proxy: str | None = None, timeout: int = 90) -> str:
    base = (provider.get("base_url") or "").rstrip("/")
    key = provider.get("api_key") or ""
    model = provider.get("model") or ""
    if not (base and key and model):
        raise ValueError("AI 服务商配置不完整：需要 base_url、api_key、model")
    system = ("你是 Kalshi 预测市场交易分析助手。只能依据用户提供的本地数据回答；"
              "数据不足以回答时明确说明缺什么，不要编造数字。"
              "用中文回答，先给结论，再列依据，必要时用要点列表。")
    user = f"本地数据（来自 DuckDB 的汇总）：\n{context}\n\n问题：{question}"
    payload = {
        "model": model,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None
    resp = requests.post(
        base + "/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=payload, proxies=proxies, timeout=timeout,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"AI 接口返回 {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    return (choice.get("message") or {}).get("content", "").strip()
