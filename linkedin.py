#!/usr/bin/env python3
"""
LinkedIn Automation — Post directly from Claude Code.

SETUP (one-time):
  1. Go to linkedin.com/developers → Create app
  2. Add redirect URI: http://localhost:8000/callback
  3. Request scopes: openid, profile, w_member_social
  4. Add to .env:
       LINKEDIN_CLIENT_ID=your_client_id
       LINKEDIN_CLIENT_SECRET=your_client_secret

COMMANDS:
  python linkedin.py auth                          # Authenticate (one-time)
  python linkedin.py post --idea "your idea"       # Write + post from idea
  python linkedin.py post --file path/to/post.md   # Post from file
  python linkedin.py post --text "ready text"      # Post exact text
"""

import sys
import os
import json
import re
import argparse
import secrets
import webbrowser
import urllib.request
import urllib.parse
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_BASE       = "https://api.linkedin.com/v2"
AUTH_URL       = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL      = "https://www.linkedin.com/oauth/v2/accessToken"
REDIRECT_URI   = "http://localhost:8000/callback"
SCOPES         = "openid profile w_member_social"
TOKEN_FILE     = os.path.join(os.path.dirname(__file__), ".linkedin_token.json")
ENV_FILE       = os.path.join(os.path.dirname(__file__), ".env")


def load_env():
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")
    env.update(os.environ)
    return env


