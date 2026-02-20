from typing import List, Dict, Any, Optional
from app.domain.external.llm import LLM
from app.core.config import get_settings
import httpx
import logging
import asyncio
import json
import re
import random

logger = logging.getLogger(__name__)

CITATION_PATTERN = re.compile(r"(\n>\s*\[\d+\]\s*\[.*?\]\(.*?\)\s*)+\s*$", re.DOTALL)


class CustomLLM(LLM):
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.api_key
        self.api_base = settings.api_base.rstrip("/")
        self._model_name = settings.model_name
        self._temperature = settings.temperature
        self._max_tokens = settings.max_tokens
        self._provider = settings.llm_provider
        logger.info(
            f"Initialized Custom LLM with model: {self._model_name}, "
            f"provider: {self._provider}, base: {self.api_base}"
        )

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    def _strip_citations(self, text: str) -> str:
        if not text:
            return text
        return CITATION_PATTERN.sub("", text).rstrip()

    def _build_tools_system_message(self, tools: List[Dict[str, Any]]) -> Dict[str, str]:
        lines = [
            "You have access to the following tools:\n"
        ]
        for tool in tools:
            func = tool.get("function", {})
            name = func.get("name", "")
            desc = func.get("description", "")
            params = func.get("parameters", {})
            lines.append(f"- {name}: {desc}")
            if params.get("properties"):
                lines.append(f"  Parameters: {json.dumps(params['properties'], indent=2)}")
            required = params.get("required", [])
            if required:
                lines.append(f"  Required: {', '.join(required)}")

        lines.append("")
        lines.append(
            'To use a tool, respond ONLY with a JSON object in this format: '
            '{"tool_calls": [{"function": {"name": "tool_name", "arguments": {"param": "value"}}}]}'
        )
        lines.append("If you don't need to use a tool, respond normally with text.")

        return {"role": "system", "content": "\n".join(lines)}

    def _convert_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        converted = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "tool":
                tool_call_id = msg.get("tool_call_id", "unknown")
                tool_name = msg.get("name", "tool")
                converted.append({
                    "role": "user",
                    "content": f"[Tool Result for {tool_name} (call_id: {tool_call_id})]: {content}"
                })
            elif role == "assistant" and msg.get("tool_calls"):
                tc_summary = []
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    tc_obj = {
                        "tool_calls": [{
                            "function": {
                                "name": fn.get("name", ""),
                                "arguments": fn.get("arguments", "{}")
                            }
                        }]
                    }
                    tc_summary.append(json.dumps(tc_obj))
                converted.append({
                    "role": "assistant",
                    "content": "\n".join(tc_summary) if tc_summary else (content or "")
                })
            else:
                if role not in ("system", "user", "assistant"):
                    role = "user"
                converted.append({
                    "role": role,
                    "content": content or ""
                })
        return converted

    def _parse_tool_calls(self, text: str) -> Optional[List[Dict[str, Any]]]:
        if not text:
            return None
        try:
            stripped = text.strip()
            json_start = stripped.find("{")
            json_end = stripped.rfind("}") + 1
            if json_start == -1 or json_end == 0:
                return None

            json_str = stripped[json_start:json_end]
            data = json.loads(json_str)

            if "tool_calls" in data:
                tool_calls = []
                for i, tc in enumerate(data["tool_calls"]):
                    func = tc.get("function", {})
                    arguments = func.get("arguments", {})
                    if isinstance(arguments, dict):
                        arguments = json.dumps(arguments)
                    elif not isinstance(arguments, str):
                        arguments = json.dumps(arguments)
                    tool_calls.append({
                        "id": f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": func.get("name", ""),
                            "arguments": arguments
                        }
                    })
                return tool_calls if tool_calls else None
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        return None

    async def ask(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        tool_choice: Optional[str] = None,
    ) -> Dict[str, Any]:
        max_retries = 3
        base_delay = 1.0
        connection_timeout = 30.0
        request_timeout = 120.0

        api_messages = self._convert_messages(messages)

        if tools:
            tools_msg = self._build_tools_system_message(tools)
            insert_idx = 0
            for i, m in enumerate(api_messages):
                if m["role"] == "system":
                    insert_idx = i + 1
                else:
                    break
            api_messages.insert(insert_idx, tools_msg)

        if response_format and response_format.get("type") == "json_object":
            json_instruction = {
                "role": "system",
                "content": (
                    "You MUST respond ONLY with valid JSON. "
                    "Do not include any explanation, markdown formatting, or text outside the JSON object. "
                    "Your entire response must be parseable as JSON."
                ),
            }
            insert_idx = 0
            for i, m in enumerate(api_messages):
                if m["role"] == "system":
                    insert_idx = i + 1
                else:
                    break
            api_messages.insert(insert_idx, json_instruction)

        payload = {
            "model": self._model_name,
            "messages": api_messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))
                    jitter = random.uniform(0, delay * 0.1)
                    delay += jitter
                    logger.info(
                        f"Retrying Custom API request (attempt {attempt + 1}/{max_retries + 1}) "
                        f"after {delay:.2f}s delay"
                    )
                    await asyncio.sleep(delay)

                logger.debug(
                    f"Sending request to Custom API: {self.api_base}/v1/chat/completions "
                    f"with model={self._model_name}"
                )

                timeout_config = httpx.Timeout(
                    timeout=request_timeout, connect=connection_timeout
                )
                async with httpx.AsyncClient(timeout=timeout_config) as client:
                    response = await client.post(
                        f"{self.api_base}/v1/chat/completions",
                        json=payload,
                        headers=headers,
                    )

                if response.status_code != 200:
                    error_msg = (
                        f"Custom API returned status {response.status_code} on attempt "
                        f"{attempt + 1}: {response.text[:500]}"
                    )
                    logger.error(error_msg)
                    if attempt == max_retries:
                        raise ValueError(
                            f"Failed after {max_retries + 1} attempts: {error_msg}"
                        )
                    continue

                response_data = response.json()
                logger.debug(
                    f"Response from Custom API (attempt {attempt + 1}): status=200"
                )

                content = ""
                if isinstance(response_data, dict):
                    choices = response_data.get("choices", [])
                    if choices:
                        message = choices[0].get("message", {})
                        content = message.get("content", "")
                    else:
                        content = (
                            response_data.get("data")
                            or response_data.get("response")
                            or response_data.get("text")
                            or response_data.get("content")
                            or json.dumps(response_data)
                        )
                elif isinstance(response_data, str):
                    content = response_data

                if isinstance(content, dict):
                    content = content.get("content", json.dumps(content))

                content = self._strip_citations(content)

                result: Dict[str, Any] = {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": None,
                }

                if tools:
                    tool_calls = self._parse_tool_calls(content)
                    if tool_calls:
                        result["tool_calls"] = tool_calls
                        result["content"] = None

                return result

            except httpx.TimeoutException as e:
                error_msg = (
                    f"Custom API request timed out on attempt "
                    f"{attempt + 1}/{max_retries + 1}: {str(e)}"
                )
                logger.error(error_msg)
                if attempt == max_retries:
                    raise ValueError(
                        f"Failed after {max_retries + 1} attempts: {error_msg}"
                    )
                continue

            except Exception as e:
                error_msg = (
                    f"Error calling Custom API on attempt "
                    f"{attempt + 1}/{max_retries + 1}: {type(e).__name__}: {str(e)}"
                )
                logger.error(error_msg)
                if attempt == max_retries:
                    raise ValueError(
                        f"Failed after {max_retries + 1} attempts: {error_msg}"
                    ) from e
                continue

        raise ValueError(
            f"Custom API request failed after {max_retries + 1} attempts"
        )
