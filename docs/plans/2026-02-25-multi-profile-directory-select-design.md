# Design: Multi-Profile GitHub Selection + Directory Picker + Repo Info Display

**Date:** 2026-02-25
**Status:** Approved

---

## Problem

1. The tool stores only a single GitHub token — users with multiple accounts push to the wrong one.
2. Windows Credential Manager intercepts git push credentials, overriding the stored token.
3. The tool always uses the current working directory — no way to target a different folder.
4. After launching, there is no confirmation of which repo you are working on.

---

## Goals

1. Support multiple named GitHub profiles (PATs + identity), defaulting to a remembered choice.
2. Guarantee the correct account is used for every push by embedding the token in the remote URL (bypasses Windows Credential Manager).
3. Show a terminal hyperlink to the detected GitHub repo after startup.
4. Let the user specify a different target folder at startup instead of always using CWD.

---

## Config File Schema

**Location:** `~/.config/coi_automator/github_token.json`

```json
{
  "default_profile": "myuser",
  "profiles": {
    "myuser":   {"token": "ghp_...", "login": "myuser",   "name": "My Name", "email": "me@example.com"},
    "workuser": {"token": "ghp_...", "login": "workuser", "name": "My Name", "email": "me@work.com"}
  }
}
```

Profile labels are automatically set to the GitHub login username (no manual label entry).

**Migration:** If the old `{"token": "..."}` format is detected, automatically migrate it by
querying the API for the username and converting to the new schema with that username as the profile key.

---

## Startup Flow (replaces current `main()` pre-amble)

### Step 1 — Profile Selection (`select_profile()`)

```
=== SELECT GITHUB PROFILE ===
1. myuser    ← default
2. workuser
3. Add a new profile

Enter choice [1]:
```

- Default is the stored `default_profile`; pressing Enter accepts it.
- After selection, save chosen profile as the new `default_profile`.
- Returns `(token, login, name, email)`.

**First-time (no profiles):** Skip the menu; go straight to PAT entry, save profile, continue.

**Add new profile:** Run PAT entry flow → verify via GitHub API → store under the GitHub login as key.

### Step 2 — Target Directory Selection

```
=== SELECT TARGET FOLDER ===
Current folder: C:\Users\tseven\Projects\my-site

1. Use this folder (current directory)
2. Enter a different folder path

Enter choice [1]:
```

- Option 2 prompts for a path, validates it exists.
- Returns `target_dir`.

### Step 3 — Repo Info Display

If `target_dir` is a git repo with a GitHub remote:
- Parse owner/repo from remote URL.
- Print: `Detected repo: owner/repo` with an OSC 8 terminal hyperlink to `https://github.com/owner/repo`.
- Silently update the remote URL to `https://<token>@github.com/owner/repo.git` (ensures correct account for push/pull).
- Run `git config --local user.name` and `git config --local user.email` using the selected profile.

If not a git repo, no repo info is shown; proceed to `handle_new_project()` as before.

---

## Token-in-URL Approach

Every time a remote is set or updated:
- Format: `https://<token>@github.com/<owner>/<repo>.git`
- Applied in: `handle_new_project()` (initial push), `handle_existing_project()` option 3 (change remote), and on startup for existing repos.
- This completely bypasses Windows Credential Manager.

---

## Functions Changed

| Function | Change |
|---|---|
| `get_github_auth()` | Replaced by `select_profile()` |
| `main()` | Add directory selection step; add repo info display step |
| `create_remote_repo()` | Returns token-embedded URL |
| `handle_new_project()` | Use token-embedded remote URL when adding origin |
| `handle_existing_project()` option 3 | Use token-embedded URL |
| *(new)* `load_config()` / `save_config()` | Read/write the new multi-profile JSON |
| *(new)* `add_profile()` | PAT entry + API verify + save |
| *(new)* `display_repo_info()` | Parse remote, print OSC 8 hyperlink, patch remote URL, set local git identity |

---

## Out of Scope

- Subfolder extraction into a new repo (not requested).
- Per-repo profile memory (global default is sufficient).
- Profile deletion UI (can be done manually in the JSON file for now).
