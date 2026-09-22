# Continue TerrisIQ from your phone

A complete, self-contained mobile workflow. Repo: **github.com/jitheshkhanna/TerrisIQ** (private).

---

## One-time setup (5 min, do once)

1. **Claude Code on web** — on your phone open **claude.ai/code** in Safari/Chrome.
   Tap Share → **Add to Home Screen** so it opens like an app.
2. Sign in with the same account you use on desktop.
3. **Connect GitHub** when prompted → authorize → pick the **TerrisIQ** repo.
4. **GitHub mobile app** (optional but handy) — install from the App Store, sign in.
   Use it to review and merge pull requests on a small screen.

That's it. From now on the loop below is all you need.

---

## The daily loop (chat → code → push)

1. Open the **claude.ai/code** icon on your home screen.
2. Start a chat on the TerrisIQ repo. If it's a fresh chat, paste in
   **HANDOFF.md** (at the repo root) so it knows where things stand.
3. Ask for the change in plain English, e.g.
   _"Add a MagicBricks content-script matcher to the extension"_.
4. Claude edits in a cloud copy of the repo, shows you a diff, and — when you
   approve — **commits and pushes** (or opens a pull request).
5. Review the PR in the **GitHub mobile app**, tap **Merge**.

You never touch a terminal. Everything happens in the browser + GitHub app.

---

## Catching a new chat up on context

Every fresh mobile chat starts blank. To orient it fast, paste the contents of
**HANDOFF.md** (repo root) as your first message. It summarizes the product,
what's deployed, and the open to-dos.

---

## Editing a file by hand (no Claude)

Two options from a phone browser:
- **github.dev** — open the repo on github.com, change the URL from
  `github.com` to `github.dev` (or press `.`). This is browser VS Code; edit,
  then Source Control tab → commit. Cramped on a phone but works.
- **GitHub mobile app** — open a file → pencil icon → edit → commit. Best for
  tiny one-line tweaks.

---

## Deploying from mobile (important)

Right now the Vercel projects deploy via the CLI (`vercel --prod`), which you
**can't run from a phone**. To make pushes deploy automatically:

1. On desktop (once), go to **vercel.com** → project **chennai-terra-risk** →
   Settings → **Git** → connect it to the **TerrisIQ** repo, root dir `frontend`.
2. Do the same for **chennai-terra-risk-api**, root dir `backend`.

After that, **every push to `main` auto-deploys** — so a change you make from
your phone goes live with no terminal. Until then, code pushes reach GitHub but
the live site updates only when someone runs the CLI deploy.

---

## What you can and can't do from mobile

| Task | Mobile? | How |
|------|---------|-----|
| Chat + edit + push code | Yes | claude.ai/code |
| Review / merge PRs | Yes | GitHub mobile app |
| Hand-edit a file | Yes | github.dev or GitHub app |
| Auto-deploy on push | Yes* | *after linking Vercel to the repo (above) |
| Run `vercel --prod` CLI | No | needs a computer |
| Chrome Web Store dashboard | Partly | works in mobile browser, fiddly |

---

## Quick links
- Repo: https://github.com/jitheshkhanna/TerrisIQ
- Claude Code web: https://claude.ai/code
- Live app: https://chennai-terra-risk.vercel.app
- Privacy policy: https://chennai-terra-risk.vercel.app/privacy
