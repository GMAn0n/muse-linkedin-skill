---
name: "linkedin"
description: "Work with the user's LinkedIn account via the custom.linkedin connector: read their profile, publish text posts (only with their explicit approval), and list their recent posts. Use when the user asks about LinkedIn posting, their profile, or their LinkedIn activity."
---

# LinkedIn

## Purpose
Operate the user's LinkedIn account through the user-connected `custom.linkedin`
credential (OAuth token from their own LinkedIn developer app). Three jobs:
`profile` (read their identity), `post` (publish a text post), `posts` (list their
recent posts with engagement).

## Tooling
All work goes through the checked-in CLI. Never hand-roll HTTP calls.

```sh
python3 ~/workspace/skills/linkedin/bin/linkedin.py profile [--json]
python3 ~/workspace/skills/linkedin/bin/linkedin.py post --text "..." [--visibility PUBLIC|CONNECTIONS] [--dry-run] [--json]
python3 ~/workspace/skills/linkedin/bin/linkedin.py post --text - < post.txt   # read text from stdin
python3 ~/workspace/skills/linkedin/bin/linkedin.py posts [--count 5] [--json]
```

The CLI imports the bundled `dynamic_credentials.py` helper and attaches the
credential as a Bearer surrogate itself. Callers never handle tokens.

## Auth
The credential is already stored as `custom.linkedin`; nothing here collects
one. Never ask the user to paste a key in chat, set a secret environment variable,
pass a secret flag, or write an auth file. Never print, log, or persist raw
credentials (the CLI only ever sees `hsurr:*` surrogates).

Authenticated requests go only to `api.linkedin.com`.

- **HTTP 401** means the token expired or was revoked (LinkedIn tokens live
  ~60 days). Tell the user: "Your LinkedIn token expired — re-mint it in the
  LinkedIn Developer Portal (your app > Auth), then I can reconnect it."
  Only then call `credentials.request_api_access` with `reconnect=true`.
- **HTTP 403** is a scope question, not a broken key. The CLI's requests do
  carry the credential (verify this before doubting the token). Current scope
  reality, verified 2026-10-08 by live calls:
  - `openid profile email` — works (`/v2/userinfo` returns their identity).
  - `w_member_social` — works (posting authorized; confirmed via a
    validation-only probe, nothing published).
  - `r_member_social` — NOT granted; LinkedIn restricts it to approved
    partners. `posts` will 403 with `ACCESS_DENIED ... partnerApiPosts`
    until their app gets that product approved. Report this plainly instead of
    retrying.

## Operating Rules
1. **Every post needs the user's explicit approval of the exact text in chat
   before sending.** Draft the text, show it to them verbatim, and only run
   `post` (without `--dry-run`) after they say go. Use `--dry-run` to preview
   the exact API payload during drafting. The skill never auto-posts, and
   test posts are never published to their account.
2. `profile` and `posts` are read-only; run them freely when needed.
3. Default visibility is PUBLIC; use CONNECTIONS only if the user asks.
4. LinkedIn text posts cap at 3000 chars (the CLI enforces this).
5. On success `post` prints the post URN and its linkedin.com URL — include
   the URL when confirming to the user.
6. If a call fails, surface the CLI's error message; it already distinguishes
   expired tokens (401) from missing scopes (403).
7. API mechanics (headers, endpoints, version pin) live in
   `references/api-notes.md` — read it before changing request shapes.
