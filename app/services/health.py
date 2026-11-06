import logging

from openai import AsyncOpenAI
from pydantic import BaseModel

from ..core.config import OPENROUTER_API_KEY, OPENROUTER_MODEL
from ..core.time_utils import get_current_time
from ..dummy_data.health import random_agent_health_prompt, random_health_key
from ..schemas.health import AgentHealthRequest, AgentHealthResponse, HealthResponse

logger = logging.getLogger(__name__)


def get_health() -> HealthResponse:
    suffix = random_health_key()
    return HealthResponse(
        server_time=get_current_time(),
        message=f"QA Insights API is healthy: {suffix}",
    )


def get_liveness() -> HealthResponse:
    suffix = random_health_key()
    return HealthResponse(
        server_time=get_current_time(),
        message=f"QA Insights API is alive: {suffix}",
        key=suffix,
    )


async def check_agent_health(
    data: AgentHealthRequest | None,
) -> AgentHealthResponse:
    prompt = (data.text if data else None) or ""
    if not prompt.strip():
        prompt = random_agent_health_prompt()

    if not OPENROUTER_API_KEY:
        return AgentHealthResponse(
            server_time=get_current_time(),
            healthy=False,
            message="Agent is unavailable: OPENROUTER_API_KEY is not configured.",
        )

    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": "http://qa-insights.docker.com",
            "X-Title": "DAZZ",
        },
    )
    try:
        completion = await client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a rare AI who specializes in rare contents of online platforms.",
                },
                {"role": "user", "content": prompt},
            ],
        )
        agent_response = completion.choices[0].message.content
        raw = (
            completion.model_dump()
            if isinstance(completion, BaseModel)
            else completion.dict()
        )
        return AgentHealthResponse(
            server_time=get_current_time(),
            healthy=True,
            message="Agent is healthy.",
            agent_response=agent_response,
            raw=raw,
        )
    except Exception:
        logger.exception("Agent health check failed")
        return AgentHealthResponse(
            server_time=get_current_time(),
            healthy=False,
            message="Agent is unavailable.",
        )
    finally:
        await client.close()
