#!/usr/bin/env python3
"""
Publish markdown articles to Medium via the Medium API.

Usage:
  python publish.py <path-to-article.md> [--status draft|public|unlisted]

Examples:
  python publish.py medium-articles/article-1-claude-beginners-guide.md
  python publish.py medium-articles/article-1-claude-beginners-guide.md --status public

Token setup (one-time):
  export MEDIUM_TOKEN=your_integration_token_here
  # Or create a .env file with: MEDIUM_TOKEN=your_token
"""

import sys
import os
import re
import json
import argparse
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_BASE = "https://api.medium.com/v1"


def load_token():
    token = os.environ.get("MEDIUM_TOKEN")
    if token:
        return token
    # Try .env file
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("MEDIUM_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    print("ERROR: MEDIUM_TOKEN not found.")
    print("Set it with:  export MEDIUM_TOKEN=your_token")
    print("Or create a .env file with:  MEDIUM_TOKEN=your_token")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_article(filepath):
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    # Title: first H1
    title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else os.path.basename(filepath)

    # Tags: look for "Tags: ..." line (italics or plain)
    tags = []
    tag_match = re.search(r"Tags?:\s*(.+?)(?:\*|$)", content, re.IGNORECASE | re.MULTILINE)
    if tag_match:
        raw_tags = tag_match.group(1)
        tags = [t.strip().strip("*") for t in raw_tags.split(",") if t.strip()]
        tags = [t for t in tags if t][:5]  # Medium allows max 5 tags

    # Strip image prompt sections at the bottom (lines starting with **IMAGE PROMPTS)
    content = re.sub(r"\n---\n\*\*IMAGE PROMPTS.*$", "", content, flags=re.DOTALL)

    return title, tags, content.strip()


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_request(method, path, token, data=None):
    url = f"{API_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"HTTP {e.code}: {error_body}")
        sys.exit(1)


def get_user(token):
    resp = api_request("GET", "/me", token)
    return resp["data"]


def create_post(token, author_id, title, content, tags, status):
    payload = {
        "title": title,
        "contentFormat": "markdown",
        "content": content,
        "tags": tags,
        "publishStatus": status,
    }
    resp = api_request("POST", f"/users/{author_id}/posts", token, payload)
    return resp["data"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Publish a markdown article to Medium")
    parser.add_argument("filepath", help="Path to the markdown article")
    parser.add_argument(
        "--status",
        choices=["draft", "public", "unlisted"],
        default="draft",
        help="Publish status (default: draft — safe to review before going live)",
    )
    args = parser.parse_args()

    if not os.path.exists(args.filepath):
        print(f"ERROR: File not found: {args.filepath}")
        sys.exit(1)

    token = load_token()

    print(f"Authenticating with Medium...")
    user = get_user(token)
    print(f"Logged in as: {user['name']} (@{user['username']})")

    print(f"\nParsing article: {args.filepath}")
    title, tags, content = parse_article(args.filepath)
    print(f"  Title : {title}")
    print(f"  Tags  : {', '.join(tags) if tags else '(none found)'}")
    print(f"  Status: {args.status}")
    print(f"  Length: {len(content):,} characters")

    print(f"\nPublishing to Medium...")
    post = create_post(token, user["id"], title, content, tags, args.status)

    print(f"\nSuccess!")
    print(f"  URL   : {post['url']}")
    print(f"  Status: {post['publishStatus']}")
    if args.status == "draft":
        print(f"\nArticle saved as draft. Review and publish it at:")
        print(f"  https://medium.com/me/stories/drafts")


if __name__ == "__main__":
    main()
