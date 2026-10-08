# LinkedIn skill for Muse

Drop-in LinkedIn skill for Meta's Muse AI: publish posts, read your profile, and list recent posts. Secure token-based connector — just bring your own LinkedIn access token:

> 🌐 **Live site:** https://gman0n.github.io/muse-linkedin-skill/
> 📦 **One-click download page:** https://muse.ai/s/linkedin-skill-for-muse-xby6bxyjxjxmqhxr

- `profile` — read your profile (name, headline, LinkedIn ID)
- `post` — publish a text post (**only** with your explicit approval of the exact text, every time)
- `posts` — list your recent posts (needs an extra LinkedIn approval — see below)

## What you need (no client ID, no client secret)

Just one thing: **your own LinkedIn access token**. The skill never needs
anyone's client ID or client secret — those stay with whoever owns the
LinkedIn developer app.

To get your token:

1. Go to the [LinkedIn Developer Portal](https://developer.linkedin.com/) and
   open (or create) an app.
2. Under **Products**, enable what you want the skill to do:
   - **Share on LinkedIn** → lets the skill publish posts (`w_member_social`)
   - **Sign In with LinkedIn using OpenID Connect** → lets the skill read your profile (`openid profile email`)
   - Reading your own posts back requires a partner-restricted product —
     request it in the Products tab if you want it; without it the `posts`
     command reports "not approved" instead of failing silently.
3. Use the portal's **token generator** to mint an access token with those
   scopes. Copy it.

## Connect it in Muse

1. Copy the `linkedin/` folder from this repo into your Muse workspace at
   `~/workspace/skills/linkedin/`.
2. In chat, ask Muse: *"set up a LinkedIn connector."*
   Muse will give you a secure form — paste your access token there.
   It goes straight to the platform vault; never paste it in chat.
   (Technical detail: it's stored as a custom connector sending the token as
   a Bearer credential to `api.linkedin.com`.)
3. Done. Try: *"read my LinkedIn profile."*

## Notes

- LinkedIn access tokens last ~60 days. When one expires, re-mint it in the
  Developer Portal and reconnect — the skill tells you exactly this on a 401.
- Posting **always** requires your explicit approval of the exact post text
  in chat first. The skill shows you the text and waits for your go-ahead.
- Your agent never sees your raw token — requests carry a surrogate that the
  platform swaps on the way out.
- Authenticated requests go only to `api.linkedin.com`.

## Files

- `linkedin/SKILL.md` — the skill definition (what it does, auth, rules)
- `linkedin/bin/linkedin.py` — the CLI the skill runs
- `linkedin/references/api-notes.md` — verified endpoints, headers, version pins
