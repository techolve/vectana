import json

from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.eol import Runtime
from app.services import toolfile
from tests.conftest import Org, auth, make_project

PRODUCTS = [
    {"name": "python", "aliases": []},
    {"name": "nodejs", "aliases": ["node"]},
    {"name": "postgresql", "aliases": ["postgres"]},
    {"name": "eclipse-temurin", "aliases": ["temurin"]},
    {"name": "terraform", "aliases": []},
]
INDEX = toolfile.product_index(PRODUCTS)

MISE = """
[tools]
python = "3.14"
node = ["24.18.0", "22"]
uv = "latest"
postgres = { version = "18.1" }
java = "temurin-21.0.2"
"aqua:hashicorp/terraform" = "v1.9.5"
go = "lts"

[tasks.dev]
run = "uv run uvicorn"
"""


def test_parse_mise() -> None:
    entries = toolfile.parse("mise.toml", MISE)
    assert [(e.tool, e.version) for e in entries] == [
        ("python", "3.14"),
        ("node", "24.18.0"),
        ("node", "22"),
        ("uv", "latest"),
        ("postgres", "18.1"),
        ("java", "temurin-21.0.2"),
        ("aqua:hashicorp/terraform", "v1.9.5"),
        ("go", "lts"),
    ]


def test_parse_tool_versions() -> None:
    content = "nodejs 20.11.0 18.19.0\n# comment\npython 3.12.1  # pinned\n"
    assert [(e.tool, e.version) for e in toolfile.parse(".tool-versions", content)] == [
        ("nodejs", "20.11.0"),
        ("nodejs", "18.19.0"),
        ("python", "3.12.1"),
    ]


def test_resolve() -> None:
    def r(tool: str, version: str) -> tuple[str | None, str, str | None]:
        res = toolfile.resolve(toolfile.Entry(tool, version), INDEX)
        return res.product, res.version, res.reason

    assert r("node", "24.18.0") == ("nodejs", "24.18.0", None)
    assert r("postgres", "prefix:18") == ("postgresql", "18", None)
    assert r("java", "temurin-21.0.2") == ("eclipse-temurin", "21.0.2", None)
    assert r("java", "21") == (None, "21", "unsupported")
    assert r("aqua:hashicorp/terraform", "v1.9.5") == ("terraform", "1.9.5", None)
    assert r("python", "latest") == (None, "latest", "unpinned")
    assert r("uv", "0.9") == (None, "0.9", "unsupported")


async def test_import_mise(
    client: AsyncClient, session: AsyncSession, org: Org, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    import httpx

    from app.services import eol

    def fake() -> httpx.AsyncClient:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"result": PRODUCTS})

        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    eol._cache.clear()
    monkeypatch.setattr(eol, "make_client", fake)
    project = await make_project(client, org.company_admin, "tools")
    url = f"/api/projects/{project['id']}/packages/import"
    h = auth(org.company_admin)

    r = await client.post(url, files={"file": ("mise.toml", MISE.encode())}, headers=h)
    body = r.json()
    assert body["kind"] == "runtimes"
    assert body["added"] == 6 and body["removed"] == 0
    # Unknown tools are reported before their version is looked at.
    assert {(s["tool"], s["reason"]) for s in body["skipped"]} == {
        ("uv", "unsupported"),
        ("go", "unsupported"),
    }
    # A manual runtime is never removed by re-importing the file.
    await client.post(
        f"/api/projects/{project['id']}/runtimes",
        json={"product": "python", "version": "3.13"},
        headers=h,
    )
    r = await client.post(
        url, files={"file": ("mise.toml", b'[tools]\npython = "3.14"\n')}, headers=h
    )
    assert r.json()["removed"] == 5
    rows = (await session.exec(select(Runtime))).all()
    assert sorted((x.product, x.version, x.source) for x in rows) == [
        ("python", "3.13", "manual"),
        ("python", "3.14", "file:mise.toml"),
    ]
    assert json.loads(
        (await client.get(f"/api/projects/{project['id']}/runtimes", headers=h)).text
    )[0]["source"]
