import json

import pytest

from app.services import lockfile


def test_package_lock_v3() -> None:
    content = json.dumps(
        {
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "app", "version": "1.0.0"},
                "node_modules/lodash": {"version": "4.17.15"},
                "node_modules/@types/node": {"version": "20.1.0"},
                "node_modules/a/node_modules/lodash": {"version": "4.17.21"},
                "node_modules/local": {"link": True, "resolved": "../local"},
            },
        }
    )
    eco, pkgs = lockfile.parse("package-lock.json", content)
    assert eco == "npm"
    assert pkgs == [("@types/node", "20.1.0"), ("lodash", "4.17.15"), ("lodash", "4.17.21")]


def test_package_lock_v1() -> None:
    content = json.dumps(
        {"dependencies": {"a": {"version": "1.0.0", "dependencies": {"b": {"version": "2.0.0"}}}}}
    )
    assert lockfile.parse("package-lock.json", content)[1] == [("a", "1.0.0"), ("b", "2.0.0")]


def test_pnpm_lock_v9_and_v6() -> None:
    v9 = "lockfileVersion: '9.0'\npackages:\n  '@next/env@16.2.9':\n    resolution: {}\n  react@19.2.4:\n    resolution: {}\n  'styled-jsx@5.1.6(react@19.2.4)':\n    resolution: {}\n"
    assert lockfile.parse("pnpm-lock.yaml", v9)[1] == [
        ("@next/env", "16.2.9"),
        ("react", "19.2.4"),
        ("styled-jsx", "5.1.6"),
    ]
    v6 = "lockfileVersion: '6.0'\npackages:\n  /lodash@4.17.15:\n    resolution: {}\n"
    assert lockfile.parse("pnpm-lock.yaml", v6)[1] == [("lodash", "4.17.15")]


def test_uv_lock_skips_project_itself() -> None:
    content = """
version = 1
[[package]]
name = "vectana"
version = "0.1.0"
source = { editable = "." }

[[package]]
name = "fastapi"
version = "0.136.3"
source = { registry = "https://pypi.org/simple" }
"""
    assert lockfile.parse("uv.lock", content) == ("PyPI", [("fastapi", "0.136.3")])


def test_requirements_only_exact_pins() -> None:
    content = "django==3.2.0\nrequests>=2\n# comment\nuvicorn[standard]==0.30.0 ; python_version>'3'\n-e .\n"
    assert lockfile.parse("requirements-dev.txt", content) == (
        "PyPI",
        [("django", "3.2.0"), ("uvicorn", "0.30.0")],
    )


def test_pubspec_lock_hosted_only() -> None:
    content = """
packages:
  http:
    dependency: "direct main"
    source: hosted
    version: "1.2.0"
  flutter:
    dependency: "direct main"
    source: sdk
    version: "0.0.0"
"""
    assert lockfile.parse("pubspec.lock", content) == ("Pub", [("http", "1.2.0")])


def test_unsupported() -> None:
    with pytest.raises(lockfile.UnsupportedLockfile):
        lockfile.parse("Gemfile.lock", "")


def test_pick_fixed_uses_release_line() -> None:
    from app.services.osv import pick_fixed

    assert pick_fixed(["2.2.28", "3.2.13", "4.0.4"], "3.2.0") == "3.2.13"
    assert pick_fixed(["4.17.21"], "4.17.15") == "4.17.21"
    assert pick_fixed([], "1.0") is None
