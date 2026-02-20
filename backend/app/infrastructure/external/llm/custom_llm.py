from typing import List, Dict, Any, Optional
from app.domain.external.llm import LLM
from app.core.config import get_settings
import httpx
import logging
import asyncio
import json

logger = logging.getLogger(__name__)


class CustomLLM(LLM):
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.api_key
        self.api_base = settings.api_base.rstrip("/")
        self._model_name = settings.model_name
        self._temperature = settings.temperature
        self._max_tokens = settings.max_tokens
        self._provider = settings.llm_provider
        logger.info(f"Initialized Custom LLM with model: {self._model_name}, provider: {self._provider}, base: {self.api_base}")

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    def _messages_to_text(self, messages: List[Dict[str, str]]) -> str:
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content:
                parts.append(f"[{role}]: {content}")
        return "\n".join(parts)

    def _build_tools_prompt(self, tools: Optional[List[Dict[str, Any]]] = None) -> str:
        if not tools:
            return ""
        
        tools_desc = "\n\nYou have access to the following tools:\n"
        for tool in tools:
            func = tool.get("function", {})
            name = func.get("name", "")
            desc = func.get("description", "")
            params = func.get("parameters", {})
            tools_desc += f"\n- {name}: {desc}"
            if params.get("properties"):
                tools_desc += f"\n  Parameters: {json.dumps(params['properties'], indent=2)}"
            required = params.get("required", [])
            if required:
                tools_desc += f"\n  Required: {', '.join(required)}"

        tools_desc += "\n\nTo use a tool, respond with JSON in this exact format:"
        tools_desc += '\n{"tool_calls": [{"function": {"name": "tool_name", "arguments": {"param": "value"}}}]}'
        tools_desc += "\n\nIf you don't need to use a tool, just respond normally with text."
        return tools_desc

    def _parse_tool_calls(self, text: str) -> Optional[List[Dict[str, Any]]]:
        try:
            text = text.strip()
            
            json_start = text.find("{")
            json_end = text.rfind("}") + 1
            if json_start == -1 or json_end == 0:
                return None
            
            json_str = text[json_start:json_end]
            data = json.loads(json_str)
            
            if "tool_calls" in data:
                tool_calls = []
                for i, tc in enumerate(data["tool_calls"]):
                    func = tc.get("function", {})
                    tool_calls.append({
                        "id": f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": func.get("name", ""),
                            "arguments": json.dumps(func.get("arguments", {}))
                        }
                    })
                return tool_calls
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        return None

    async def ask(self, messages: List[Dict[str, str]],
                  tools: Optional[List[Dict[str, Any]]] = None,
                  response_format: Optional[Dict[str, Any]] = None,
                  tool_choice: Optional[str] = None) -> Dict[str, Any]:
        max_retries = 3
        base_delay = 1.0
        connection_timeout = 30.0
        request_timeout = 120.0

        text = self._messages_to_text(messages)
        tools_prompt = self._build_tools_prompt(tools)
        if tools_prompt:
            text += tools_prompt

        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    import random
                    delay = base_delay * (2 ** (attempt - 1))
                    jitter = random.uniform(0, delay * 0.1)
                    delay += jitter
                    logger.info(f"Retrying Custom API request (attempt {attempt + 1}/{max_retries + 1}) after {delay:.2f}s delay")
                    await asyncio.sleep(delay)

                payload = {
                    "text": text,
                    "provider": self._provider,
                    "model": self._model_name
                }

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                }

                logger.debug(f"Sending request to Custom API: {self.api_base}/api/chat with payload model={self._model_name}, provider={self._provider}")

                timeout_config = httpx.Timeout(timeout=request_timeout, connect=connection_timeout)
                async with httpx.AsyncClient(timeout=timeout_config) as client:
                    response = await client.post(
                        f"{self.api_base}/api/chat",
                        json=payload,
                        headers=headers
                    )

                if response.status_code != 200:
                    error_msg = f"Custom API returned status {response.status_code} on attempt {attempt + 1}: {response.text[:500]}"
                    logger.error(error_msg)
                    if attempt == max_retries:
                        raise ValueError(f"Failed after {max_retries + 1} attempts: {error_msg}")
                    continue

                response_data = response.json()
                logger.debug(f"Response from Custom API (attempt {attempt + 1}): status=200, response_type={type(response_data).__name__}")

                content = ""
                if isinstance(response_data, str):
                    content = response_data
                elif isinstance(response_data, dict):
                    content = (
                        response_data.get("response") or
                        response_data.get("text") or
                        response_data.get("content") or
                        response_data.get("message") or
                        response_data.get("result") or
                        response_data.get("answer") or
                        json.dumps(response_data)
                    )
                    if isinstance(content, dict):
                        content = content.get("content", json.dumps(content))

                result = {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": None
                }

                if tools:
                    tool_calls = self._parse_tool_calls(content)
                    if tool_calls:
                        result["tool_calls"] = tool_calls
                        result["content"] = None

                return result

            except httpx.TimeoutException as e:
                error_msg = f"Custom API request timed out on attempt {attempt + 1}/{max_retries + 1}: {str(e)}"
                logger.error(error_msg)
                if attempt == max_retries:
                    raise ValueError(f"Failed after {max_retries + 1} attempts: {error_msg}")
                continue

            except Exception as e:
                error_msg = f"Error calling Custom API on attempt {attempt + 1}/{max_retries + 1}: {type(e).__name__}: {str(e)}"
                logger.error(error_msg)
                if attempt == max_retries:
                    raise ValueError(f"Failed after {max_retries + 1} attempts: {error_msg}") from e
                continue

        raise ValueError(f"Custom API request failed after {max_retries + 1} attempts")
