import json

import pytest

from app.services import lockfile, sbom

CDX_JSON = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.5",
    "metadata": {"component": {"name": "app", "purl": "pkg:npm/app@1.0.0"}},
    "components": [
        {"name": "node", "purl": "pkg:npm/%40types/node@20.1.0"},
        {"name": "lodash", "purl": "pkg:npm/lodash@4.17.15"},
        {
            "name": "log4j-core",
            "purl": "pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1?type=jar",
            "components": [{"name": "inner", "purl": "pkg:pypi/django@3.2.0"}],
        },
        {"name": "x/net", "purl": "pkg:golang/golang.org/x/net@v0.20.0"},
        {"name": "serde", "purl": "pkg:cargo/serde@1.0.190"},
        {"name": "kernel", "purl": "pkg:composer/symfony/http-kernel@5.4.0"},
        {"name": "rails", "purl": "pkg:gem/rails@7.0.0"},
        {"name": "Newtonsoft.Json", "purl": "pkg:nuget/Newtonsoft.Json@13.0.1"},
        {"name": "http", "purl": "pkg:pub/http@1.2.0"},
        {"name": "openssl", "purl": "pkg:deb/debian/openssl@3.0.11?arch=amd64"},
        {"name": "musl", "purl": "pkg:apk/alpine/musl@1.2.4"},
        {"name": "nopurl"},
    ],
}

EXPECTED = [
    ("Go", "golang.org/x/net", "0.20.0"),
    ("Maven", "org.apache.logging.log4j:log4j-core", "2.14.1"),
    ("NuGet", "Newtonsoft.Json", "13.0.1"),
    ("Packagist", "symfony/http-kernel", "5.4.0"),
    ("Pub", "http", "1.2.0"),
    ("PyPI", "django", "3.2.0"),
    ("RubyGems", "rails", "7.0.0"),
    ("crates.io", "serde", "1.0.190"),
    ("npm", "@types/node", "20.1.0"),
    ("npm", "lodash", "4.17.15"),
]


def test_purl_parsing() -> None:
    p = sbom.parse_purl("pkg:npm/%40angular/core@16.0.0?x=1#sub")
    assert p == sbom.Purl(type="npm", namespace="@angular", name="core", version="16.0.0")
    assert sbom.to_package(p) == ("npm", "@angular/core", "16.0.0")
    assert sbom.parse_purl("not a purl") is None
    # No version: nothing to match against.
    assert sbom.to_package(sbom.parse_purl("pkg:pypi/django")) is None  # type: ignore[arg-type]


def test_cyclonedx_json() -> None:
    doc = sbom.parse(json.dumps(CDX_JSON))
    assert doc.format == "CycloneDX"
    assert doc.packages == EXPECTED
    assert doc.unsupported == {"deb": 1, "apk": 1, "(no purl)": 1}


def test_cyclonedx_json_detected_when_bomformat_is_late() -> None:
    padded = {"components": CDX_JSON["components"], "x": "y" * 5000, "bomFormat": "CycloneDX"}
    assert sbom.detect(json.dumps(padded)) == "CycloneDX"


def test_cyclonedx_xml() -> None:
    content = """<?xml version="1.0" encoding="UTF-8"?>
<bom xmlns="http://cyclonedx.org/schema/bom/1.5" version="1">
  <metadata>
    <component type="application"><name>app</name><purl>pkg:maven/com.acme/app@1.0</purl></component>
  </metadata>
  <components>
    <component type="library">
      <name>log4j-core</name>
      <purl>pkg:maven/org.apache.logging.log4j/log4j-core@2.14.1?type=jar</purl>
      <components>
        <component type="library"><name>inner</name><purl>pkg:maven/com.acme/inner@0.1</purl></component>
      </components>
    </component>
    <component type="library"><name>noid</name></component>
  </components>
</bom>"""
    doc = sbom.parse(content)
    assert doc.packages == [
        ("Maven", "com.acme:inner", "0.1"),
        ("Maven", "org.apache.logging.log4j:log4j-core", "2.14.1"),
    ]
    assert doc.unsupported == {"(no purl)": 1}


def test_xml_with_dtd_is_rejected() -> None:
    content = (
        '<?xml version="1.0"?><!DOCTYPE bom [<!ENTITY a "aaaa">]>'
        '<bom xmlns="http://cyclonedx.org/schema/bom/1.5"><components/></bom>'
    )
    with pytest.raises(ValueError):
        sbom.parse(content)


def test_spdx_json_skips_described_root() -> None:
    content = json.dumps(
        {
            "spdxVersion": "SPDX-2.3",
            "SPDXID": "SPDXRef-DOCUMENT",
            "packages": [
                {
                    "SPDXID": "SPDXRef-root",
                    "name": "app",
                    "externalRefs": [
                        {"referenceType": "purl", "referenceLocator": "pkg:npm/app@1.0.0"}
                    ],
                },
                {
                    "SPDXID": "SPDXRef-lodash",
                    "name": "lodash",
                    "externalRefs": [
                        {
                            "referenceCategory": "PACKAGE-MANAGER",
                            "referenceType": "purl",
                            "referenceLocator": "pkg:npm/lodash@4.17.15",
                        },
                        {"referenceType": "cpe23Type", "referenceLocator": "cpe:2.3:a:..."},
                    ],
                },
                {"SPDXID": "SPDXRef-file", "name": "something"},
            ],
            "relationships": [
                {
                    "spdxElementId": "SPDXRef-DOCUMENT",
                    "relationshipType": "DESCRIBES",
                    "relatedSpdxElement": "SPDXRef-root",
                }
            ],
        }
    )
    doc = sbom.parse(content)
    assert doc.format == "SPDX"
    assert doc.packages == [("npm", "lodash", "4.17.15")]
    assert doc.unsupported == {"(no purl)": 1}


def test_spdx_tag_value() -> None:
    content = """SPDXVersion: SPDX-2.3
DataLicense: CC0-1.0
SPDXID: SPDXRef-DOCUMENT
DocumentName: app

PackageName: app
SPDXID: SPDXRef-root
ExternalRef: PACKAGE-MANAGER purl pkg:pypi/app@1.0

PackageName: django
SPDXID: SPDXRef-django
ExternalRef: SECURITY cpe23Type cpe:2.3:a:djangoproject:django:3.2.0:*:*:*:*:*:*:*
ExternalRef: PACKAGE-MANAGER purl pkg:pypi/django@3.2.0

Relationship: SPDXRef-DOCUMENT DESCRIBES SPDXRef-root
"""
    doc = sbom.parse(content)
    assert doc.packages == [("PyPI", "django", "3.2.0")]
    assert doc.unsupported == {}


def test_lockfile_parse_falls_back_to_sbom_by_content() -> None:
    r = lockfile.parse("bom.json", json.dumps(CDX_JSON))
    assert r.kind == "sbom" and r.format == "CycloneDX"
    assert r.packages == EXPECTED
    assert "npm" in r.ecosystems and "Maven" in r.ecosystems
