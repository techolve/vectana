#!/usr/bin/env bash
# Prints the GitHub Release notes for tag vX.Y.Z:
#   1. .github/release-notes/vX.Y.Z.md if it exists (a hand-written summary)
#   2. "動かし方": the Docker image, and the npm package when mcp/ has the same version
#   3. "変更履歴": the [X.Y.Z] section of CHANGELOG.md
# CHANGELOG.md and mcp/package.json are read at the tag, the summary from the
# working tree, so a summary can be added later for an older tag. Without the
# tag (e.g. in the release PR before tagging), everything comes from the
# working tree. Fails when CHANGELOG.md has no section for the version.
# Usage: tools/release/notes.sh vX.Y.Z
set -euo pipefail

tag="${1:?usage: $0 vX.Y.Z}"
version="${tag#v}"
repo="${GITHUB_REPOSITORY:-techolve/vectana}"
root="$(cd "$(dirname "$0")/../.." && pwd)"

at_tag() {
  if git -C "$root" rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
    git -C "$root" show "$tag:$1"
  else
    cat "$root/$1"
  fi
}

section="$(awk -v v="$version" '
  index($0, "## [" v "]") == 1 { found = 1; next }
  found && /^## \[/ { exit }
  found && /^\[[^]]+\]: / { exit }
  found { print }
' <(at_tag CHANGELOG.md) | sed -e '/./,$!d' | sed -e ':a' -e '/^\n*$/{$d;N;ba' -e '}')"

if [ -z "$section" ]; then
  echo "CHANGELOG.md has no section for [$version]" >&2
  exit 1
fi

summary="$root/.github/release-notes/$tag.md"
if [ -f "$summary" ]; then
  cat "$summary"
  echo
fi

echo "## 動かし方"
echo
echo "- イメージ: \`heki0824/vectana:$version\`（linux/amd64・linux/arm64）"
mcp_version="$( (at_tag mcp/package.json 2>/dev/null || true) | sed -n 's/^  "version": "\(.*\)",$/\1/p' | head -1)"
if [ "$mcp_version" = "$version" ]; then
  echo "- MCP サーバー: \`@techolve/vectana-mcp@$version\`（npm、タグ \`mcp-$tag\`）"
fi
echo
echo "## 変更履歴"
echo
echo "$section"
echo
echo "全履歴は [CHANGELOG.md](https://github.com/$repo/blob/$tag/CHANGELOG.md) を参照してください。"
