"""GitHub pull request integration."""

import asyncio
import logging
import re
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..core.config import GITHUB_ALLOWED_REPOS, GITHUB_GRAPHQL_URL, GITHUB_TOKEN

logger = logging.getLogger(__name__)
CACHE_TTL_SECONDS = 45
LOW_RATE_LIMIT_THRESHOLD = 100
MAX_FILES = 3000
MAX_REST_CACHE_ENTRIES = 5000
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
GRAPHQL_ERRORS = {
    "list": """
query PullRequests($owner: String!, $name: String!, $states: [PullRequestState!], $first: Int!, $after: String) {
  rateLimit { cost remaining resetAt }
  repository(owner: $owner, name: $name) {
    pullRequests(states: $states, first: $first, after: $after, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        number title isDraft url createdAt updatedAt author { login avatarUrl }
        headRefName baseRefName labels(first: 10) { nodes { name color } }
        reviewDecision additions deletions changedFiles
        commits(last: 1) { nodes { commit { statusCheckRollup { state } } } }
      }
    }
  }
}
""",
    "detail": """
query PullRequestDetail($owner: String!, $name: String!, $number: Int!) {
  rateLimit { cost remaining resetAt }
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      number title body state isDraft merged mergeable url createdAt updatedAt
      author { login avatarUrl } baseRefName headRefName headRefOid
      labels(first: 10) { nodes { name color } }
      reviewDecision
      reviewRequests(first: 20) { nodes { requestedReviewer { ... on User { login } ... on Team { name } } } }
      latestOpinionatedReviews(first: 20) { nodes { author { login avatarUrl } state submittedAt body } }
      reviews(first: 50) { nodes { author { login } state submittedAt body } }
      reviewThreads(first: 50) {
        nodes { isResolved isOutdated path line comments(first: 20) { nodes { author { login } body createdAt } } }
      }
      comments(first: 50) { nodes { author { login } body createdAt } }
      files(first: 100) { pageInfo { hasNextPage endCursor } nodes { path additions deletions changeType } }
      commits(last: 1) {
        nodes { commit {
          oid statusCheckRollup {
            state
            contexts(first: 50) { nodes {
              ... on CheckRun { name status conclusion detailsUrl }
              ... on StatusContext { context state targetUrl }
            } }
          }
        } }
      }
    }
  }
}
""",
    "files": """
query PullRequestFiles($owner: String!, $name: String!, $number: Int!, $after: String!) {
  rateLimit { cost remaining resetAt }
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      files(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes { path additions deletions changeType }
      }
    }
  }
}
""",
}


