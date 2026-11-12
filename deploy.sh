#!/bin/bash
# Publish the mock folder to GitHub Pages (gh-pages branch, served at https://1jenson.github.io/garage-system/).
# Run after committing changes on main. Bump VERSION in mock/sw.js first so installed copies update.
set -e
cd "$(dirname "$0")"
git push origin main
git push --force origin "$(git subtree split --prefix mock main):refs/heads/gh-pages"
echo "Published. Pages rebuilds in about a minute."
