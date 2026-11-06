from fastapi import APIRouter, Depends, Request, Response

from ...api.qa_dependencies import get_current_user
from ...core.keycloak import User
from ...services.test_reports_proxy import proxy_request

router = APIRouter(prefix="/api/test-reports", tags=["Test reports gateway"])
ALLOWED_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]


@router.get("/health")
async def reports_health(
    request: Request,
    _: User = Depends(get_current_user),
) -> Response:
    return await proxy_request(request, "health")


@router.api_route("/{path:path}", methods=ALLOWED_METHODS, include_in_schema=False)
async def proxy_test_reports(
    request: Request,
    path: str,
    _: User = Depends(get_current_user),
) -> Response:
    return await proxy_request(request, path)
