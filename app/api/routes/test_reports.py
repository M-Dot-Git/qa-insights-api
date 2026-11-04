import logging
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ...api.qa_dependencies import get_current_user
from ...core.config import TEST_REPORTS_API_URL
from ...core.keycloak import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/test-reports", tags=["Test reports gateway"])
UPSTREAM_TIMEOUT_SECONDS = 15.0
ALLOWED_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"]
FORWARDED_REQUEST_HEADERS = ("accept", "authorization", "content-type")
FORWARDED_RESPONSE_HEADERS = ("cache-control", "content-disposition", "content-type")


@router.get("/health")
async def test_reports_health(
    request: Request,
    _: User = Depends(get_current_user),
) -> Response:
    return await _proxy_request(request, "health")


@router.api_route("/{path:path}", methods=ALLOWED_METHODS, include_in_schema=False)
async def proxy_test_reports(
    request: Request,
    path: str,
    _: User = Depends(get_current_user),
) -> Response:
    return await _proxy_request(request, path)


async def _proxy_request(request: Request, path: str) -> Response:
    if not TEST_REPORTS_API_URL:
        raise HTTPException(
            status_code=503,
            detail="The test reports service is not configured.",
        )

    headers = {
        name: value
        for name in FORWARDED_REQUEST_HEADERS
        if (value := request.headers.get(name)) is not None
    }
    upstream_path = f"/api/test-reports/{quote(path, safe='/')}"
    upstream_url = f"{TEST_REPORTS_API_URL}{upstream_path}"
    try:
        async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_SECONDS) as client:
            upstream_response = await client.request(
                request.method,
                upstream_url,
                params=list(request.query_params.multi_items()),
                content=await request.body(),
                headers=headers,
            )
    except httpx.TimeoutException as error:
        logger.warning("Test reports service request timed out.")
        raise HTTPException(
            status_code=504,
            detail="The test reports service timed out.",
        ) from error
    except httpx.RequestError as error:
        logger.warning("Test reports service request failed (%s).", type(error).__name__)
        raise HTTPException(
            status_code=503,
            detail="The test reports service is unavailable.",
        ) from error

    response_headers = {
        name: upstream_response.headers[name]
        for name in FORWARDED_RESPONSE_HEADERS
        if name in upstream_response.headers
    }
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
    )