def get_credentials():
    env = load_env()
    client_id     = env.get("LINKEDIN_CLIENT_ID")
    client_secret = env.get("LINKEDIN_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("ERROR: LinkedIn credentials not found.")
        print("Add to .env:")
        print("  LINKEDIN_CLIENT_ID=your_client_id")
        print("  LINKEDIN_CLIENT_SECRET=your_client_secret")
        print()
        print("Get them at: https://linkedin.com/developers")
        sys.exit(1)
    return client_id, client_secret


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------

_auth_code = None

class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style="font-family:sans-serif;text-align:center;padding:60px">
                <h2>&#10003; Authenticated!</h2>
                <p>You can close this tab and return to Claude Code.</p>
                </body></html>
            """)
        else:
            self.send_response(400)
            self.end_headers()
    def log_message(self, *args):
        pass


def authenticate():
    client_id, client_secret = get_credentials()
    state = secrets.token_urlsafe(16)

    auth_params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id":     client_id,
        "redirect_uri":  REDIRECT_URI,
        "scope":         SCOPES,
        "state":         state,
    })
    auth_link = f"{AUTH_URL}?{auth_params}"

    print("Opening LinkedIn login in your browser...")
    print(f"\nIf it doesn't open automatically, visit:\n{auth_link}\n")
    webbrowser.open(auth_link)

    server = HTTPServer(("localhost", 8000), _CallbackHandler)
    server.timeout = 120
    print("Waiting for LinkedIn authorization (2 min timeout)...")
    server.handle_request()

    if not _auth_code:
        print("ERROR: No authorization code received.")
        sys.exit(1)

    # Exchange code for token
    token_data = urllib.parse.urlencode({
        "grant_type":    "authorization_code",
        "code":          _auth_code,
        "redirect_uri":  REDIRECT_URI,
        "client_id":     client_id,
        "client_secret": client_secret,
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=token_data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req) as resp:
        token_resp = json.loads(resp.read().decode())

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_resp, f, indent=2)
    os.chmod(TOKEN_FILE, 0o600)

    print(f"\nAuthenticated! Token saved to {TOKEN_FILE}")
    return token_resp["access_token"]


def load_token():
    if not os.path.exists(TOKEN_FILE):
        print("Not authenticated. Run:  python linkedin.py auth")
        sys.exit(1)
    with open(TOKEN_FILE) as f:
        data = json.load(f)
    return data["access_token"]


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_get(path, token):
    req = urllib.request.Request(f"{API_BASE}{path}")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("LinkedIn-Version", "202401")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def api_post(path, token, payload):
    body = json.dumps(payload).encode()
    req = urllib.request.Request(f"{API_BASE}{path}", data=body, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("LinkedIn-Version", "202401")
    req.add_header("X-Restli-Protocol-Version", "2.0.0")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode()) if resp.read() else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"HTTP {e.code}: {err}")
        sys.exit(1)


def get_profile(token):
    return api_get("/userinfo", token)


# ---------------------------------------------------------------------------
# Post composition
# ---------------------------------------------------------------------------

HASHTAG_MAP = {
    "design system":    ["#DesignSystem", "#UXDesign", "#ProductDesign", "#Figma", "#DesignOps"],
    "claude":           ["#Claude", "#AI", "#ArtificialIntelligence", "#Productivity", "#AITools"],
    "ai":               ["#AI", "#ArtificialIntelligence", "#MachineLearning", "#Tech", "#Innovation"],
    "chatgpt":          ["#ChatGPT", "#AI", "#ArtificialIntelligence", "#Tech", "#Productivity"],
    "developer":        ["#SoftwareDevelopment", "#Coding", "#Programming", "#DevTools", "#AI"],
    "prompt":           ["#PromptEngineering", "#AI", "#Claude", "#Productivity", "#AITools"],
    "medium":           ["#Writing", "#ContentCreation", "#Blogging", "#Medium", "#TechWriting"],
    "linkedin":         ["#LinkedIn", "#PersonalBranding", "#SocialMedia", "#Marketing", "#Growth"],
}

DEFAULT_HASHTAGS = ["#AI", "#Tech", "#Productivity", "#Innovation", "#Learning"]


def pick_hashtags(text):
    text_lower = text.lower()
    for keyword, tags in HASHTAG_MAP.items():
        if keyword in text_lower:
            return tags
    return DEFAULT_HASHTAGS


def compose_from_idea(idea):
    """Turn a short idea into a full LinkedIn post."""
    hashtags = pick_hashtags(idea)
    tags_str = " ".join(hashtags)

    # Simple template-based composition
    post = f"""Here's something worth thinking about:

{idea}

Most people overlook this. The ones who don't tend to build better products, write better content, and make faster decisions.

What's your take? Drop it in the comments 👇

{tags_str}"""
    return post


def load_from_file(filepath):
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    # If it's our linkedin-post file, extract Option A by default
    option_match = re.search(
        r"## Option A.*?---\n(.*?)---",
        content, re.DOTALL
    )
    if option_match:
        text = option_match.group(1).strip()
        # Remove the trailing hashtag line (we'll re-add clean ones)
        text = re.sub(r"\n#\w+.*$", "", text, flags=re.MULTILINE).strip()
        hashtags = pick_hashtags(text)
        return text + "\n\n" + " ".join(hashtags)

    return content.strip()


# ---------------------------------------------------------------------------
# Publish
# ---------------------------------------------------------------------------

def publish_post(token, author_urn, text):
    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        },
    }
    status, resp = api_post("/ugcPosts", token, payload)
    return resp


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_auth(_args):
    authenticate()


def cmd_post(args):
    token = load_token()

    print("Fetching your LinkedIn profile...")
    profile  = get_profile(token)
    name     = profile.get("name", "Unknown")
    sub      = profile.get("sub")          # OpenID subject = person ID
    author_urn = f"urn:li:person:{sub}"
    print(f"Posting as: {name}")

    if args.idea:
        text = compose_from_idea(args.idea)
        print("\nComposed post:\n")
        print("─" * 60)
        print(text)
        print("─" * 60)
    elif args.file:
        if not os.path.exists(args.file):
            print(f"ERROR: File not found: {args.file}")
            sys.exit(1)
        text = load_from_file(args.file)
        print(f"\nLoaded post from {args.file}")
    elif args.text:
        text = args.text
    else:
        print("ERROR: Provide --idea, --file, or --text")
        sys.exit(1)

    confirm = input("\nPost this to LinkedIn? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        sys.exit(0)

    print("Posting...")
    resp = publish_post(token, author_urn, text)
    post_id = resp.get("id", "")
    print(f"\nPosted! LinkedIn post ID: {post_id}")
    print("View at: https://www.linkedin.com/feed/")


def main():
    parser = argparse.ArgumentParser(
        description="LinkedIn automation — post from Claude Code"
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("auth", help="Authenticate with LinkedIn (one-time)")

    post_p = sub.add_parser("post", help="Create and publish a LinkedIn post")
    group = post_p.add_mutually_exclusive_group(required=True)
    group.add_argument("--idea",  help="Short idea — Claude expands it into a full post")
    group.add_argument("--file",  help="Path to a markdown post file")
    group.add_argument("--text",  help="Exact post text to publish")

    args = parser.parse_args()

    if args.command == "auth":
        cmd_auth(args)
    elif args.command == "post":
        cmd_post(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
