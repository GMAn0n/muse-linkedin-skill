#!/usr/bin/env python3
"""LinkedIn CLI for the custom.linkedin connector.

Subcommands:
  profile   Read the authenticated member's profile (name, person URN, email).
  post      Publish a text post. Requires Sam's explicit approval of the exact
            text in chat BEFORE running (the agent shows the text, Sam says go).
            Use --dry-run to preview the exact API payload without publishing.
  posts     List the member's recent posts with best-effort engagement counts.

Auth: the real token never appears in this process. Requests carry only an
hsurr:* surrogate that authd/Sentinel swap for the real credential on egress
to api.linkedin.com. Never print request headers.
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

HELPER_PATH = "/opt/hatch/skills/skill-creator/bin/dynamic_credentials.py"
CRED_NAME = "custom.linkedin"
ALLOWED_HOSTS = ("api.linkedin.com",)
API_BASE = "https://api.linkedin.com"
# LinkedIn versioned APIs require YYYYMM; paired with X-Restli-Protocol-Version.
# Verified 2026-10-08: 202501 is sunset (426 NONEXISTENT_VERSION); 202609 active.
LI_VERSION = "202609"
POST_TEXT_LIMIT = 3000


def _load_helper():
    spec = importlib.util.spec_from_file_location("dynamic_credentials", HELPER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


dc = _load_helper()


class LinkedInError(RuntimeError):
    """User-facing error; never includes credential material."""


def _friendly_error(status, body, path):
    snippet = (body or "").strip()[:600]
    if status == 401:
        return (
            "LinkedIn returned HTTP 401: the access token is expired, revoked, "
            "or invalid.\n"
            "This request WAS built with the skill's credential helper, so the "
            "credential was attached - this is a token problem, not a code problem.\n"
            "Fix: re-mint the token in the LinkedIn Developer Portal "
            "(your app > Auth > generate a new access token), then replace the "
            "custom.linkedin connector by running credentials.request_api_access "
            "with reconnect=true.\n"
            f"LinkedIn said: {snippet}"
        )
    if status == 403:
        return (
            "LinkedIn returned HTTP 403: the token is valid but the app lacks "
            "permission for this call.\n"
            "Likely cause: a missing scope/product on the LinkedIn developer app. "
            "w_member_social covers posting; r_member_social (reading posts) is "
            "restricted to approved partners and usually 403s on self-serve apps.\n"
            "Fix: LinkedIn Developer Portal > your app > Products tab > request "
            "the needed product, then re-authorize.\n"
            f"LinkedIn said: {snippet}"
        )
    return f"LinkedIn returned HTTP {status} for {path}. LinkedIn said: {snippet}"


def api(method, path, body=None, versioned=True, timeout=30):
    """Make an authenticated LinkedIn API call.

    Returns (status, json_dict, headers_dict). Raises LinkedInError on HTTP
    errors. The Authorization header carries only the hsurr surrogate.
    """
    url = API_BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if versioned:
        req.add_header("LinkedIn-Version", LI_VERSION)
        req.add_header("X-Restli-Protocol-Version", "2.0.0")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    dc.add_surrogate_to_request(req, CRED_NAME, allowed_hosts=ALLOWED_HOSTS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            try:
                payload = dc.read_json_response(resp)
            except Exception:
                payload = {}
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return resp.status, payload, headers
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = ""
        raise LinkedInError(_friendly_error(e.code, err_body, path))
    except urllib.error.URLError as e:
        raise LinkedInError(f"Network error calling LinkedIn {path}: {e.reason}")


def get_me():
    """Return the /v2/userinfo identity dict (has .get('sub') person id)."""
    _, data, _ = api("GET", "/v2/userinfo", versioned=False)
    if not data.get("sub"):
        raise LinkedInError(
            "LinkedIn /v2/userinfo did not return a member id. "
            f"Response keys: {sorted(data.keys())}"
        )
    return data


def fmt_ts(millis):
    try:
        dt = datetime.datetime.fromtimestamp(int(millis) / 1000,
                                             tz=datetime.timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return "?"


def cmd_profile(args):
    me = get_me()
    person_id = me.get("sub", "")
    profile = {
        "name": me.get("name"),
        "given_name": me.get("given_name"),
        "family_name": me.get("family_name"),
        "email": me.get("email"),
        "person_id": person_id,
        "person_urn": f"urn:li:person:{person_id}" if person_id else None,
        "picture": me.get("picture"),
        "locale": (me.get("locale") or {}).get("country")
                  if isinstance(me.get("locale"), dict) else me.get("locale"),
    }
    if args.json:
        print(json.dumps(profile, indent=2))
    else:
        print(f"Name:       {profile['name']}")
        print(f"Email:      {profile['email']}")
        print(f"Person URN: {profile['person_urn']}")


def escape_commentary(text):
    """Backslash-escape LinkedIn's 'little text' reserved characters.

    The /rest/posts commentary field is NOT plain text: the characters
    \\ | { } @ [ ] ( ) < > # * _ ~ are reserved, and LinkedIn silently
    drops the post body from the first unescaped reserved character
    onward (no error). Escaping makes them render literally.
    """
    return "".join(
        ("\\" + ch) if ch in "\\|{}@[]()<>#*_~" else ch for ch in text
    )


def cmd_post(args):
    text = args.text
    if text == "-":
        text = sys.stdin.read()
    text = (text or "").strip()
    if not text:
        raise LinkedInError(
            'Post text is empty. Pass --text "..." or pipe it with --text -'
        )
    if len(text) > POST_TEXT_LIMIT:
        raise LinkedInError(
            f"Post text is {len(text)} chars; LinkedIn's limit is {POST_TEXT_LIMIT}."
        )
    text = escape_commentary(text)
    me = get_me()
    author = args.author or f"urn:li:person:{me['sub']}"
    body = {
        "author": author,
        "commentary": text,
        "visibility": args.visibility,
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if args.dry_run:
        preview = {
            "method": "POST",
            "url": API_BASE + "/rest/posts",
            "headers": {
                "LinkedIn-Version": LI_VERSION,
                "X-Restli-Protocol-Version": "2.0.0",
                "Content-Type": "application/json",
                "Authorization": "Bearer <attached by skill helper, never shown>",
            },
            "body": body,
        }
        print(json.dumps(preview, indent=2))
        print("\nDRY RUN - nothing was published.")
        return
    status, _, headers = api("POST", "/rest/posts", body=body, versioned=True)
    post_urn = headers.get("x-restli-id")
    out = {"status": status, "post_urn": post_urn}
    if post_urn:
        out["url"] = f"https://www.linkedin.com/feed/update/{post_urn}/"
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"Published (HTTP {status}).")
        if post_urn:
            print(f"Post URN: {post_urn}")
            print(f"URL:      {out['url']}")
        else:
            print("Warning: no x-restli-id header came back; check LinkedIn to confirm.")


def _engagement(post_urn):
    """Best-effort (likes, comments) totals; (None, None) when unavailable."""
    enc = urllib.parse.quote(post_urn, safe="")
    likes = comments = None
    for kind in ("likes", "comments"):
        try:
            _, data, _ = api(
                "GET", f"/v2/socialActions/{enc}/{kind}?count=1", versioned=False
            )
            total = (data.get("paging") or {}).get("total")
            if kind == "likes":
                likes = total
            else:
                comments = total
        except LinkedInError:
            pass
    return likes, comments


def cmd_posts(args):
    me = get_me()
    author = f"urn:li:person:{me['sub']}"
    query = urllib.parse.urlencode(
        {"author": author, "q": "author", "count": args.count,
         "sortBy": "LAST_MODIFIED"}
    )
    _, data, _ = api("GET", "/rest/posts?" + query, versioned=True)
    elements = data.get("elements", [])
    rows = []
    for el in elements:
        urn = el.get("id", "")
        likes, comments = _engagement(urn) if urn else (None, None)
        rows.append({
            "urn": urn,
            "date": fmt_ts(el.get("createdAt")),
            "visibility": el.get("visibility"),
            "lifecycle": el.get("lifecycleState"),
            "likes": likes if likes is not None else "n/a",
            "comments": comments if comments is not None else "n/a",
            "text": (el.get("commentary") or "")[:160],
        })
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print("No posts returned.")
        return
    for r in rows:
        print(f"{r['date']}  likes={r['likes']} comments={r['comments']} [{r['visibility']}]")
        print(f"  {r['urn']}")
        print(f"  {r['text']}")
        print()


def cmd_delete(args):
    urn = args.urn.strip()
    if not urn.startswith("urn:li:"):
        raise LinkedInError(f"Not a LinkedIn URN: {urn}")
    enc = urllib.parse.quote(urn, safe="")
    status, _, _ = api("DELETE", f"/rest/posts/{enc}", versioned=True)
    if args.json:
        print(json.dumps({"status": status, "deleted": urn}, indent=2))
    else:
        print(f"Deleted {urn} (HTTP {status}).")


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="linkedin.py",
        description="LinkedIn CLI (custom.linkedin connector).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("profile", help="Show the authenticated member's profile.")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_profile)

    sp = sub.add_parser("post", help="Publish a text post (needs Sam's approval first).")
    sp.add_argument("--text", required=True,
                    help='Post text, or "-" to read from stdin.')
    sp.add_argument("--visibility", default="PUBLIC",
                    choices=["PUBLIC", "CONNECTIONS"],
                    help="Who can see it (default PUBLIC).")
    sp.add_argument("--author",
                    help="Author URN override (default: urn:li:person from /v2/userinfo).")
    sp.add_argument("--dry-run", action="store_true",
                    help="Print the exact request without publishing.")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_post)

    sp = sub.add_parser("posts", help="List recent posts with engagement.")
    sp.add_argument("--count", type=int, default=5)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_posts)

    sp = sub.add_parser("delete", help="Delete one of your posts by URN.")
    sp.add_argument("--urn", required=True, help="Post URN, e.g. urn:li:share:...")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_delete)

    args = p.parse_args(argv)
    try:
        args.func(args)
    except LinkedInError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except dc.DynamicCredentialError as e:
        print(f"error: credential problem: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
