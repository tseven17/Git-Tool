# Multi-Profile GitHub Selection Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the single-token auth system with a multi-profile system that asks the user which GitHub account to use at startup, remembers the default, fixes credential routing on Windows by embedding tokens in remote URLs, shows a clickable link to the detected repo, and lets users pick a target folder instead of always using CWD.

**Architecture:** All changes are self-contained in `github_automator.py`. The config file at `~/.config/coi_automator/github_token.json` is extended to hold multiple named profiles keyed by GitHub login. On startup, `main()` runs three new steps: profile selection, directory selection, repo info display + credential patching. The token-in-URL approach is applied whenever a remote is set or updated.

**Tech Stack:** Python 3, stdlib only (`json`, `os`, `subprocess`, `pathlib`, `stat`), `requests` (already auto-installed).

---

## Important context before starting

- The entire tool is a single file: `github_automator.py`
- No test framework is set up — verification is done by running the script and checking output
- The old config format is `{"token": "ghp_..."}` — must be auto-migrated
- Windows Terminal supports OSC 8 hyperlinks; other terminals will just show plain text (that's fine)
- The `run_cmd` helper returns `(bool, str)` — use it for all git commands
- `CONFIG_DIR`, `TOKEN_FILE` are module-level constants — keep them, they're used in file permission code

---

### Task 1: Add config load/save helpers and auto-migration

**Files:**
- Modify: `github_automator.py` — add after the `TOKEN_FILE` constant (around line 31)

**Step 1: Read the file to confirm insertion point**

Read `github_automator.py` lines 28–35 to confirm `TOKEN_FILE` is defined around line 31.

**Step 2: Insert `load_config()` and `save_config()` after the TOKEN_FILE line**

Add these two functions immediately after the `TOKEN_FILE = CONFIG_DIR / "github_token.json"` line:

```python
def load_config():
    """
    Loads the multi-profile config. Automatically migrates the old single-token
    format {"token": "..."} to the new {"default_profile": ..., "profiles": {...}} format.
    Returns a dict. If the file doesn't exist or is unreadable, returns an empty config.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    empty = {"default_profile": None, "profiles": {}}

    if not TOKEN_FILE.exists():
        return empty

    try:
        if os.name == 'nt':
            subprocess.run(["attrib", "-H", str(TOKEN_FILE)], capture_output=True)
        with open(TOKEN_FILE, 'r') as f:
            data = json.load(f)
    except Exception:
        return empty

    # Migrate old single-token format
    if "token" in data and "profiles" not in data:
        old_token = data["token"]
        # Fetch username from GitHub to use as profile key
        try:
            res = requests.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {old_token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28"
                }
            )
            if res.status_code == 200:
                info = res.json()
                login = info.get("login", "default")
                name  = info.get("name") or login
                email = info.get("email") or ""
                migrated = {
                    "default_profile": login,
                    "profiles": {
                        login: {"token": old_token, "login": login, "name": name, "email": email}
                    }
                }
                save_config(migrated)
                return migrated
        except Exception:
            pass
        # Fallback: store with key "default"
        migrated = {
            "default_profile": "default",
            "profiles": {
                "default": {"token": old_token, "login": "default", "name": "", "email": ""}
            }
        }
        save_config(migrated)
        return migrated

    return data


def save_config(config):
    """Writes the config dict to TOKEN_FILE, hiding it on Windows."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Remove hidden attribute before overwriting (Windows)
    if TOKEN_FILE.exists():
        try:
            if os.name == 'nt':
                subprocess.run(["attrib", "-H", str(TOKEN_FILE)], capture_output=True)
            TOKEN_FILE.chmod(stat.S_IWRITE | stat.S_IREAD)
        except Exception:
            pass
    with open(TOKEN_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    try:
        if os.name == 'nt':
            subprocess.run(["attrib", "+H", str(TOKEN_FILE)], capture_output=True)
        else:
            TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass
```

**Step 3: Manual verification**

Run `python github_automator.py` — it will fail because `select_profile` doesn't exist yet, but the script should at least import without error. If there's a syntax error, fix it before proceeding.

**Step 4: Commit**

```bash
git add github_automator.py
git commit -m "feat: add load_config/save_config with auto-migration from single-token format"
```

---

### Task 2: Add `add_profile()` helper

**Files:**
- Modify: `github_automator.py` — add after `save_config()`

**Step 1: Insert `add_profile()` after `save_config()`**

```python
def add_profile(config):
    """
    Interactively prompts for a new GitHub PAT, verifies it, and saves the profile.
    Uses the GitHub login as the profile key automatically.
    Returns the updated config and the new login name.
    """
    def get_headers(pat):
        return {
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }

    print_header("🔑 ADD GITHUB PROFILE")
    print("To add a GitHub profile, we need a Personal Access Token (PAT) from that account.")
    print(f"Generate one at: {Colors.CYAN}https://github.com/settings/tokens/new?scopes=repo{Colors.ENDC}\n")

    while True:
        token = input(f"{Colors.BOLD}Paste your PAT here and press Enter: {Colors.ENDC}").strip()
        print(f"{Colors.CYAN}Verifying token...{Colors.ENDC}")

        try:
            res = requests.get("https://api.github.com/user", headers=get_headers(token))
        except Exception as e:
            print(f"{Colors.FAIL}Network error: {e}{Colors.ENDC}")
            continue

        if res.status_code == 200:
            info  = res.json()
            login = info.get("login", "")
            name  = info.get("name") or login
            email = info.get("email") or ""

            if not email:
                email = input(f"GitHub didn't share your email. Enter it manually (for git commits): {Colors.GREEN}").strip()
                print(Colors.ENDC, end="")

            config.setdefault("profiles", {})[login] = {
                "token": token, "login": login, "name": name, "email": email
            }
            if not config.get("default_profile"):
                config["default_profile"] = login

            save_config(config)
            print(f"{Colors.GREEN}✔ Profile '{login}' saved.{Colors.ENDC}")
            return config, login
        else:
            print(f"{Colors.FAIL}✖ That token didn't work. Please check it and try again.{Colors.ENDC}")
```

**Step 2: Commit**

```bash
git add github_automator.py
git commit -m "feat: add add_profile() for interactive PAT entry with GitHub API verification"
```

---

### Task 3: Add `select_profile()` replacing `get_github_auth()`

**Files:**
- Modify: `github_automator.py` — add after `add_profile()`

**Step 1: Insert `select_profile()`**

```python
def select_profile():
    """
    Shows a profile selection menu. On first run (no profiles) goes straight to add_profile.
    Returns (token, login, name, email) for the selected profile.
    """
    config = load_config()
    profiles = config.get("profiles", {})

    # First time — no profiles at all
    if not profiles:
        print_header("🔑 GITHUB LOGIN — FIRST TIME SETUP")
        print("We need a GitHub Personal Access Token to get started.")
        config, login = add_profile(config)
        profiles = config["profiles"]
        profile = profiles[login]
        return profile["token"], profile["login"], profile["name"], profile["email"]

    default = config.get("default_profile") or list(profiles.keys())[0]
    logins  = list(profiles.keys())

    print_header("SELECT GITHUB PROFILE")
    for i, key in enumerate(logins, 1):
        marker = " ← default" if key == default else ""
        print(f"  {i}. {key}{Colors.CYAN}{marker}{Colors.ENDC}")
    print(f"  {len(logins) + 1}. Add a new profile")

    default_idx = logins.index(default) + 1 if default in logins else 1
    raw = input(f"\nEnter choice [{default_idx}]: {Colors.GREEN}").strip()
    print(Colors.ENDC, end="")

    if raw == "":
        choice = default_idx
    else:
        try:
            choice = int(raw)
        except ValueError:
            choice = default_idx

    # Add new profile
    if choice == len(logins) + 1:
        config, login = add_profile(config)
        profiles = config["profiles"]
        config["default_profile"] = login
        save_config(config)
        profile = profiles[login]
        return profile["token"], profile["login"], profile["name"], profile["email"]

    # Select existing profile (clamp to valid range)
    choice = max(1, min(choice, len(logins)))
    selected_login = logins[choice - 1]
    config["default_profile"] = selected_login
    save_config(config)

    profile = profiles[selected_login]
    print(f"{Colors.GREEN}✔ Using profile: {Colors.BOLD}{selected_login}{Colors.ENDC}")
    return profile["token"], profile["login"], profile["name"], profile["email"]
```

**Step 2: Commit**

```bash
git add github_automator.py
git commit -m "feat: add select_profile() with numbered menu and default memory"
```

---

### Task 4: Add `select_target_directory()` and `display_repo_info()`

**Files:**
- Modify: `github_automator.py` — add after `select_profile()`

**Step 1: Insert both functions**

```python
def select_target_directory():
    """
    Asks the user whether to use the current working directory or specify a different path.
    Returns the validated absolute path as a string.
    """
    current = os.getcwd()
    print(f"\n{Colors.BOLD}Target folder:{Colors.ENDC} {Colors.CYAN}{current}{Colors.ENDC}")
    ans = input("Use this folder? (Y/n): ").strip().lower()
    if ans != 'n':
        return current

    while True:
        path = input(f"Enter the full folder path: {Colors.GREEN}").strip().strip('"').strip("'")
        print(Colors.ENDC, end="")
        if os.path.isdir(path):
            return path
        print(f"{Colors.FAIL}✖ That folder doesn't exist. Please try again.{Colors.ENDC}")


def _make_hyperlink(url, label):
    """Returns an OSC 8 terminal hyperlink. Falls back to plain text on unsupported terminals."""
    # OSC 8 is supported by Windows Terminal, iTerm2, most modern terminals.
    return f"\033]8;;{url}\033\\{label}\033]8;;\033\\"


def _embed_token_in_url(remote_url, token):
    """
    Returns a remote URL with the PAT embedded for credential-free push/pull.
    e.g. https://github.com/owner/repo.git  →  https://ghp_xxx@github.com/owner/repo.git
    """
    if remote_url.startswith("https://"):
        # Remove any existing credentials
        without_scheme = remote_url[len("https://"):]
        if "@" in without_scheme:
            without_scheme = without_scheme.split("@", 1)[1]
        return f"https://{token}@{without_scheme}"
    # SSH or other protocols — return unchanged
    return remote_url


def _parse_github_owner_repo(remote_url):
    """
    Parses owner and repo name from an HTTPS or SSH GitHub remote URL.
    Returns (owner, repo) or (None, None) if not a GitHub URL.
    """
    if "github.com" not in remote_url:
        return None, None
    try:
        if remote_url.startswith("http"):
            # Strip credentials if present
            without_scheme = remote_url[remote_url.index("github.com"):]
            parts = without_scheme.rstrip("/").rstrip(".git").split("/")
            return parts[1], parts[2]
        elif remote_url.startswith("git@"):
            path_part = remote_url.split(":")[-1].rstrip(".git")
            parts = path_part.split("/")
            return parts[0], parts[1]
    except (IndexError, ValueError):
        pass
    return None, None


def display_repo_info(target_dir, token, login, name, email):
    """
    If target_dir is a git repo with a GitHub remote:
    - Shows the repo name as a clickable terminal hyperlink
    - Updates the remote URL to embed the PAT (bypasses Windows Credential Manager)
    - Sets local git user.name and user.email to match the selected profile
    """
    is_repo, _ = run_cmd("git rev-parse --is-inside-work-tree", cwd=target_dir, hide_output=True)
    if not is_repo:
        return

    ok, remote_url = run_cmd(["git", "remote", "get-url", "origin"], cwd=target_dir, hide_output=True)
    if not ok or not remote_url.strip():
        return

    remote_url = remote_url.strip()
    owner, repo = _parse_github_owner_repo(remote_url)

    if owner and repo:
        gh_url = f"https://github.com/{owner}/{repo}"
        link   = _make_hyperlink(gh_url, f"{owner}/{repo}")
        print(f"\n{Colors.CYAN}Detected repo:{Colors.ENDC} {Colors.BOLD}{link}{Colors.ENDC}")
        print(f"  {Colors.CYAN}{gh_url}{Colors.ENDC}")

        # Patch remote URL to embed token — ensures correct account is used for push/pull
        token_url = _embed_token_in_url(remote_url, token)
        run_cmd(["git", "remote", "set-url", "origin", token_url], cwd=target_dir, hide_output=True)

    # Set local git identity to match the selected profile
    if name:
        run_cmd(["git", "config", "--local", "user.name",  name],  cwd=target_dir, hide_output=True)
    if email:
        run_cmd(["git", "config", "--local", "user.email", email], cwd=target_dir, hide_output=True)
    if name or email:
        print(f"{Colors.GREEN}✔ Git identity set to: {name} <{email}>{Colors.ENDC}")
```

**Step 2: Commit**

```bash
git add github_automator.py
git commit -m "feat: add directory picker, repo info display, OSC 8 hyperlink, and token-in-URL helper"
```

---

### Task 5: Wire everything into `main()` and retire `get_github_auth()`

**Files:**
- Modify: `github_automator.py` — the `main()` function (around line 932) and `get_github_auth()` (around line 169)

**Step 1: Read the current `main()` function**

Read lines 932–965 to see the exact current body before editing.

**Step 2: Replace `main()` with the new version**

Replace the entire `main()` function body with:

```python
def main():
    print(f"{Colors.BOLD}{Colors.BLUE}")
    print("=====================================================")
    print("          GITHUB AUTO-PILOT (Beginner Friendly)      ")
    print("=====================================================")
    print(f"{Colors.ENDC}")

    check_git_installed()
    ensure_git_configured()

    # Step 1: Choose GitHub profile
    token, login, name, email = select_profile()

    # Step 2: Choose target directory
    target_dir = select_target_directory()

    # Step 3: Show repo info, patch remote URL with token, set local git identity
    display_repo_info(target_dir, token, login, name, email)

    # Step 4: Route to new-project or existing-project workflow
    is_git_repo, _ = run_cmd("git rev-parse --is-inside-work-tree", cwd=target_dir, hide_output=True)

    if is_git_repo:
        handle_existing_project(token, target_dir)
    else:
        handle_new_project(token, target_dir)
```

**Step 3: Delete (or keep as dead code) `get_github_auth()`**

Remove the entire `get_github_auth()` function (lines ~169–238) since it is fully replaced by `select_profile()`. The function is not called anywhere else.

**Step 4: Run a quick manual smoke test**

```
python github_automator.py
```

Expected on first run (clean config): shows "ADD GITHUB PROFILE" prompt.
Expected on subsequent runs: shows profile selection menu with the previous profile as default.

Check that pressing Enter at the profile menu selects the default without error.
Check that the target folder prompt works.

**Step 5: Commit**

```bash
git add github_automator.py
git commit -m "feat: wire select_profile, select_target_directory, and display_repo_info into main()"
```

---

### Task 6: Update `handle_new_project()` to use token-embedded remote URL

**Files:**
- Modify: `github_automator.py` — `handle_new_project()` (around line 263)

**Step 1: Read `handle_new_project()` to find the `git remote add origin` line**

Find the line: `run_cmd(["git", "remote", "add", "origin", repo_url], cwd=target_dir)`

**Step 2: Replace that line to embed the token in the URL**

Old:
```python
run_cmd(["git", "remote", "add", "origin", repo_url], cwd=target_dir)
```

New:
```python
token_url = _embed_token_in_url(repo_url, token)
run_cmd(["git", "remote", "add", "origin", token_url], cwd=target_dir)
```

Note: `handle_new_project` receives `token` as a parameter already — no signature change needed.

**Step 3: Also update `handle_existing_project()` option 3 (change remote)**

Find the line in option 3 (`choice == '3'`):
```python
run_cmd(["git", "remote", "add", "origin", repo_url], cwd=target_dir)
```

Replace with:
```python
token_url = _embed_token_in_url(repo_url, token)
run_cmd(["git", "remote", "add", "origin", token_url], cwd=target_dir)
```

**Step 4: Commit**

```bash
git add github_automator.py
git commit -m "fix: embed PAT in remote URL for new repos and change-remote to bypass Windows Credential Manager"
```

---

### Task 7: Final end-to-end verification

**Step 1: Test profile addition**

Run the script. If you have a clean config (or rename the token file temporarily), verify:
- "ADD GITHUB PROFILE" flow appears
- Bad token shows the error message and re-prompts
- Good token saves and shows the username

**Step 2: Test profile switching**

If you have two PATs available, add a second profile and verify:
- Both profiles appear in the menu
- Selecting profile 2 prints "Using profile: <login>"
- The default updates so the next run pre-selects the last-used profile

**Step 3: Test repo detection and hyperlink**

Run in a folder that has a GitHub remote. Verify:
- "Detected repo: owner/repo" line appears
- The URL printed below it is correct
- Running `git remote get-url origin` from that folder now shows the token-embedded URL

**Step 4: Test directory picker**

Run in one folder, choose "n" when asked about the current folder, enter a different valid path. Verify the tool operates on the entered path.

**Step 5: Commit final state**

```bash
git add github_automator.py
git commit -m "chore: verified multi-profile flow, token-in-URL, repo info display, and directory picker"
```

---

## Rollback

If anything breaks, `TOKEN_FILE` still exists on disk in the old format. `load_config()` will migrate it on next run. No data is lost.

To test migration manually: edit `~/.config/coi_automator/github_token.json` to contain `{"token": "ghp_..."}` and run the script — it should silently convert the file and continue.
