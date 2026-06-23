# -*- coding: utf-8 -*-
"""统一AI调用模块：默认 DeepSeek，预留 OpenAI。"""
from __future__ import annotations

import json
import os
import re
from typing import Any

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL_DEFAULT = "deepseek-v4-flash"
OPENAI_MODEL_DEFAULT = "gpt-5.4-mini"

PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_OPENAI = "openai"


def extract_json(text: str) -> dict[str, Any]:
    """兼容纯JSON和 ```json ... ``` 包裹输出。"""
    if not isinstance(text, str):
        raise ValueError("模型输出不是字符串")
    raw = text.strip()
    m = re.search(r"```json\s*(.*?)\s*```", raw, re.S)
    if m:
        raw = m.group(1).strip()
    else:
        m = re.search(r"```\s*(.*?)\s*```", raw, re.S)
        if m:
            raw = m.group(1).strip()
    return json.loads(raw)


def provider_label(provider: str) -> str:
    return "DeepSeek" if provider == PROVIDER_DEEPSEEK else "OpenAI / ChatGPT API"


def get_env_key(provider: str) -> str | None:
    if provider == PROVIDER_DEEPSEEK:
        return os.getenv("DEEPSEEK_API_KEY")
    if provider == PROVIDER_OPENAI:
        return os.getenv("OPENAI_API_KEY")
    return None


def check_api_key(provider: str) -> tuple[bool, str]:
    key = get_env_key(provider)
    if not key:
        env_name = "DEEPSEEK_API_KEY" if provider == PROVIDER_DEEPSEEK else "OPENAI_API_KEY"
        return False, f"未检测到 {env_name} 环境变量。"
    if not key.isascii():
        return False, "API Key 含有非ASCII字符，请检查是否误填中文说明。"
    if not key.startswith("sk-"):
        return False, "API Key 前缀看起来不是 sk-，请确认。"
    return True, f"已检测到 {provider_label(provider)} Key，长度 {len(key)}。"


def build_ai_prompt(market_state: dict[str, Any], strategy: dict[str, Any], rule_signal: dict[str, Any]) -> str:
    """构造AI提示词。JSON输出结构在这里修改；策略硬规则在 strategies/*.yaml 修改。"""
    allowed = strategy.get("allowed_actions") or ["WATCH", "NO_ACTION", "PAPER_BUY", "PAPER_ADD", "PAPER_SELL", "PAPER_CLEAR"]
    strategy_payload = {
        "strategy_id": strategy.get("strategy_id"),
        "strategy_name": strategy.get("strategy_name"),
        "strategy_type": strategy.get("strategy_type"),
        "version": strategy.get("version"),
        "description": strategy.get("description"),
        "allowed_actions": allowed,
        "parameters": strategy.get("parameters"),
        "hard_risk_rules": strategy.get("hard_risk_rules"),
        "buy_rules": strategy.get("buy_rules"),
        "add_rules": strategy.get("add_rules"),
        "sell_rules": strategy.get("sell_rules"),
        "clear_rules": strategy.get("clear_rules") or strategy.get("clear"),
        "risk_control": strategy.get("risk_control"),
        "ai_guidance": strategy.get("ai_guidance"),
    }
    return f"""
你是JZL证券分析的A股趋势波段虚拟交易员。你不是实盘操盘手，只能在虚拟盘里输出动作建议。
你必须服从代码规则引擎和审计器：脚本负责硬条件，AI负责解释交易质量与输出结构化交易语言。

【当前执行策略】
{json.dumps(strategy_payload, ensure_ascii=False, indent=2)}

【代码规则引擎触发结果】
{json.dumps(rule_signal, ensure_ascii=False, indent=2)}

【当前行情与虚拟持仓】
{json.dumps(market_state, ensure_ascii=False, indent=2)}

必须严格遵守：
1. 只能输出 JSON，不能输出 Markdown，不能输出代码块标记，不能输出解释性段落。
2. action 只能从当前策略 allowed_actions 里选择。
3. 如果 rule_signal.should_call_ai 为 false，只能输出 WATCH 或 NO_ACTION。
4. 如果 rule_signal.preferred_action 是 PAPER_CLEAR，不能输出 PAPER_BUY 或 PAPER_ADD。
5. 如果 intraday_status、volume_status、position_limit 任意一个为空，不允许 PAPER_BUY 或 PAPER_ADD。
6. PAPER_BUY、PAPER_ADD、PAPER_SELL、PAPER_CLEAR 必须带 order。
7. WATCH、NO_ACTION 的 order 必须为 null。
8. 不能创造新策略，只能按当前策略和代码引擎结果执行。
9. need_human_review 必须为 true。
10. reason 必须写具体交易语言；risk 必须写具体风险；execution_plan 写后续观察条件；invalid_if 写本次判断失效条件。

必须输出以下 JSON 字段：
{{
  "action": "",
  "code": "",
  "name": "",
  "strategy_id": "",
  "setup_type": "pullback_buy | breakout_buy | trend_resume | reduce_risk | clear_risk | watch",
  "confidence": "low | medium | high",
  "reason": [],
  "risk": [],
  "order": null,
  "execution_plan": [],
  "invalid_if": [],
  "review_note": "",
  "need_human_review": true
}}

order格式要求：
- PAPER_BUY / PAPER_ADD / PAPER_SELL / PAPER_CLEAR 时：{{"price_mode":"current_price", "position_pct": 数字}}
- WATCH / NO_ACTION 时：null

现在只输出 JSON。
"""


def _client_for(provider: str):
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"缺少 openai 依赖：{exc}")

    key = get_env_key(provider)
    if not key:
        env_name = "DEEPSEEK_API_KEY" if provider == PROVIDER_DEEPSEEK else "OPENAI_API_KEY"
        raise RuntimeError(f"未检测到 {env_name} 环境变量")
    if provider == PROVIDER_DEEPSEEK:
        return OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL, timeout=30.0, max_retries=1)
    if provider == PROVIDER_OPENAI:
        return OpenAI(api_key=key, timeout=30.0, max_retries=1)
    raise RuntimeError(f"未知AI_PROVIDER：{provider}")


def call_ai_json(
    prompt: str,
    provider: str = PROVIDER_DEEPSEEK,
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 1200,
) -> tuple[str, dict[str, Any]]:
    """返回 (原始文本, 解析后的JSON或错误对象)。"""
    provider = provider or PROVIDER_DEEPSEEK
    if provider == PROVIDER_DEEPSEEK:
        model = model or DEEPSEEK_MODEL_DEFAULT
    elif provider == PROVIDER_OPENAI:
        model = model or OPENAI_MODEL_DEFAULT
    else:
        return f"未知AI_PROVIDER：{provider}", {"action": "NO_ACTION", "reason": ["AI_PROVIDER不支持"], "risk": [str(provider)], "order": None, "need_human_review": True}

    try:
        client = _client_for(provider)
        kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": "你是严格执行固定策略的A股虚拟交易员。你只能输出JSON。数据不足时必须观察，不能买入。"},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        resp = client.chat.completions.create(**kwargs)
        raw = resp.choices[0].message.content or ""
    except Exception as exc:
        raw = f"{provider_label(provider)} 调用失败：{exc}"
        return raw, {"action": "NO_ACTION", "reason": ["AI调用失败"], "risk": [str(exc)], "order": None, "need_human_review": True}

    try:
        return raw, extract_json(raw)
    except Exception as exc:
        return raw, {"action": "NO_ACTION", "reason": ["AI输出不是合法JSON"], "risk": [str(exc)], "order": None, "need_human_review": True}
