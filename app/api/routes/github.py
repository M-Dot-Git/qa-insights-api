from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from ...api.qa_dependencies import get_current_user
from ...core.keycloak import User
from ...services.github import GitHubAPIError, GitHubClient, GitHubClientFactory

router = APIRouter(prefix="/api/github", tags=["GitHub"])


def get_github_client() -> GitHubClient:
    return GitHubClientFactory.create_client()


def raise_api_error(error: GitHubAPIError) -> None:
    raise HTTPException(status_code=error.status_code, detail=str(error)) from error


@router.get("/repos")
async def list_repositories(
    _: User = Depends(get_current_user),
    github: GitHubClient = Depends(get_github_client),
) -> list[dict[str, str]]:
    return github.configured_repos()


@router.get("/prs")
async def list_pull_requests(
    repo: Annotated[str, Query(min_length=3, max_length=200)],
    state: str = Query(default="open", pattern="^(?i:open|closed)$"),
    first: int = Query(default=20, ge=1, le=100),
    after: str | None = Query(default=None, max_length=500),
    _: User = Depends(get_current_user),
    github: GitHubClient = Depends(get_github_client),
) -> dict:
    try:
        return await github.list_pull_requests(repo, state, first, after)
    except GitHubAPIError as error:
        raise_api_error(error)


@router.get("/prs/{number}")
async def pull_request_detail(
    number: int,
    repo: Annotated[str, Query(min_length=3, max_length=200)],
    _: User = Depends(get_current_user),
    github: GitHubClient = Depends(get_github_client),
) -> dict:
    if number < 1:
        raise HTTPException(status_code=422, detail="Pull request number must be positive.")
    try:
        return await github.pull_request_detail(repo, number)
    except GitHubAPIError as error:
        raise_api_error(error)
