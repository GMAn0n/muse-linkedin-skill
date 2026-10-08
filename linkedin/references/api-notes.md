# LinkedIn API notes (verified 2026-10-08)

Base: `https://api.linkedin.com`. Auth: `Authorization: Bearer <token>`
(in the skill this is always the `hsurr:*` surrogate, swapped on egress).

## Required headers (versioned `/rest/*` calls)

```
LinkedIn-Version: 202609          # YYYYMM; old versions sunset (202501 -> 426 NONEXISTENT_VERSION)
X-Restli-Protocol-Version: 2.0.0
Content-Type: application/json    # on POST
Accept: application/json
```

If a `/rest/*` call 426s with `NONEXISTENT_VERSION`, bump `LI_VERSION` in
`bin/linkedin.py` to a recent YYYYMM and re-test.

## Identity — GET /v2/userinfo (unversioned)

Works with `openid profile email`. Returns e.g.:

```json
{"sub": "ynUlGbsqlM", "name": "Sam Clark", "given_name": "Sam",
 "family_name": "Clark", "email": "369samclarkisfine@gmail.com",
 "email_verified": true, "picture": "...", "locale": {"country": "US", ...}}
```

`sub` is the person id. Author URN for posting: `urn:li:person:{sub}`.

## Create text post — POST /rest/posts (scope: w_member_social)

```json
{
  "author": "urn:li:person:ynUlGbsqlM",
  "commentary": "Post text here (max 3000 chars)",
  "visibility": "PUBLIC",
  "distribution": {
    "feedDistribution": "MAIN_FEED",
    "targetEntities": [],
    "thirdPartyDistributionChannels": []
  },
  "lifecycleState": "PUBLISHED",
  "isReshareDisabledByAuthor": false
}
```

Success: HTTP 201; the new post's URN is in the `x-restli-id` response
header (`urn:li:share:...` or `urn:li:ugcPost:...`). Public URL:
`https://www.linkedin.com/feed/update/{urn}/`.

Scope probe (safe, publishes nothing): POSTing `{}` returns HTTP 422
listing missing required fields — that 422 (not 403) proves `w_member_social`
is granted.

## Commentary escaping (critical)

The `commentary` field is NOT plain text — LinkedIn parses it as "little
text", where `\ | { } @ [ ] ( ) < > # * _ ~` are reserved. The first
UNESCAPED reserved character silently truncates the post from that point
onward (HTTP 201, no error; the rendered post just ends mid-sentence).
The CLI's `escape_commentary()` backslash-escapes every reserved char
before sending, so what you write is what renders. Never bypass it.
Verified 2026-10-08: two posts truncated at the first `(` before the fix.

## List own posts — GET /rest/posts?q=author (scope: r_member_social)

```
GET /rest/posts?author={url-encoded urn:li:person:...}&q=author&count=10&sortBy=LAST_MODIFIED
```

**Currently 403s**: `ACCESS_DENIED ... Not enough permissions to access:
partnerApiPosts`. `r_member_social` is restricted to approved LinkedIn
partners; a self-serve developer app does not get it. Needs a Products-tab
approval in the LinkedIn Developer Portal before this works.

## Engagement (best-effort)

Per post URN (URL-encoded), likes/comments totals come from the Social
Actions API:

```
GET /v2/socialActions/{encodedUrn}/likes?count=1      -> paging.total
GET /v2/socialActions/{encodedUrn}/comments?count=1    -> paging.total
```

These likely need the same restricted read scope; the CLI treats failures
as "n/a" rather than erroring.

## Token lifetime

Access tokens last ~60 days (`expires_in` on mint). There is no
long-lived token; on 401, re-mint in the Developer Portal and reconnect
via `credentials.request_api_access` with `reconnect=true`.
