# Security notes

This repo is **public**. Treat anything that touches your accounts as toxic by default.

## Never commit

- `.env` (real values) — only `.env.example` is tracked
- Anything inside `cookies/`, `sessions/`, `playwright-profile/`
  These hold the cookies that keep you logged into **Onshape** and **Gemini web**.
  Leaking them is account takeover.
- Anything inside `logs/` — may contain doc URLs, request IDs, partial screenshots paths
- Anything inside `state/` — the action journal records every UI op + screenshot of your documents

All of the above are in `.gitignore` at install. **Do not edit the `.gitignore` to
re-add them.** If you accidentally stage a sensitive file:

```bash
git rm --cached <file>
git commit --amend --no-edit
```

If a secret has been pushed:

1. Rotate the secret immediately (log out everywhere, change password, revoke sessions)
2. `git filter-repo` or BFG to scrub history
3. Force-push

## How secrets enter the system

| Secret              | How it's obtained                                       | Where it lives         |
|---------------------|---------------------------------------------------------|------------------------|
| Onshape session     | First-time `python -m onshape_mcp.driver login`         | `playwright-profile/`  |
| Gemini web cookies  | Browser extension export (e.g. `cookies.txt` style)     | `cookies/gemini.cookies.json` |

The repo contains no baked-in credentials. It cannot do anything useful without you
providing your own session.

## Reporting issues

Open a GitHub issue or DM the maintainer. Do not paste secrets into issues.
