import os
import sys
import subprocess
import json
import stat
import glob
import shutil
from pathlib import Path

# Automatically install the 'requests' tool if the user doesn't have it
try:
    import requests
except ImportError:
    print("Installing a small tool needed to talk to GitHub... please wait.")
    subprocess.run([sys.executable, "-m", "pip", "install", "requests"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import requests

class Colors:
    """Colors to make the text easier to read."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

CONFIG_DIR = Path.home() / ".config" / "coi_automator"
TOKEN_FILE = CONFIG_DIR / "github_token.json"


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
    if os.name != 'nt' and not TOKEN_FILE.exists():
        # Pre-create with restricted permissions to avoid world-readable window
        fd = os.open(str(TOKEN_FILE), os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(fd)
    with open(TOKEN_FILE, 'w') as f:
        json.dump(config, f, indent=2)
    try:
        if os.name == 'nt':
            subprocess.run(["attrib", "+H", str(TOKEN_FILE)], capture_output=True)
        else:
            TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass


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
    print(f"Generate one at: {Colors.CYAN}https://github.com/settings/tokens/new?scopes=repo{Colors.ENDC}")
    print()

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
        return profile.get("token", ""), profile.get("login", login), profile.get("name", login), profile.get("email", "")

    stored_default = config.get("default_profile")
    default = stored_default if stored_default in profiles else list(profiles.keys())[0]
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
        return profile.get("token", ""), profile.get("login", login), profile.get("name", login), profile.get("email", "")

    # Select existing profile (clamp to valid range)
    choice = max(1, min(choice, len(logins)))
    selected_login = logins[choice - 1]
    config["default_profile"] = selected_login
    save_config(config)

    profile = profiles[selected_login]
    print(f"{Colors.GREEN}✔ Using profile: {Colors.BOLD}{selected_login}{Colors.ENDC}")
    return profile.get("token", ""), profile.get("login", selected_login), profile.get("name", selected_login), profile.get("email", "")

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
    return chr(27) + f"]8;;{url}" + chr(27) + chr(92) + label + chr(27) + "]8;;" + chr(27) + chr(92)


def _embed_token_in_url(remote_url, token):
    """
    Returns a remote URL with the PAT embedded for credential-free push/pull.
    e.g. https://github.com/owner/repo.git  ->  https://ghp_xxx@github.com/owner/repo.git
    """
    if remote_url.startswith("https://"):
        without_scheme = remote_url[len("https://"):]
        if "@" in without_scheme:
            without_scheme = without_scheme.split("@", 1)[1]
        return f"https://{token}@{without_scheme}"
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
            without_scheme = remote_url[remote_url.index("github.com"):]
            without_scheme = without_scheme.removesuffix(".git").rstrip("/")
            parts = without_scheme.split("/")
            return parts[1], parts[2]
        elif remote_url.startswith("git@"):
            path_part = remote_url.split(":")[-1].removesuffix(".git")
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

        token_url = _embed_token_in_url(remote_url, token)
        run_cmd(["git", "remote", "set-url", "origin", token_url], cwd=target_dir, hide_output=True)

    if name:
        run_cmd(["git", "config", "--local", "user.name",  name],  cwd=target_dir, hide_output=True)
    if email:
        run_cmd(["git", "config", "--local", "user.email", email], cwd=target_dir, hide_output=True)
    if name or email:
        identity_parts = []
        if name:
            identity_parts.append(name)
        if email:
            identity_parts.append(f"<{email}>")
        print(f"{Colors.GREEN}✔ Git identity set to: {' '.join(identity_parts)}{Colors.ENDC}")

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}=== {text} ==={Colors.ENDC}")

def run_cmd(cmd, cwd=None, hide_output=False):
    """Runs an invisible computer command. Accepts lists for safe variable injection."""
    use_shell = isinstance(cmd, str)
    result = subprocess.run(
        cmd, 
        cwd=cwd, 
        shell=use_shell, 
        text=True, 
        capture_output=True
    )
    # Combine standard output and standard error
    output = (result.stdout + "\n" + result.stderr).strip()
    if result.returncode != 0 and not hide_output:
        cmd_str = cmd if isinstance(cmd, str) else " ".join(cmd)
        print(f"{Colors.FAIL}Oops, something went wrong running a background task: {cmd_str}\n{output}{Colors.ENDC}")
    return result.returncode == 0, output

# Windows device names that git cannot index as regular files
WINDOWS_RESERVED_NAMES = {
    "nul", "con", "prn", "aux",
    "com0", "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
    "lpt0", "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
}

def find_reserved_filenames(target_dir):
    """Finds files or directories with Windows-reserved names that git cannot index."""
    found = []
    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d != '.git']
        for name in files + dirs:
            if name.lower() in WINDOWS_RESERVED_NAMES:
                found.append(os.path.relpath(os.path.join(root, name), target_dir))
    return found

def safe_git_add(target_dir):
    """
    Runs 'git add .' and gracefully handles Windows-reserved filename errors
    (e.g. a file literally named 'nul', 'con', 'aux', etc.).
    Returns True if staging succeeded.
    """
    success, output = run_cmd("git add .", cwd=target_dir, hide_output=True)
    if success:
        return True

    # Detect reserved-filename errors from git's output
    if "unable to index file" in output or "failed to insert into database" in output:
        reserved = find_reserved_filenames(target_dir)
        if reserved:
            print(f"\n{Colors.FAIL}✖ Git could not stage your files because the following item(s) have")
            print(f"   names that are reserved by Windows and cannot be tracked by Git:{Colors.ENDC}")
            for f in reserved:
                print(f"   {Colors.WARNING}• {f}{Colors.ENDC}")
            print(
                f"\n{Colors.CYAN}Names like 'nul', 'con', 'aux', 'com1', etc. are special Windows device\n"
                f"names. Git is unable to add them to its database.{Colors.ENDC}"
            )
            print(
                f"\nHow would you like to fix this?\n"
                f"  1. Add them to .gitignore {Colors.GREEN}(recommended — they will simply be skipped){Colors.ENDC}\n"
                f"  2. Delete them permanently\n"
                f"  3. Abort — leave everything as it is"
            )
            fix_choice = input(f"Choose (1/2/3): {Colors.GREEN}").strip()
            print(Colors.ENDC, end="")

            if fix_choice == '1':
                gitignore_path = os.path.join(target_dir, ".gitignore")
                try:
                    with open(gitignore_path, "a", encoding="utf-8") as gi:
                        gi.write("\n# Windows reserved device names — cannot be tracked by Git\n")
                        for rf in reserved:
                            gi.write(rf.replace("\\", "/") + "\n")
                    print(f"{Colors.GREEN}✔ Added to .gitignore. Re-staging files...{Colors.ENDC}")
                except Exception as e:
                    print(f"{Colors.FAIL}Could not update .gitignore: {e}{Colors.ENDC}")
                    return False
                success2, output2 = run_cmd("git add .", cwd=target_dir, hide_output=True)
                if success2:
                    return True
                print(f"{Colors.FAIL}Staging still failed:\n{output2}{Colors.ENDC}")
                return False

            elif fix_choice == '2':
                for rf in reserved:
                    full_path = os.path.join(target_dir, rf)
                    try:
                        if os.path.isdir(full_path):
                            shutil.rmtree(full_path)
                        else:
                            os.remove(full_path)
                        print(f"{Colors.GREEN}✔ Deleted: {rf}{Colors.ENDC}")
                    except Exception as e:
                        print(f"{Colors.FAIL}Could not delete {rf}: {e}{Colors.ENDC}")
                print(f"{Colors.CYAN}Re-staging files...{Colors.ENDC}")
                success2, output2 = run_cmd("git add .", cwd=target_dir, hide_output=True)
                if success2:
                    return True
                print(f"{Colors.FAIL}Staging still failed:\n{output2}{Colors.ENDC}")
                return False

            else:
                print(f"{Colors.WARNING}Aborted — no changes made.{Colors.ENDC}")
                return False

    # Generic failure — surface the error
    print(f"{Colors.FAIL}Oops, something went wrong running: git add .\n{output}{Colors.ENDC}")
    return False

def check_git_installed():
    """Makes sure the user actually has Git installed on their computer."""
    success, _ = run_cmd("git --version", hide_output=True)
    if not success:
        print(f"{Colors.FAIL}It looks like you don't have Git installed on your computer yet!{Colors.ENDC}")
        print("Git is the engine that saves your file history (version control).")
        print("Please download and install it from here: https://git-scm.com/downloads")
        sys.exit(1)

def ensure_git_configured():
    """Beginners usually don't have their name/email set up. Git requires this to save files."""
    success, name = run_cmd("git config --global user.name", hide_output=True)
    if not success or not name:
        print_header("FIRST TIME SETUP")
        print("Since this is your first time, your computer needs to know who is saving these files (git config).")
        user_name = input(f"Please enter your full name: {Colors.GREEN}").strip()
        print(Colors.ENDC, end="")
        user_email = input(f"Please enter your email address: {Colors.GREEN}").strip()
        print(Colors.ENDC, end="")
        
        # Use lists for commands that include user input to prevent command injection
        run_cmd(["git", "config", "--global", "user.name", user_name])
        run_cmd(["git", "config", "--global", "user.email", user_email])
        print(f"{Colors.GREEN}✔ Identity saved!{Colors.ENDC}")

def create_remote_repo(token, repo_name, private=True):
    """Creates the cloud folder on GitHub."""
    print(f"{Colors.CYAN}Creating your new cloud project (repository) '{repo_name}' on GitHub...{Colors.ENDC}")
    url = "https://api.github.com/user/repos"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    data = {
        "name": repo_name,
        "private": private,
        "description": "Created via Automated Pipeline"
    }
    
    res = requests.post(url, headers=headers, json=data)
    if res.status_code == 201:
        repo_url = res.json().get('clone_url')
        print(f"{Colors.GREEN}✔ Cloud project (repository) created successfully!{Colors.ENDC}")
        return repo_url
    else:
        print(f"{Colors.FAIL}✖ Failed to create it. You might already have a project (repository) with this exact name.{Colors.ENDC}")
        sys.exit(1)

def handle_new_project(token, target_dir):
    """Walks the user through backing up a folder for the very first time."""
    print_header("🚀 NEW PROJECT BACKUP")
    print("It looks like this folder hasn't been saved to GitHub before.")
    
    repo_name = input(f"What do you want to call this project (repository) on GitHub? (No spaces, use dashes instead): {Colors.GREEN}").strip().replace(" ", "-")
    print(Colors.ENDC, end="")
    
    is_private = input("Should this project (repository) be Private (only you can see it)? (Y/n): ").strip().lower() != 'n'
    
    repo_url = create_remote_repo(token, repo_name, is_private)
    
    print(f"{Colors.CYAN}Preparing your files for their first journey to the cloud (git init)...{Colors.ENDC}")
    run_cmd("git init", cwd=target_dir) # Turns the folder into a Git folder

    # Configure .gitignore BEFORE the first git add so secrets are excluded immediately
    configure_gitignore(target_dir)

    print(f"\n{Colors.CYAN}Adding your files to the staging area (git add)...{Colors.ENDC}")
    if not safe_git_add(target_dir):
        print(f"{Colors.FAIL}Staging failed — aborting upload.{Colors.ENDC}")
        return

    print("\nEvery time you save files to GitHub, you attach a little 'Save Note' (commit message) so you remember what you changed.")
    commit_msg = input(f"Type a short note (commit message, e.g. 'First upload of my website'): {Colors.GREEN}") or "First upload"
    print(Colors.ENDC, end="")
    
    run_cmd(["git", "commit", "-m", commit_msg], cwd=target_dir)
    run_cmd("git branch -M main", cwd=target_dir)
    token_url = _embed_token_in_url(repo_url, token)
    run_cmd(["git", "remote", "add", "origin", token_url], cwd=target_dir)
    
    print(f"{Colors.CYAN}Uploading files to GitHub (git push). This might take a second depending on how big the folder is...{Colors.ENDC}")
    success, _ = run_cmd("git push -u origin main", cwd=target_dir)
    
    if success:
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 Success! Your files are safely backed up on GitHub.{Colors.ENDC}")
    else:
        print(f"\n{Colors.WARNING}Something went wrong during the upload (push). Make sure your internet is working.{Colors.ENDC}")

def handle_existing_project(token, target_dir):
    """Handles a folder that is already connected to GitHub."""
    print_header("📁 EXISTING PROJECT FOUND")
    print("This folder is already connected to GitHub (tracked by git). What would you like to do?")

    _, current_branch = run_cmd("git branch --show-current", cwd=target_dir)
    current_branch = current_branch.strip()

    print(f"\n1. {Colors.GREEN}Standard Update (Commit & Push):{Colors.ENDC} Upload my newest changes to GitHub.")
    print(f"2. {Colors.CYAN}Download Updates (Pull):{Colors.ENDC} Fetch and apply the latest changes from GitHub to this computer.")
    print(f"3. {Colors.BLUE}Duplicate/Copy (Change Remote):{Colors.ENDC} Create a brand new separate copy of this project on GitHub.")
    print(f"4. {Colors.WARNING}Safe Playground (Git Worktree):{Colors.ENDC} Create a 'Git Worktree' (A safe, parallel folder for experimenting).")
    print(f"5. {Colors.HEADER}Pull Request (Propose Changes):{Colors.ENDC} Create a new branch and open a Pull Request for review.")
    print(f"6. {Colors.CYAN}Manage .gitignore:{Colors.ENDC} Review and update what files are ignored / kept off GitHub.")
    print(f"7. {Colors.FAIL}Purge File from History:{Colors.ENDC} Permanently erase a sensitive file from ALL past commits.")
    print(f"8. {Colors.CYAN}Skip (Do Nothing):{Colors.ENDC} Leave the repository exactly as it is.")

    choice = input(f"\nSelect an option (1-8): {Colors.GREEN}")
    print(Colors.ENDC, end="")
    
    if choice == '1':
        print("\nYou are about to upload your newest changes (git add & commit).")
        # Offer to update .gitignore before staging files
        update_gi = input(f"Would you like to review your .gitignore before uploading? (y/N): ").strip().lower()
        if update_gi == 'y':
            configure_gitignore(target_dir)
        if not safe_git_add(target_dir):
            print(f"{Colors.FAIL}Staging failed — upload cancelled.{Colors.ENDC}")
            return
        commit_msg = input(f"What did you change? (commit message, e.g. 'Fixed the spelling error on homepage'): {Colors.GREEN}")
        print(Colors.ENDC, end="")

        # We catch the commit command to see if Git rejected it because there were no file changes made
        success, output = run_cmd(["git", "commit", "-m", commit_msg], cwd=target_dir, hide_output=True)

        if success:
            print(f"{Colors.CYAN}Uploading (git push)...{Colors.ENDC}")
            run_cmd(["git", "push", "origin", current_branch], cwd=target_dir)
            print(f"{Colors.GREEN}🎉 Awesome! Your changes are saved on the cloud.{Colors.ENDC}")
        elif "nothing to commit" in output.lower():
            print(f"{Colors.CYAN}No new changes detected. Everything is already up to date!{Colors.ENDC}")
            print(f"{Colors.CYAN}Ensuring cloud is synced (git push)...{Colors.ENDC}")
            run_cmd(["git", "push", "origin", current_branch], cwd=target_dir)
            print(f"{Colors.GREEN}🎉 Awesome! Your files are safely synced.{Colors.ENDC}")
        else:
            print(f"{Colors.FAIL}Oops, something went wrong committing: {output}{Colors.ENDC}")

    elif choice == '2':
        print(f"\n{Colors.CYAN}Checking for the latest updates from GitHub (git pull)...{Colors.ENDC}")
        
        success, output = run_cmd(["git", "pull", "origin", current_branch], cwd=target_dir, hide_output=True)
        
        if success:
            if "Already up to date" in output:
                print(f"{Colors.GREEN}✔ Everything is already up to date! You have the newest files.{Colors.ENDC}")
            else:
                print(f"{Colors.GREEN}🎉 Success! Downloaded the latest changes from GitHub.{Colors.ENDC}")
                print(f"{Colors.CYAN}Here is a summary of what changed:{Colors.ENDC}\n{output}")
        else:
            print(f"{Colors.FAIL}Oops, something went wrong while pulling.{Colors.ENDC}")
            if "conflict" in output.lower() or "local changes" in output.lower():
                print(f"{Colors.WARNING}It looks like you have local changes that conflict with the cloud version.{Colors.ENDC}")
                print("Try committing your changes first (Option 1) and then pull again to merge them.")
            print(f"\n{Colors.CYAN}Technical details:{Colors.ENDC}\n{output}")

    elif choice == '3':
        print("\nWe are going to take your files and upload them as a brand new project (changing git remote).")
        repo_name = input(f"What do you want to call the NEW project (repository)? (No spaces): {Colors.GREEN}").strip().replace(" ", "-")
        print(Colors.ENDC, end="")
        is_private = input("Should this new project (repository) be Private? (Y/n): ").strip().lower() != 'n'

        repo_url = create_remote_repo(token, repo_name, is_private)

        run_cmd("git remote remove origin", cwd=target_dir, hide_output=True) # Disconnect from old
        token_url = _embed_token_in_url(repo_url, token)
        run_cmd(["git", "remote", "add", "origin", token_url], cwd=target_dir) # Connect to new
        safe_git_add(target_dir)
        run_cmd(["git", "commit", "-m", "Copied to a new project"], cwd=target_dir)
        run_cmd("git branch -M main", cwd=target_dir)

        print(f"{Colors.CYAN}Uploading to the new cloud project (git push to new remote)...{Colors.ENDC}")
        run_cmd("git push -u origin main", cwd=target_dir)
        print(f"{Colors.GREEN}🎉 Success! You now have a fresh copy online.{Colors.ENDC}")

    elif choice == '4':
        explain_worktrees()
        print("Let's name this new parallel universe folder (git branch).")
        new_branch = input(f"Enter a short name for the experiment (e.g. 'new-button-test'): {Colors.GREEN}").strip().replace(" ", "-")
        print(Colors.ENDC, end="")

        # Create worktree one directory level up so it sits nicely next to the original folder
        parent_dir = Path(target_dir).parent
        wt_dir_name = f"{Path(target_dir).name}-{new_branch}"
        wt_path = parent_dir / wt_dir_name

        print(f"{Colors.CYAN}Creating your safe playground folder (git worktree) at: {wt_path}...{Colors.ENDC}")
        success, err = run_cmd(["git", "worktree", "add", "-b", new_branch, str(wt_path), "main"], cwd=target_dir)

        if success:
            print(f"\n{Colors.GREEN}✔ Playground (worktree) created successfully!{Colors.ENDC}")
            print(f"{Colors.BOLD}If you open your file explorer, you will see a brand new folder right next to your old one.{Colors.ENDC}")
            print(f"You can open {Colors.BLUE}{wt_path}{Colors.ENDC} and break things inside it without ever hurting your original project.")
        else:
            print(f"{Colors.FAIL}Oops, couldn't create the playground. Make sure you don't have unsaved changes (uncommitted files) in your main folder first.{Colors.ENDC}")

    elif choice == '5':
        create_pull_request(token, target_dir)

    elif choice == '6':
        configure_gitignore(target_dir)
        print(f"\n{Colors.CYAN}Tip: Run Option 1 (Standard Update) next to commit the updated .gitignore to GitHub.{Colors.ENDC}")

    elif choice == '7':
        purge_file_from_history(target_dir)

    elif choice == '8':
        print(f"{Colors.CYAN}Skipping GitHub update. Your repository remains unchanged.{Colors.ENDC}")
        return

def configure_gitignore(target_dir):
    """
    Scans the project for potentially sensitive or unwanted files, shows the
    user what was found, and updates (or creates) .gitignore accordingly.
    Also offers to ignore common large media/binary file types.
    """
    print_header("🔒 .GITIGNORE SETUP — PROTECT SENSITIVE FILES")
    print(
        "Before uploading your files to GitHub, it is important to make sure\n"
        "you are NOT accidentally sharing secret or private information.\n"
        "\nThink of .gitignore as a 'do NOT upload' list. Any file or folder\n"
        "listed there will be completely ignored by GitHub, no matter what.\n"
    )

    # Patterns that are commonly sensitive or unnecessary to commit
    SENSITIVE_CHECKS = [
        # (glob_pattern, human_readable_label, reason_to_ignore)
        (".env",             ".env files (API keys, passwords)",
         "These files often contain secret keys or database passwords that should NEVER be public."),
        (".env.*",           ".env.* variants (.env.local, .env.production, etc.)",
         "Variant .env files used for different environments — still contain secrets."),
        ("*.pem",            "PEM / SSL certificate private keys (*.pem)",
         "Private certificate files. Exposing these lets attackers impersonate your server."),
        ("*.key",            "Private key files (*.key)",
         "Generic private key files. Same risk as PEM files."),
        ("*.p12",            "PKCS#12 certificate bundles (*.p12)",
         "Certificate + private key bundles used for authentication."),
        ("*.pfx",            "PFX certificate bundles (*.pfx)",
         "Windows equivalent of .p12 — same risk."),
        ("__pycache__/",     "Python cache folders (__pycache__/)",
         "Compiled Python bytecode. Not useful to other people and clutters the repository."),
        ("*.pyc",            "Compiled Python files (*.pyc)",
         "Python bytecode — auto-generated, not needed in version control."),
        ("venv/",            "Python virtual environment folder (venv/)",
         "This folder can be hundreds of MB and is rebuilt from requirements.txt anyway."),
        (".venv/",           "Python virtual environment folder (.venv/)",
         "Same as venv/ — very large and automatically recreatable."),
        ("node_modules/",    "Node.js packages folder (node_modules/)",
         "Can be thousands of files. Rebuilt with 'npm install' — never needs to be on GitHub."),
        ("*.log",            "Log files (*.log)",
         "Log files grow large and often contain internal paths or error details."),
        ("*.zip",            "ZIP archives (*.zip)",
         "Large binary files that bloat your repository history."),
        ("*.sqlite",         "SQLite database files (*.sqlite)",
         "May contain real user data — databases should not be committed to GitHub."),
        ("*.db",             "Database files (*.db)",
         "Same as .sqlite — may contain sensitive data."),
        ("Thumbs.db",        "Windows thumbnail cache (Thumbs.db)",
         "A Windows internal file — not useful on GitHub."),
        (".DS_Store",        "macOS metadata files (.DS_Store)",
         "macOS folder metadata — not relevant to your project."),
        (".vs/",             "Visual Studio settings folder (.vs/)",
         "Local editor settings — not useful to share with others."),
        (".idea/",           "JetBrains IDE settings (.idea/)",
         "Local editor settings for PyCharm, WebStorm, etc."),
        ("dist/",            "Build output folder (dist/)",
         "Auto-generated files from your build process. Rebuilt any time with your build command."),
        ("build/",           "Build output folder (build/)",
         "Same as dist/ — auto-generated, not needed in source control."),
    ]

    # Large media / binary file types that can bloat a repository
    LARGE_FILE_CHECKS = [
        # Audio
        ("*.mp3",  "MP3 audio files (*.mp3)",
         "Audio files can be large and bloat repository history. Use Git LFS or an asset host instead."),
        ("*.wav",  "WAV audio files (*.wav)",
         "Uncompressed audio — often very large. Not suitable for git."),
        ("*.ogg",  "OGG audio files (*.ogg)",
         "Compressed audio that still adds to repository size over time."),
        ("*.flac", "FLAC lossless audio (*.flac)",
         "Lossless audio files are very large — not suited for git."),
        ("*.aac",  "AAC audio files (*.aac)",
         "Audio files that can bloat your repository."),
        ("*.m4a",  "M4A audio files (*.m4a)",
         "Apple audio format — same size concerns as MP3."),
        # Video
        ("*.mp4",  "MP4 video files (*.mp4)",
         "Video files are very large and will severely bloat your repository history."),
        ("*.mkv",  "MKV video files (*.mkv)",
         "Matroska video container — very large, not suited for git."),
        ("*.avi",  "AVI video files (*.avi)",
         "Older video format — often very large."),
        ("*.mov",  "MOV video files (*.mov)",
         "QuickTime video — can be extremely large."),
        ("*.wmv",  "WMV video files (*.wmv)",
         "Windows Media Video — large binary files."),
        ("*.webm", "WebM video files (*.webm)",
         "Web video format — still large for git storage."),
        # Large image / design files
        ("*.psd",  "Photoshop files (*.psd)",
         "Large design files that can bloat repository size significantly."),
        ("*.raw",  "Camera RAW image files (*.raw)",
         "Unprocessed camera images — very large, unsuitable for git."),
        # Archives
        ("*.rar",  "RAR archives (*.rar)",
         "Large binary archives — bloat repository history."),
        ("*.7z",   "7-Zip archives (*.7z)",
         "Compressed archives — same concerns as ZIP."),
        # Disk / executable images
        ("*.iso",  "Disk image files (*.iso)",
         "Disk images are extremely large (often gigabytes)."),
        ("*.exe",  "Windows executables (*.exe)",
         "Binary executables — rarely belong in source control and can be large."),
        ("*.dmg",  "macOS disk images (*.dmg)",
         "macOS installer images — very large binary files."),
    ]

    # Read existing .gitignore to avoid duplicating entries
    gitignore_path = os.path.join(target_dir, ".gitignore")
    existing_lines = set()
    if os.path.exists(gitignore_path):
        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                existing_lines = {l.strip() for l in f if l.strip() and not l.startswith("#")}
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  SECTION 1 — Sensitive / unnecessary files                          #
    # ------------------------------------------------------------------ #

    # Scan which patterns actually exist in this project
    found_patterns = []
    for pattern, label, reason in SENSITIVE_CHECKS:
        search = pattern.rstrip("/")
        exact_match = os.path.exists(os.path.join(target_dir, search))
        wildcard_match = False
        if "*" in pattern:
            wildcard_match = bool(glob.glob(os.path.join(target_dir, "**", search), recursive=True))
        if (exact_match or wildcard_match) and pattern not in existing_lines:
            found_patterns.append((pattern, label, reason))

    # Always suggest the most important ones even if not present
    always_suggest = {
        ".env", ".env.*", "*.pem", "*.key", "node_modules/", "venv/", ".venv/"
    }
    for pattern, label, reason in SENSITIVE_CHECKS:
        if pattern in always_suggest and pattern not in existing_lines:
            if not any(p == pattern for p, _, _ in found_patterns):
                found_patterns.append((pattern, label, reason))

    to_add = []

    if not found_patterns:
        print(f"{Colors.GREEN}✔ Your .gitignore looks good — no obvious sensitive files detected.{Colors.ENDC}")
    else:
        print(f"{Colors.WARNING}The following file types were found or are commonly present in projects like yours.{Colors.ENDC}")
        print(f"You will be asked about each one. It is strongly recommended to ignore most of them.\n")

        for i, (pattern, label, reason) in enumerate(found_patterns, 1):
            print(f"\n  {Colors.BOLD}[{i}/{len(found_patterns)}] {label}{Colors.ENDC}")
            print(f"      {Colors.CYAN}Why ignore it?{Colors.ENDC} {reason}")
            answer = input(f"      Add '{pattern}' to .gitignore? (Y/n): ").strip().lower()
            if answer != "n":
                to_add.append(pattern)
                print(f"      {Colors.GREEN}✔ Will be ignored.{Colors.ENDC}")
            else:
                print(f"      {Colors.WARNING}Skipped — this file type WILL be uploaded to GitHub.{Colors.ENDC}")

    # ------------------------------------------------------------------ #
    #  SECTION 2 — Large media / binary files (optional)                  #
    # ------------------------------------------------------------------ #

    print(f"\n{Colors.HEADER}--- Large Media & Binary Files ---{Colors.ENDC}")
    print(
        "Large files (audio, video, disk images) can severely bloat your repository.\n"
        f"GitHub has a {Colors.WARNING}100 MB file-size limit{Colors.ENDC} and repositories should stay well under 1 GB.\n"
    )
    show_large = input("Would you like to check for common large file types to ignore? (y/N): ").strip().lower()

    to_add_large = []
    if show_large == 'y':
        # Detect which large-file patterns are present in the project
        found_large = []
        for pattern, label, reason in LARGE_FILE_CHECKS:
            search = pattern.rstrip("/")
            wildcard_match = bool(glob.glob(os.path.join(target_dir, "**", search), recursive=True))
            exact_match = os.path.exists(os.path.join(target_dir, search))
            if (wildcard_match or exact_match) and pattern not in existing_lines:
                found_large.append((pattern, label, reason))

        # Always suggest the most common media types
        always_suggest_large = {"*.mp3", "*.mp4", "*.wav"}
        for pattern, label, reason in LARGE_FILE_CHECKS:
            if pattern in always_suggest_large and pattern not in existing_lines:
                if not any(p == pattern for p, _, _ in found_large):
                    found_large.append((pattern, label, reason))

        if not found_large:
            print(f"{Colors.GREEN}✔ No large media files detected in your project.{Colors.ENDC}")
        else:
            print(
                f"{Colors.WARNING}The following large file types were found or are commonly committed by mistake.{Colors.ENDC}\n"
            )
            for i, (pattern, label, reason) in enumerate(found_large, 1):
                print(f"\n  {Colors.BOLD}[{i}/{len(found_large)}] {label}{Colors.ENDC}")
                print(f"      {Colors.CYAN}Why ignore it?{Colors.ENDC} {reason}")
                answer = input(f"      Add '{pattern}' to .gitignore? (Y/n): ").strip().lower()
                if answer != "n":
                    to_add_large.append(pattern)
                    print(f"      {Colors.GREEN}✔ Will be ignored.{Colors.ENDC}")
                else:
                    print(f"      {Colors.WARNING}Skipped.{Colors.ENDC}")

    # ------------------------------------------------------------------ #
    #  Write all new entries to .gitignore                                #
    # ------------------------------------------------------------------ #

    if not to_add and not to_add_large:
        print(f"\n{Colors.CYAN}No changes made to .gitignore.{Colors.ENDC}")
        return

    try:
        with open(gitignore_path, "a", encoding="utf-8") as f:
            if to_add:
                f.write("\n# --- Added by GitHub Auto-Pilot ---\n")
                for p in to_add:
                    f.write(p + "\n")
            if to_add_large:
                f.write("\n# --- Large Media & Binary Files (GitHub Auto-Pilot) ---\n")
                for p in to_add_large:
                    f.write(p + "\n")
        total = len(to_add) + len(to_add_large)
        print(f"\n{Colors.GREEN}✔ .gitignore updated successfully with {total} new rule(s).{Colors.ENDC}")
        print(f"   File saved at: {gitignore_path}")
    except Exception as e:
        print(f"{Colors.FAIL}Could not write .gitignore: {e}{Colors.ENDC}")


def purge_file_from_history(target_dir):
    """
    Permanently removes a file from ALL git history (rewrites commits).
    Critical for cases where a sensitive file was accidentally committed.

    IMPORTANT: This rewrites history. Anyone who has already cloned the repo
    will need to re-clone it or run 'git fetch --all && git reset --hard origin/main'.
    """
    print_header("🗑️  PURGE FILE FROM GIT HISTORY")
    print(
        f"{Colors.WARNING}⚠  IMPORTANT — PLEASE READ CAREFULLY:{Colors.ENDC}\n"
        "\nWhen you commit a file to git, it is saved FOREVER in git's history,\n"
        "even after you delete it. This means:\n"
        "  • Anyone who clones your repository can see the file's old content.\n"
        "  • GitHub's own servers store the history indefinitely.\n"
        "\nThis tool will REWRITE your entire git history to completely erase\n"
        "the file from every past commit. After this:\n"
        "  • The file will no longer exist in any commit, past or present.\n"
        "  • Anyone else who has cloned the repo must re-clone it.\n"
        "  • You must force-push to GitHub (this tool will do that for you).\n"
        f"\n{Colors.FAIL}If the file contained API keys or passwords, you MUST also rotate\n"
        f"(change/regenerate) those credentials immediately — GitHub's servers\n"
        f"may have already indexed the content.{Colors.ENDC}\n"
    )

    file_to_purge = input(
        f"Enter the path of the file to purge (relative to project root, e.g. .env): {Colors.GREEN}"
    ).strip()
    print(Colors.ENDC, end="")

    if not file_to_purge:
        print(f"{Colors.FAIL}No file specified. Aborting.{Colors.ENDC}")
        return

    confirm = input(
        f"\n{Colors.WARNING}Are you SURE you want to permanently erase '{file_to_purge}' from ALL history?\n"
        f"This cannot be undone (type YES to confirm): {Colors.ENDC}"
    ).strip()
    if confirm != "YES":
        print(f"{Colors.CYAN}Aborted — no changes made.{Colors.ENDC}")
        return

    # Method 1: git filter-repo (modern, fast, recommended)
    ok_filter_repo, _ = run_cmd("git filter-repo --version", cwd=target_dir, hide_output=True)
    # Method 2: git filter-branch (older, always available)
    ok_filter_branch, _ = run_cmd("git filter-branch --help", cwd=target_dir, hide_output=True)

    purge_ok = False

    if ok_filter_repo:
        print(f"{Colors.CYAN}Using git filter-repo to purge '{file_to_purge}' from history...{Colors.ENDC}")
        purge_ok, out = run_cmd(
            ["git", "filter-repo", "--path", file_to_purge, "--invert-paths", "--force"],
            cwd=target_dir
        )
    else:
        print(f"{Colors.CYAN}Using git filter-branch to purge '{file_to_purge}' from history...{Colors.ENDC}")
        print(f"{Colors.WARNING}(This may take a while on large repositories){Colors.ENDC}")
        # Use a shell string here since filter-branch requires the shell for --index-filter
        safe_file = file_to_purge.replace("'", "\\'")
        purge_ok, out = run_cmd(
            f"git filter-branch --force --index-filter "
            f"\"git rm --cached --ignore-unmatch '{safe_file}'\" "
            f"--prune-empty --tag-name-filter cat -- --all",
            cwd=target_dir
        )

    if not purge_ok:
        print(f"{Colors.FAIL}✖ History rewrite failed. See above for details.{Colors.ENDC}")
        print(
            f"{Colors.WARNING}Tip: If git filter-repo is not installed, run:\n"
            f"  pip install git-filter-repo{Colors.ENDC}"
        )
        return

    # Add the file to .gitignore to prevent it from being committed again
    gitignore_path = os.path.join(target_dir, ".gitignore")
    existing = ""
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            existing = f.read()

    if file_to_purge not in existing:
        with open(gitignore_path, "a", encoding="utf-8") as f:
            f.write(f"\n# Purged from history — never commit again\n{file_to_purge}\n")
        print(f"{Colors.GREEN}✔ Added '{file_to_purge}' to .gitignore so it can never be committed again.{Colors.ENDC}")
        run_cmd("git add .gitignore", cwd=target_dir)
        run_cmd(["git", "commit", "-m", f"chore: add {file_to_purge} to gitignore after history purge"], cwd=target_dir)

    # Force push to GitHub to overwrite remote history
    print(f"\n{Colors.WARNING}Force-pushing rewritten history to GitHub...{Colors.ENDC}")
    _, current_branch = run_cmd("git branch --show-current", cwd=target_dir)
    push_ok, _ = run_cmd(["git", "push", "origin", current_branch, "--force"], cwd=target_dir)

    if push_ok:
        print(f"\n{Colors.GREEN}{Colors.BOLD}✔ File successfully purged from all history!{Colors.ENDC}")
        print(
            f"\n{Colors.CYAN}Next steps you MUST take:{Colors.ENDC}\n"
            f"  1. {Colors.WARNING}Rotate any secrets that were in the file{Colors.ENDC} — change passwords,\n"
            f"     regenerate API keys, revoke tokens. Assume they are compromised.\n"
            f"  2. If other people have cloned this repo, ask them to re-clone it\n"
            f"     (or run: git fetch --all && git reset --hard origin/{current_branch}).\n"
            f"  3. Contact GitHub Support (support.github.com) to clear their caches\n"
            f"     if the repository was ever public.\n"
        )
    else:
        print(f"{Colors.FAIL}✖ Force push failed. You may need to manually run:{Colors.ENDC}")
        print(f"  git push origin {current_branch} --force")


def explain_pull_requests():
    """A friendly explanation of what Pull Requests are and why they are used."""
    print(f"\n{Colors.HEADER}--- What is a 'Pull Request' (PR)? ---{Colors.ENDC}")
    print(
        "Imagine you and a friend are both working on the same website.\n"
        "If you both edited the same file at the same time, things could get messy!\n"
        "\nA Pull Request solves this by working in stages:\n"
        "  1. You make your changes on your OWN separate copy (called a 'branch').\n"
        "  2. When you are happy with your changes, you open a Pull Request.\n"
        "     This is like saying: 'Hey team, I made some changes. Can you look\n"
        "     them over before we add them to the main website?'\n"
        "  3. Your team (or just you) reviews the changes, leaves comments, and\n"
        "     approves them.\n"
        "  4. Once approved, the changes are 'merged' (combined) into the main branch.\n"
        "\nEven if you work alone, Pull Requests are great because:\n"
        "  • They give you a clean history of what changed and WHY.\n"
        "  • Cloudflare Pages will automatically build a PREVIEW of your PR branch,\n"
        "    so you can see the live result before publishing to the main site.\n"
        "  • You can link issues and keep everything organised.\n"
    )


def create_pull_request(token, target_dir):
    """
    Creates a new branch from the current state, pushes it, and opens a
    Pull Request against the main/master branch on GitHub.
    """
    _, current_branch = run_cmd("git branch --show-current", cwd=target_dir)

    # Get remote URL to extract owner/repo
    success, remote_url = run_cmd(["git", "remote", "get-url", "origin"], cwd=target_dir)
    if not success or not remote_url:
        print(f"{Colors.FAIL}✖ This repository does not have a GitHub remote configured.{Colors.ENDC}")
        print("  Please run Option 1 (Standard Update) first to push your code to GitHub.")
        return

    # Parse owner and repo from HTTPS or SSH URL
    owner, repo = None, None
    if "github.com" in remote_url:
        if remote_url.startswith("http"):
            remote_url_stripped = remote_url.removesuffix(".git").rstrip("/")
            parts = remote_url_stripped.split("/")
            owner, repo = parts[-2], parts[-1]
        elif remote_url.startswith("git@"):
            path_part = remote_url.split(":")[-1].removesuffix(".git")
            parts = path_part.split("/")
            owner, repo = parts[0], parts[1]

    if not owner or not repo:
        print(f"{Colors.FAIL}✖ Could not determine GitHub owner/repo from remote URL: {remote_url}{Colors.ENDC}")
        return

    explain_pull_requests()

    print(f"\n{Colors.BOLD}Let's create a Pull Request for '{owner}/{repo}'.{Colors.ENDC}")
    print(f"You are currently on branch: {Colors.CYAN}{current_branch}{Colors.ENDC}\n")

    # Step 1: Create (or reuse) a feature branch
    new_branch = input(
        f"Enter a name for your new feature branch (e.g. 'add-contact-page'): {Colors.GREEN}"
    ).strip().replace(" ", "-")
    print(Colors.ENDC, end="")

    if not new_branch:
        print(f"{Colors.FAIL}Branch name cannot be empty.{Colors.ENDC}")
        return

    # Check if branch already exists locally
    _, branches_out = run_cmd("git branch", cwd=target_dir, hide_output=True)
    branch_exists = new_branch in (b.strip().lstrip("* ") for b in branches_out.splitlines())

    if branch_exists:
        print(f"{Colors.CYAN}Branch '{new_branch}' already exists. Switching to it...{Colors.ENDC}")
        run_cmd(["git", "checkout", new_branch], cwd=target_dir)
    else:
        print(f"{Colors.CYAN}Creating new branch '{new_branch}' from '{current_branch}'...{Colors.ENDC}")
        success, err = run_cmd(["git", "checkout", "-b", new_branch], cwd=target_dir)
        if not success:
            print(f"{Colors.FAIL}✖ Could not create branch '{new_branch}'.{Colors.ENDC}")
            return

    # Step 2: Stage and commit any pending changes
    _, status_out = run_cmd("git status --porcelain", cwd=target_dir, hide_output=True)
    if status_out.strip():
        print(f"\n{Colors.CYAN}You have uncommitted changes. Committing them to '{new_branch}'...{Colors.ENDC}")
        safe_git_add(target_dir)
        commit_msg = input(
            f"Commit message for this branch (e.g. 'Add contact page'): {Colors.GREEN}"
        ) or f"Changes for PR: {new_branch}"
        print(Colors.ENDC, end="")
        run_cmd(["git", "commit", "-m", commit_msg], cwd=target_dir)
    else:
        print(f"{Colors.CYAN}No uncommitted changes detected on this branch.{Colors.ENDC}")

    # Step 3: Push the branch to GitHub
    print(f"{Colors.CYAN}Pushing branch '{new_branch}' to GitHub...{Colors.ENDC}")
    push_ok, _ = run_cmd(["git", "push", "-u", "origin", new_branch], cwd=target_dir)
    if not push_ok:
        print(f"{Colors.FAIL}✖ Push failed. Check your internet connection and GitHub permissions.{Colors.ENDC}")
        return

    # Step 4: Determine base branch (main or master)
    base_branch = current_branch if current_branch in ("main", "master") else "main"
    base_override = input(
        f"Which branch should the PR merge INTO? [{base_branch}]: {Colors.GREEN}"
    ).strip()
    print(Colors.ENDC, end="")
    if base_override:
        base_branch = base_override

    # Step 5: Create the PR via GitHub API
    pr_title = input(
        f"PR title (short summary, e.g. 'Add contact page'): {Colors.GREEN}"
    ).strip() or f"Changes from {new_branch}"
    print(Colors.ENDC, end="")

    pr_body = input(
        f"PR description (optional — what does this change do?): {Colors.GREEN}"
    ).strip()
    print(Colors.ENDC, end="")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    data = {
        "title": pr_title,
        "head":  new_branch,
        "base":  base_branch,
        "body":  pr_body or f"Pull request created via GitHub Auto-Pilot from branch `{new_branch}`.",
    }
    res = requests.post(
        f"https://api.github.com/repos/{owner}/{repo}/pulls",
        headers=headers,
        json=data
    )

    if res.status_code == 201:
        pr_url = res.json().get("html_url", "")
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 Pull Request created successfully!{Colors.ENDC}")
        print(f"   View it here: {Colors.CYAN}{pr_url}{Colors.ENDC}")
        print(
            f"\n{Colors.CYAN}What happens next?{Colors.ENDC}\n"
            "  • If you use Cloudflare Pages, a preview deployment of your branch\n"
            "    will start automatically — check your Cloudflare dashboard.\n"
            "  • When you are happy with the changes, click 'Merge Pull Request'\n"
            "    on GitHub to publish them to your main branch.\n"
        )
    elif res.status_code == 422:
        err_msg = res.json().get("message", "Unknown error")
        errors  = res.json().get("errors", [])
        if errors:
            err_msg += " — " + "; ".join(str(e) for e in errors)
        print(f"{Colors.FAIL}✖ GitHub rejected the Pull Request: {err_msg}{Colors.ENDC}")
        if "no commits between" in err_msg.lower():
            print(
                f"{Colors.WARNING}  This means the branch '{new_branch}' has no new commits\n"
                f"  compared to '{base_branch}'. Make some changes and commit them first.{Colors.ENDC}"
            )
    else:
        print(f"{Colors.FAIL}✖ Failed to create PR (HTTP {res.status_code}): {res.text}{Colors.ENDC}")


def explain_worktrees():
    """A user-friendly primer on what Git Worktrees are and why they are useful."""
    print(f"\n{Colors.HEADER}--- What is a 'Safe Playground' (Git Worktree)? ---{Colors.ENDC}")
    print("Imagine you have a perfectly working website, but you want to try adding a crazy new feature.")
    print("Normally, if you edit your files and it breaks, it's annoying to undo everything.")
    print("\nA 'Worktree' fixes this by magically creating a second, physical copy of your folder on your computer (git worktree add).")
    print("It links to the exact same cloud project (repository), but it acts like a parallel universe (checked out to a different branch).")
    print("You can open this new folder, completely break everything inside it, and your original folder remains perfectly untouched.\n")

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

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Goodbye! Nothing was changed.{Colors.ENDC}")
        sys.exit(0)