class GitHubAPIError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class GitHubClient:
    def __init__(self, token: str, graphql_url: str, allowed_repos: list[str]) -> None:
        self.token = token
        self.graphql_url = graphql_url
        self.allowed_repos = {
            repo.lower(): repo for repo in allowed_repos if REPO_PATTERN.fullmatch(repo)
        }
        self._list_cache: dict[tuple[str, str, int, str | None], tuple[float, dict[str, Any]]] = {}
        self._detail_cache: dict[tuple[str, int], tuple[float, dict[str, Any]]] = {}
        self._rest_cache: dict[
            str, tuple[str | None, list[dict[str, Any]], str | None]
        ] = {}

    def configured_repos(self) -> list[dict[str, str]]:
        return [
            {"owner": owner, "repo": name, "fullName": f"{owner}/{name}"}
            for full_name in sorted(self.allowed_repos.values(), key=str.lower)
            for owner, name in [full_name.split("/", 1)]
        ]

    def validate_repo(self, repo: str) -> tuple[str, str]:
        if not REPO_PATTERN.fullmatch(repo) or repo.lower() not in self.allowed_repos:
            raise GitHubAPIError(403, "This repository is not in the GitHub allowlist.")
        owner, name = repo.split("/", 1)
        return owner, name

    def _expire_response_caches(self) -> None:
        now = time.monotonic()
        self._list_cache = {
            key: value for key, value in self._list_cache.items() if value[0] > now
        }
        self._detail_cache = {
            key: value for key, value in self._detail_cache.items() if value[0] > now
        }

    async def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        if not self.token:
            raise GitHubAPIError(503, "GitHub integration is not configured.")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.graphql_url,
                    json={"query": query, "variables": variables},
                    headers={"Authorization": f"Bearer {self.token}"},
                )
        except httpx.RequestError as error:
            raise GitHubAPIError(502, "Could not connect to GitHub.") from error
        if response.status_code != 200:
            raise self._http_error(response)
        try:
            payload = response.json()
        except ValueError as error:
            raise GitHubAPIError(502, "GitHub returned an invalid response.") from error
        if not isinstance(payload, dict):
            raise GitHubAPIError(502, "GitHub returned an invalid response.")
        if payload.get("errors"):
            error = self._graphql_error(payload["errors"])
            raise error
        data = payload.get("data")
        if not isinstance(data, dict):
            raise GitHubAPIError(502, "GitHub returned an invalid response.")
        rate_limit = data.get("rateLimit") or {}
        remaining = rate_limit.get("remaining")
        if isinstance(remaining, int) and remaining < LOW_RATE_LIMIT_THRESHOLD:
            logger.warning(
                "GitHub GraphQL rate limit is low: %s requests remain; reset at %s",
                remaining,
                rate_limit.get("resetAt"),
            )
        return data

    @staticmethod
    def _graphql_error(errors: list[dict[str, Any]]) -> GitHubAPIError:
        first = errors[0] if errors else {}
        extensions = first.get("extensions") or {}
        kind = str(extensions.get("type") or extensions.get("code") or "").upper()
        message = str(first.get("message") or "GitHub rejected the request.")
        lowered = message.lower()
        if kind in {"NOT_FOUND", "NOTFOUND"} or "could not resolve to" in lowered:
            return GitHubAPIError(404, "Repository or pull request not found.")
        if kind in {"FORBIDDEN", "RESOURCE_NOT_ACCESSIBLE"}:
            return GitHubAPIError(403, "GitHub denied access to this resource.")
        if kind in {"UNAUTHENTICATED", "BAD_CREDENTIALS", "BAD_CREDENTIAL"}:
            return GitHubAPIError(401, "GitHub rejected the configured credentials.")
        if kind in {"RATE_LIMITED", "RATE_LIMIT", "ABUSE_DETECTED"} or "rate limit" in lowered:
            return GitHubAPIError(429, "GitHub API rate limit exceeded. Try again later.")
        if "bad credentials" in lowered or "authentication" in lowered:
            return GitHubAPIError(401, "GitHub rejected the configured credentials.")
        if "resource not accessible" in lowered or "forbidden" in lowered:
            return GitHubAPIError(403, "GitHub denied access to this resource.")
        return GitHubAPIError(502, "GitHub GraphQL request failed.")

    @staticmethod
    def _http_error(response: httpx.Response) -> GitHubAPIError:
        if response.status_code == 401:
            return GitHubAPIError(401, "GitHub rejected the configured credentials.")
        if response.status_code == 404:
            return GitHubAPIError(404, "Repository or pull request not found.")
        if response.status_code in {403, 429}:
            if (
                response.status_code == 429
                or response.headers.get("X-RateLimit-Remaining") == "0"
                or "rate limit" in response.text.lower()
            ):
                return GitHubAPIError(429, "GitHub API rate limit exceeded. Try again later.")
            return GitHubAPIError(403, "GitHub denied access to this resource.")
        return GitHubAPIError(502, "GitHub API request failed.")

    async def list_pull_requests(
        self, repo: str, state: str, first: int, after: str | None
    ) -> dict[str, Any]:
        owner, name = self.validate_repo(repo)
        self._expire_response_caches()
        key = (repo.lower(), state, first, after)
        cached = self._list_cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        data = await self.graphql(
            GRAPHQL_ERRORS["list"],
            {
                "owner": owner,
                "name": name,
                "states": [state.upper()],
                "first": first,
                "after": after,
            },
        )
        repository = data.get("repository")
        if not repository:
            raise GitHubAPIError(404, "Repository not found.")
        pull_requests = repository["pullRequests"]
        result = {
            "items": [
                {
                    "repo": repo,
                    "number": pr["number"],
                    "title": pr["title"],
                    "isDraft": pr["isDraft"],
                    "url": pr["url"],
                    "author": pr.get("author"),
                    "labels": pr["labels"]["nodes"],
                    "headRef": pr["headRefName"],
                    "baseRef": pr["baseRefName"],
                    "createdAt": pr["createdAt"],
                    "updatedAt": pr["updatedAt"],
                    "reviewDecision": pr.get("reviewDecision"),
                    "additions": pr["additions"],
                    "deletions": pr["deletions"],
                    "changedFiles": pr["changedFiles"],
                    "ciState": self._ci_state(pr),
                }
                for pr in pull_requests["nodes"]
            ],
            "totalCount": pull_requests["totalCount"],
            "hasNext": pull_requests["pageInfo"]["hasNextPage"],
            "endCursor": pull_requests["pageInfo"]["endCursor"],
        }
        self._list_cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, result)
        return result

    @staticmethod
    def _ci_state(pull_request: dict[str, Any]) -> str | None:
        commits = pull_request.get("commits", {}).get("nodes", [])
        if not commits:
            return None
        rollup = commits[-1].get("commit", {}).get("statusCheckRollup")
        return rollup.get("state") if rollup else None

    async def pull_request_detail(self, repo: str, number: int) -> dict[str, Any]:
        owner, name = self.validate_repo(repo)
        if not self.token:
            raise GitHubAPIError(503, "GitHub integration is not configured.")
        self._expire_response_caches()
        key = (repo.lower(), number)
        cached = self._detail_cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]

        gql_task = self._detail_graphql(owner, name, number)
        rest_task = self._rest_files(owner, name, number)
        data, rest_files = await asyncio.gather(gql_task, rest_task)
        pull_request = data.get("repository", {}).get("pullRequest")
        if pull_request is None:
            raise GitHubAPIError(404, "Pull request not found.")
        if pull_request.get("mergeable") == "UNKNOWN":
            await asyncio.sleep(0.2)
            data = await self._detail_graphql(owner, name, number)
            pull_request = data.get("repository", {}).get("pullRequest")
            if pull_request is None:
                raise GitHubAPIError(404, "Pull request not found.")

        files = self._merge_files(pull_request.get("files", []), rest_files)
        commits = pull_request.get("commits", {}).get("nodes", [])
        commit = commits[-1]["commit"] if commits else {}
        rollup = commit.get("statusCheckRollup")
        result = {
            "repo": repo,
            "number": pull_request["number"],
            "title": pull_request["title"],
            "bodyMarkdown": pull_request.get("body"),
            "state": pull_request["state"],
            "merged": pull_request["merged"],
            "isDraft": pull_request["isDraft"],
            "mergeable": pull_request.get("mergeable"),
            "url": pull_request["url"],
            "author": pull_request.get("author"),
            "createdAt": pull_request["createdAt"],
            "updatedAt": pull_request["updatedAt"],
            "baseRef": pull_request["baseRefName"],
            "headRef": pull_request["headRefName"],
            "headSha": pull_request["headRefOid"],
            "labels": pull_request["labels"]["nodes"],
            "approvals": {
                "reviewDecision": pull_request.get("reviewDecision"),
                "requested": self._requested_reviewers(pull_request),
                "reviews": [
                    self._review(review) for review in pull_request["reviews"]["nodes"]
                ],
            },
            "reviewThreads": [
                {
                    "path": thread["path"],
                    "line": thread.get("line"),
                    "isResolved": thread["isResolved"],
                    "isOutdated": thread["isOutdated"],
                    "comments": [
                        self._comment(comment) for comment in thread["comments"]["nodes"]
                    ],
                }
                for thread in pull_request["reviewThreads"]["nodes"]
            ],
            "conversation": [
                self._comment(comment) for comment in pull_request["comments"]["nodes"]
            ],
            "files": files,
            "ci": {
                "state": rollup.get("state") if rollup else None,
                "checks": self._checks(rollup),
            },
        }
        self._detail_cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, result)
        return result

    async def _detail_graphql(
        self, owner: str, name: str, number: int
    ) -> dict[str, Any]:
        variables = {"owner": owner, "name": name, "number": number}
        data = await self.graphql(GRAPHQL_ERRORS["detail"], variables)
        pull_request = data.get("repository", {}).get("pullRequest")
        if pull_request is None:
            return data
        files = pull_request["files"]
        nodes = files["nodes"]
        cursor = files["pageInfo"]["endCursor"]
        while files["pageInfo"]["hasNextPage"] and cursor and len(nodes) < MAX_FILES:
            page = await self.graphql(
                GRAPHQL_ERRORS["files"],
                {**variables, "after": cursor},
            )
            next_pr = page.get("repository", {}).get("pullRequest")
            if next_pr is None:
                raise GitHubAPIError(404, "Pull request not found.")
            files = next_pr["files"]
            nodes.extend(files["nodes"][: MAX_FILES - len(nodes)])
            cursor = files["pageInfo"]["endCursor"]
        return data

    async def _rest_files(self, owner: str, name: str, number: int) -> list[dict[str, Any]]:
        url = f"https://api.github.com/repos/{owner}/{name}/pulls/{number}/files?per_page=100"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        result: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            while url and len(result) < MAX_FILES:
                etag, previous, cached_next_url = self._rest_cache.get(
                    url, (None, [], None)
                )
                request_headers = dict(headers)
                if etag:
                    request_headers["If-None-Match"] = etag
                try:
                    response = await client.get(url, headers=request_headers)
                except httpx.RequestError as error:
                    raise GitHubAPIError(502, "Could not connect to GitHub.") from error
                if response.status_code == 304:
                    page_files = previous
                    next_url = (
                        self._next_link(response.headers.get("Link", ""))
                        or cached_next_url
                    )
                elif response.is_success:
                    try:
                        page_files = response.json()
                    except ValueError as error:
                        raise GitHubAPIError(502, "GitHub returned an invalid response.") from error
                    if not isinstance(page_files, list):
                        raise GitHubAPIError(502, "GitHub returned an invalid response.")
                    next_url = self._next_link(response.headers.get("Link", ""))
                    self._rest_cache[url] = (
                        response.headers.get("ETag"),
                        page_files,
                        next_url,
                    )
                    while len(self._rest_cache) > MAX_REST_CACHE_ENTRIES:
                        self._rest_cache.pop(next(iter(self._rest_cache)))
                else:
                    raise self._http_error(response)
                result.extend(page_files[: MAX_FILES - len(result)])
                url = next_url
        return result

    @staticmethod
    def _next_link(link_header: str) -> str | None:
        for part in link_header.split(","):
            url, *attributes = part.split(";")
            if any(attribute.strip() == 'rel="next"' for attribute in attributes):
                next_url = url.strip().strip("<>")
                parsed = urlsplit(next_url)
                if parsed.scheme != "https" or parsed.netloc != "api.github.com":
                    raise GitHubAPIError(502, "GitHub returned an invalid pagination link.")
                return next_url
        return None

    @staticmethod
    def _merge_files(
        graphql_files: dict[str, Any], rest_files: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        patches = {item["filename"]: item for item in rest_files}
        return [
            {
                "filename": item["path"],
                "status": {
                    "ADDED": "added",
                    "DELETED": "removed",
                    "MODIFIED": "modified",
                    "RENAMED": "renamed",
                    "COPIED": "copied",
                    "CHANGED": "changed",
                }.get(item["changeType"], item["changeType"].lower()),
                "additions": item["additions"],
                "deletions": item["deletions"],
                "patch": patches.get(item["path"], {}).get("patch"),
                "truncated": patches.get(item["path"], {}).get("patch") is None,
            }
            for item in graphql_files.get("nodes", [])[:MAX_FILES]
        ]

    @staticmethod
    def _requested_reviewers(pull_request: dict[str, Any]) -> list[dict[str, str]]:
        requested = []
        for node in pull_request["reviewRequests"]["nodes"]:
            reviewer = node.get("requestedReviewer") or {}
            if "login" in reviewer:
                requested.append({"type": "user", "name": reviewer["login"]})
            elif "name" in reviewer:
                requested.append({"type": "team", "name": reviewer["name"]})
        return requested

    @staticmethod
    def _review(review: dict[str, Any]) -> dict[str, Any]:
        return {
            "author": review.get("author"),
            "state": review["state"],
            "submittedAt": review.get("submittedAt"),
            "body": review.get("body"),
        }

    @staticmethod
    def _comment(comment: dict[str, Any]) -> dict[str, Any]:
        return {
            "author": comment.get("author"),
            "body": comment["body"],
            "createdAt": comment["createdAt"],
        }

    @staticmethod
    def _checks(rollup: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not rollup:
            return []
        contexts = rollup.get("contexts", {}).get("nodes", [])
        checks = []
        for check in contexts:
            if "name" in check:
                checks.append(
                    {
                        "name": check["name"],
                        "status": check.get("status"),
                        "conclusion": check.get("conclusion"),
                        "url": check.get("detailsUrl"),
                    }
                )
            else:
                checks.append(
                    {
                        "name": check["context"],
                        "status": check.get("state"),
                        "conclusion": None,
                        "url": check.get("targetUrl"),
                    }
                )
        return checks


class GitHubClientFactory:
    """Creates clients from the configured GitHub integration settings."""

    _client: GitHubClient | None = None

    @staticmethod
    def create_client() -> GitHubClient:
        if GitHubClientFactory._client is None:
            GitHubClientFactory._client = GitHubClient(
                GITHUB_TOKEN, GITHUB_GRAPHQL_URL, GITHUB_ALLOWED_REPOS
            )
        return GitHubClientFactory._client
