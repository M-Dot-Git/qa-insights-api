import logging
import secrets
import string

from fastapi import APIRouter, Response
from openai import AsyncOpenAI

from ...core.config import OPENROUTER_API_KEY, OPENROUTER_MODEL
from ...core.time_utils import get_current_time
from ...schemas.health import AgentHealthRequest, AgentHealthResponse, HealthResponse

router = APIRouter(tags=["health"])

logger = logging.getLogger(__name__)
AGENT_HEALTH_PROMPTS = (
    "Reply with a brief greeting.",
    "In one sentence, describe what you can help with.",
    "Say hello and confirm you are available.",
)

@router.get("/health", response_model=HealthResponse, response_model_exclude_none=True)
async def health() -> HealthResponse:
    suffix = "".join(
        secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10)
    )
    return HealthResponse(
        server_time=get_current_time(),
        message=f"QA Insights API is healthy: {suffix}",
    )

@router.get("/health/liveness")
async def liveness() :
    suffix = "".join(
        secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10)
    )
    return HealthResponse(
        server_time=get_current_time(),
        message=f"QA Insights API is alive: {suffix}",
        key=suffix
    )

@router.post("/health/agent")
async def agent_health(
    response: Response,
    data: AgentHealthRequest | None = None,
) -> AgentHealthResponse:
    prompt = (data.text if data else None) or ""
    if not prompt.strip():
        prompt = secrets.choice(AGENT_HEALTH_PROMPTS)

    if not OPENROUTER_API_KEY:
        response.status_code = 503
        return AgentHealthResponse(
            server_time=get_current_time(),
            healthy=False,
            message="Agent is unavailable: OPENROUTER_API_KEY is not configured.",
        )

    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": "http://muz.postman.com",
            "X-Title": "DAZZ",
        },
    )
    try:
        completion = await client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=[
                {"role": "system", "content": "You are a rare AI who specializes in rare contents of online platforms."},
                {"role": "user", "content": prompt},
            ],
        )
        agent_response = completion.choices[0].message.content
        return AgentHealthResponse(
            server_time=get_current_time(),
            healthy=True,
            message="Agent is healthy.",
            agent_response=agent_response,
            raw=completion.dict(),
        )
    except Exception:
        logger.exception("Agent health check failed")
        response.status_code = 503
        return AgentHealthResponse(
            server_time=get_current_time(),
            healthy=False,
            message="Agent is unavailable.",
        )
    finally:
        await client.close()