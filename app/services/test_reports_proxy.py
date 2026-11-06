import logging
from urllib.parse import quote

import httpx
from fastapi import HTTPException, Request, Response

from ..core.config import TEST_REPORTS_API_URL

logger = logging.getLogger(__name__)
UPSTREAM_TIMEOUT_SECONDS = 15.0
FORWARDED_REQUEST_HEADERS = ("accept", "authorization", "content-type")
FORWARDED_RESPONSE_HEADERS = ("cache-control", "content-disposition", "content-type")


async def proxy_request(request: Request, path: str) -> Response:
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
    upstream_path = (
        "/health"
        if path == "health"
        else f"/api/test-reports/{quote(path, safe='/')}"
    )
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
