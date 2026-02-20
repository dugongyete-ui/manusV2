from fastapi import APIRouter
from app.interfaces.schemas.base import APIResponse
from app.core.config import get_settings
import httpx
import logging
import time

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=APIResponse)
async def health_check():
    settings = get_settings()
    status = {
        "status": "ok",
        "llm_type": settings.llm_type,
        "llm_provider": settings.llm_provider,
        "model": settings.model_name,
        "api_base": settings.api_base[:50] + "..." if len(settings.api_base) > 50 else settings.api_base,
        "has_api_key": bool(settings.api_key),
    }
    return APIResponse.success(data=status)


@router.get("/llm", response_model=APIResponse)
async def llm_health_check():
    settings = get_settings()
    start_time = time.time()

    try:
        if settings.llm_type == "custom":
            api_base = settings.api_base.rstrip("/")
            payload = {
                "text": "Hello, respond with just 'OK' in one word.",
                "provider": settings.llm_provider,
                "model": settings.model_name
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.api_key}"
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{api_base}/api/chat",
                    json=payload,
                    headers=headers
                )

            elapsed = round(time.time() - start_time, 2)

            if response.status_code == 200:
                return APIResponse.success(data={
                    "status": "connected",
                    "provider": settings.llm_provider,
                    "model": settings.model_name,
                    "response_time_seconds": elapsed,
                    "response_preview": str(response.text)[:200]
                })
            else:
                return APIResponse.error(
                    code=response.status_code,
                    msg=f"LLM API returned {response.status_code}: {response.text[:200]}"
                )
        else:
            return APIResponse.success(data={
                "status": "configured",
                "type": "openai",
                "model": settings.model_name,
                "has_api_key": bool(settings.api_key)
            })

    except httpx.TimeoutException:
        elapsed = round(time.time() - start_time, 2)
        return APIResponse.error(code=504, msg=f"LLM API timed out after {elapsed}s")
    except Exception as e:
        elapsed = round(time.time() - start_time, 2)
        logger.error(f"LLM health check failed: {e}")
        return APIResponse.error(code=500, msg=f"LLM health check failed: {str(e)[:200]}")
