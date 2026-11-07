import json

import pytest

from app.services import lockfile


def lp(filename: str, content: str) -> tuple[str, list[tuple[str, str]]]:
    r = lockfile.parse(filename, content)
    assert {eco for eco, _, _ in r.packages} <= {r.format}
    return r.format, [(n, v) for _, n, v in r.packages]


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
    eco, pkgs = lp("package-lock.json", content)
    assert eco == "npm"
    assert pkgs == [("@types/node", "20.1.0"), ("lodash", "4.17.15"), ("lodash", "4.17.21")]


def test_package_lock_v1() -> None:
    content = json.dumps(
        {"dependencies": {"a": {"version": "1.0.0", "dependencies": {"b": {"version": "2.0.0"}}}}}
    )
    assert lp("package-lock.json", content)[1] == [("a", "1.0.0"), ("b", "2.0.0")]


def test_pnpm_lock_v9_and_v6() -> None:
    v9 = "lockfileVersion: '9.0'\npackages:\n  '@next/env@16.2.9':\n    resolution: {}\n  react@19.2.4:\n    resolution: {}\n  'styled-jsx@5.1.6(react@19.2.4)':\n    resolution: {}\n"
    assert lp("pnpm-lock.yaml", v9)[1] == [
        ("@next/env", "16.2.9"),
        ("react", "19.2.4"),
        ("styled-jsx", "5.1.6"),
    ]
    v6 = "lockfileVersion: '6.0'\npackages:\n  /lodash@4.17.15:\n    resolution: {}\n"
    assert lp("pnpm-lock.yaml", v6)[1] == [("lodash", "4.17.15")]


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
    assert lp("uv.lock", content) == ("PyPI", [("fastapi", "0.136.3")])


def test_requirements_only_exact_pins() -> None:
    content = "django==3.2.0\nrequests>=2\n# comment\nuvicorn[standard]==0.30.0 ; python_version>'3'\n-e .\n"
    assert lp("requirements-dev.txt", content) == (
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
    assert lp("pubspec.lock", content) == ("Pub", [("http", "1.2.0")])


def test_unsupported() -> None:
    with pytest.raises(lockfile.UnsupportedLockfile):
        lockfile.parse("Gemfile.lock", "")
    # JSON that is neither a known lockfile nor an SBOM
    with pytest.raises(lockfile.UnsupportedLockfile):
        lockfile.parse("package.json", '{"name": "x"}')


def test_pick_fixed_uses_release_line() -> None:
    from app.services.osv import pick_fixed

    assert pick_fixed(["2.2.28", "3.2.13", "4.0.4"], "3.2.0") == "3.2.13"
    assert pick_fixed(["4.17.21"], "4.17.15") == "4.17.21"
    assert pick_fixed([], "1.0") is None


def test_go_mod_requires_and_replaces() -> None:
    content = """module example.com/app

go 1.22

require github.com/pkg/errors v0.9.1

require (
	golang.org/x/net v0.20.0 // indirect
	github.com/old/thing v1.0.0
	example.com/local v0.0.0
	github.com/gin-gonic/gin v1.9.1+incompatible
)

replace github.com/old/thing => github.com/new/thing v1.2.0
replace example.com/local => ../local
"""
    assert lp("go.mod", content) == (
        "Go",
        [
            ("github.com/gin-gonic/gin", "1.9.1+incompatible"),
            ("github.com/new/thing", "1.2.0"),
            ("github.com/pkg/errors", "0.9.1"),
            ("golang.org/x/net", "0.20.0"),
        ],
    )


def test_go_sum_skips_go_mod_hashes() -> None:
    content = (
        "github.com/pkg/errors v0.9.1 h1:abc=\n"
        "github.com/pkg/errors v0.9.1/go.mod h1:def=\n"
        "golang.org/x/text v0.3.0/go.mod h1:ghi=\n"
    )
    assert lp("go.sum", content) == ("Go", [("github.com/pkg/errors", "0.9.1")])


def test_composer_lock() -> None:
    content = json.dumps(
        {
            "packages": [
                {"name": "symfony/http-kernel", "version": "v5.4.0"},
                {"name": "acme/branch", "version": "dev-main"},
            ],
            "packages-dev": [{"name": "phpunit/phpunit", "version": "9.6.1"}],
        }
    )
    assert lp("composer.lock", content) == (
        "Packagist",
        [("phpunit/phpunit", "9.6.1"), ("symfony/http-kernel", "5.4.0")],
    )


def test_cargo_lock_registry_only() -> None:
    content = """
version = 3

[[package]]
name = "myapp"
version = "0.1.0"

[[package]]
name = "serde"
version = "1.0.190"
source = "registry+https://github.com/rust-lang/crates.io-index"

[[package]]
name = "forked"
version = "0.2.0"
source = "git+https://github.com/acme/forked#abc"
"""
    assert lp("Cargo.lock", content) == ("crates.io", [("serde", "1.0.190")])


def test_gradle_lockfile() -> None:
    content = """# This is a Gradle generated file for dependency locking.
com.fasterxml.jackson.core:jackson-databind:2.15.2=compileClasspath,runtimeClasspath
org.apache.logging.log4j:log4j-core:2.14.1=runtimeClasspath
empty=annotationProcessor
"""
    expected = (
        "Maven",
        [
            ("com.fasterxml.jackson.core:jackson-databind", "2.15.2"),
            ("org.apache.logging.log4j:log4j-core", "2.14.1"),
        ],
    )
    assert lp("gradle.lockfile", content) == expected
    assert lp("buildscript-gradle.lockfile", content) == expected
