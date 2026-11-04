from fastapi import APIRouter, Response

from ...services import health as health_service
from ...schemas.health import AgentHealthRequest, AgentHealthResponse, HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, response_model_exclude_none=True)
async def health() -> HealthResponse:
    return health_service.get_health()

@router.get("/health/liveness")
async def liveness() -> HealthResponse:
    return health_service.get_liveness()

@router.post("/health/agent")
async def agent_health(
    response: Response,
    data: AgentHealthRequest | None = None,
) -> AgentHealthResponse:
    result = await health_service.check_agent_health(data)
    if not result.healthy:
        response.status_code = 503
    return result