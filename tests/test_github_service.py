import asyncio
import time

import pytest

import app.services.github as github_service
from app.services.github import CACHE_TTL_SECONDS, GitHubAPIError, GitHubClient


def _client() -> GitHubClient:
    client = GitHubClient("test-token", "https://example.test/graphql")
    client._repositories_cache = (
        time.monotonic() + CACHE_TTL_SECONDS,
        [{"owner": "Acme", "repo": "widgets", "fullName": "Acme/widgets"}],
    )
    return client


@pytest.mark.parametrize(
    ("extensions", "message", "status"),
    [
        ({"type": "NOT_FOUND"}, "Not found", 404),
        ({"type": "FORBIDDEN"}, "Forbidden", 403),
        ({"type": "UNAUTHENTICATED"}, "Unauthorized", 401),
        ({"type": "RATE_LIMITED"}, "Limit reached", 429),
    ],
)
def test_graphql_errors_map_to_clear_http_errors(extensions, message, status) -> None:
    error = GitHubClient._graphql_error(
        [{"extensions": extensions, "message": message}]
    )

    assert error.status_code == status
    assert str(error)


def test_http_200_graphql_errors_are_not_treated_as_success(monkeypatch) -> None:
    class MockAsyncClient:
        def __init__(self, *, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            import httpx

            request = httpx.Request("POST", "https://example.test/graphql")
            return httpx.Response(
                200,
                json={
                    "errors": [
                        {
                            "message": "Bad credentials",
                            "extensions": {"type": "UNAUTHENTICATED"},
                        }
                    ]
                },
                request=request,
            )

    monkeypatch.setattr(github_service.httpx, "AsyncClient", MockAsyncClient)
    with pytest.raises(GitHubAPIError) as error:
        asyncio.run(_client().graphql("query { viewer { login } }", {}))

    assert error.value.status_code == 401


def test_pull_request_list_is_normalized_and_uses_cursor(monkeypatch) -> None:
    client = _client()
    captured = {}

    async def fake_graphql(_query, variables):
        captured.update(variables)
        return {
            "repository": {
                "pullRequests": {
                    "totalCount": 1,
                    "pageInfo": {"hasNextPage": True, "endCursor": "next-cursor"},
                    "nodes": [
                        {
                            "number": 7,
                            "title": "Feature",
                            "state": "OPEN",
                            "merged": False,
                            "isDraft": False,
                            "url": "https://github.com/Acme/widgets/pull/7",
                            "createdAt": "2026-01-01T00:00:00Z",
                            "updatedAt": "2026-01-02T00:00:00Z",
                            "author": {"login": "dev", "avatarUrl": "https://avatar.test"},
                            "headRefName": "feature",
                            "baseRefName": "main",
                            "labels": {"nodes": [{"name": "bug", "color": "ff0000"}]},
                            "reviewDecision": "REVIEW_REQUIRED",
                            "additions": 3,
                            "deletions": 1,
                            "changedFiles": 2,
                            "commits": {
                                "nodes": [
                                    {
                                        "commit": {
                                            "statusCheckRollup": {"state": "PENDING"}
                                        }
                                    }
                                ]
                            },
                        }
                    ],
                }
            }
        }

    client.graphql = fake_graphql
    result = asyncio.run(
        client.list_pull_requests("Acme/widgets", "open", 20, "prior-cursor")
    )

    assert captured["after"] == "prior-cursor"
    assert captured["states"] == ["OPEN"]
    assert result["items"][0]["repo"] == "Acme/widgets"
    assert result["items"][0]["state"] == "OPEN"
    assert result["items"][0]["ciState"] == "PENDING"
    assert result["hasNext"] is True
    assert result["endCursor"] == "next-cursor"


def test_repository_discovery_follows_cursors_and_caches_results() -> None:
    client = GitHubClient(
        "test-token", "https://example.test/graphql", "M-Dot-Git"
    )
    calls = []

    async def fake_graphql(query, variables):
        calls.append((query, variables))
        if variables["after"] is None:
            return {
                "organization": {
                    "repositories": {
                        "nodes": [
                            {"nameWithOwner": "M-Dot-Git/widgets"},
                            {"nameWithOwner": "Other-Org/ignored"},
                        ],
                        "pageInfo": {"hasNextPage": True, "endCursor": "repo-cursor"},
                    }
                }
            }
        return {
            "organization": {
                "repositories": {
                    "nodes": [{"nameWithOwner": "M-Dot-Git/qa-tools"}],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        }

    client.graphql = fake_graphql
    result = asyncio.run(client.list_repositories())
    cached_result = asyncio.run(client.list_repositories())

    assert [repo["fullName"] for repo in result] == [
        "M-Dot-Git/qa-tools",
        "M-Dot-Git/widgets",
    ]
    assert cached_result == result
    assert [variables["after"] for _, variables in calls] == [None, "repo-cursor"]
    assert all(variables["organization"] == "M-Dot-Git" for _, variables in calls)
    assert all("organization(login: $organization)" in query for query, _ in calls)
    assert all(variables["first"] == 100 for _, variables in calls)
    assert len(calls) == 2


def test_repository_discovery_reports_inaccessible_organization() -> None:
    client = GitHubClient(
        "test-token", "https://example.test/graphql", "M-Dot-Git"
    )

    async def fake_graphql(*_args, **_kwargs):
        return {"organization": None}

    client.graphql = fake_graphql
    with pytest.raises(GitHubAPIError) as error:
        asyncio.run(client.list_repositories())

    assert error.value.status_code == 404


def test_repository_not_visible_to_token_is_rejected_before_pr_query() -> None:
    client = _client()
    calls = []

    async def unexpected_request(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("No PR query should be made for an undiscovered repository")

    client.graphql = unexpected_request
    with pytest.raises(GitHubAPIError) as error:
        asyncio.run(client.list_pull_requests("acme/other", "open", 20, None))

    assert error.value.status_code == 403
    assert calls == []


def test_files_are_paged_with_end_cursor_until_complete() -> None:
    client = _client()
    calls = []

    async def fake_graphql(_query, variables):
        calls.append(variables)
        if "after" not in variables:
            return {
                "repository": {
                    "pullRequest": {
                        "files": {
                            "pageInfo": {"hasNextPage": True, "endCursor": "cursor-1"},
                            "nodes": [{"path": "one.py"}],
                        }
                    }
                }
            }
        return {
            "repository": {
                "pullRequest": {
                    "files": {
                        "pageInfo": {"hasNextPage": False, "endCursor": "cursor-2"},
                        "nodes": [{"path": "two.py"}],
                    }
                }
            }
        }

    client.graphql = fake_graphql
    result = asyncio.run(client._detail_graphql("Acme", "widgets", 7))

    files = result["repository"]["pullRequest"]["files"]["nodes"]
    assert [item["path"] for item in files] == ["one.py", "two.py"]
    assert calls[1]["after"] == "cursor-1"


def test_rest_files_follow_links_and_reuse_etags(monkeypatch) -> None:
    client = _client()
    first_url = "https://api.github.com/repos/Acme/widgets/pulls/7/files?per_page=100"
    second_url = f"{first_url}&page=2"
    requests = []
    responses = [
        (200, {"ETag": '"first"', "Link": f'<{second_url}>; rel="next"'}, [{"filename": "one.py"}]),
        (200, {"ETag": '"second"'}, [{"filename": "two.py"}]),
        (304, {}, []),
        (304, {}, []),
    ]

    class MockAsyncClient:
        def __init__(self, *, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, *, headers):
            import httpx

            requests.append((url, headers))
            status, response_headers, payload = responses.pop(0)
            request = httpx.Request("GET", url)
            return httpx.Response(
                status,
                headers=response_headers,
                json=payload if status != 304 else None,
                request=request,
            )

    monkeypatch.setattr(github_service.httpx, "AsyncClient", MockAsyncClient)

    first = asyncio.run(client._rest_files("Acme", "widgets", 7))
    second = asyncio.run(client._rest_files("Acme", "widgets", 7))

    assert [file["filename"] for file in first] == ["one.py", "two.py"]
    assert second == first
    assert [url for url, _ in requests] == [first_url, second_url, first_url, second_url]
    assert requests[0][1]["Authorization"] == "Bearer test-token"
    assert requests[0][1]["Accept"] == "application/vnd.github+json"
    assert requests[0][1]["X-GitHub-Api-Version"] == "2022-11-28"
    assert requests[2][1]["If-None-Match"] == '"first"'
    assert requests[3][1]["If-None-Match"] == '"second"'


def test_patch_merge_maps_status_and_marks_missing_patch_as_truncated() -> None:
    files = {
        "nodes": [
            {
                "path": "src/new.py",
                "additions": 4,
                "deletions": 0,
                "changeType": "ADDED",
            },
            {
                "path": "assets/data.bin",
                "additions": 0,
                "deletions": 0,
                "changeType": "MODIFIED",
            },
        ]
    }

    result = GitHubClient._merge_files(
        files,
        [{"filename": "src/new.py", "patch": "@@ -0,0 +1 @@\\n+hello"}],
    )

    assert result[0] == {
        "filename": "src/new.py",
        "status": "added",
        "additions": 4,
        "deletions": 0,
        "patch": "@@ -0,0 +1 @@\\n+hello",
        "truncated": False,
    }
    assert result[1]["patch"] is None
    assert result[1]["truncated"] is True
    assert GitHubClient._merge_files(
        {"nodes": [{"path": "old.py", "additions": 0, "deletions": 1, "changeType": "DELETED"}]},
        [],
    )[0]["status"] == "removed"


def _detail(mergeable: str | None = "MERGEABLE") -> dict:
    return {
        "repository": {
            "pullRequest": {
                "number": 7,
                "title": "Feature",
                "body": None,
                "state": "OPEN",
                "merged": False,
                "isDraft": False,
                "mergeable": mergeable,
                "url": "https://github.com/Acme/widgets/pull/7",
                "createdAt": "2026-01-01T00:00:00Z",
                "updatedAt": "2026-01-02T00:00:00Z",
                "author": None,
                "baseRefName": "main",
                "headRefName": "feature",
                "headRefOid": "abc123",
                "labels": {"nodes": []},
                "reviewDecision": None,
                "reviewRequests": {"nodes": []},
                "reviews": {"nodes": []},
                "reviewThreads": {"nodes": []},
                "comments": {"nodes": []},
                "files": {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [],
                },
                "commits": {
                    "nodes": [
                        {
                            "commit": {
                                "oid": "abc123",
                                "statusCheckRollup": None,
                            }
                        }
                    ]
                },
            }
        }
    }


def test_empty_ci_is_normalized_and_unknown_mergeable_is_retried(monkeypatch) -> None:
    client = _client()
    responses = [_detail("UNKNOWN"), _detail("MERGEABLE")]
    calls = []

    async def fake_graphql(*_args, **_kwargs):
        calls.append(True)
        return responses.pop(0)

    async def empty_rest_files(*_args):
        return []

    async def no_wait(_seconds):
        return None

    client.graphql = fake_graphql
    client._rest_files = empty_rest_files
    monkeypatch.setattr("app.services.github.asyncio.sleep", no_wait)

    result = asyncio.run(client.pull_request_detail("Acme/widgets", 7))

    assert len(calls) == 2
    assert result["mergeable"] == "MERGEABLE"
    assert result["ci"] == {"state": None, "checks": []}
