# Security

This repo is public. Anything that touches my accounts is toxic by default.

## Never commit

- `.env` (real values). Only `.env.example` is tracked.
- Anything in `cookies/`, `sessions/`, `playwright-profile/`. These hold
  the cookies that keep me logged into Onshape and Gemini web. Leaking
  them is account takeover.
- Anything in `logs/`. May contain doc URLs, request IDs, partial paths.
- Anything in `state/`. The action journal records every UI op plus
  screenshots of my documents.

All of the above are in `.gitignore` from the first commit. I don't edit
that ignore list. If I accidentally stage a sensitive file:

```bash
git rm --cached <file>
git commit --amend --no-edit
```

If a secret has been pushed:

1. Rotate the secret immediately. Log out everywhere, change the
   password, revoke sessions.
2. Scrub history with `git filter-repo` or BFG.
3. Force-push.

## How secrets enter the system

| Secret | How I get it | Where it lives |
|--------|--------------|----------------|
| Onshape session | `python scripts/bootstrap.py` (one-time headed login) | `playwright-profile/` |
| Gemini web cookies | `python scripts/extract_gemini_cookies.py` (one-time headed login) | `cookies/gemini.cookies.json` |

The repo ships with no baked-in credentials. It can't do anything useful
without me providing my own session.

## Reporting issues

GitHub issue or DM. Don't paste secrets into issues.
