import os
import sys
import subprocess
import json
import stat
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

def get_github_auth():
    """Logs the user into GitHub securely."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    token = None
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, 'r') as f:
                token = json.load(f).get("token")
        except Exception:
            pass

    # Standardize Modern GitHub API Headers
    def get_headers(pat):
        return {
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }

    if token:
        # Check if the saved token still works
        res = requests.get("https://api.github.com/user", headers=get_headers(token))
        if res.status_code == 200:
            user = res.json().get('login')
            print(f"{Colors.GREEN}✔ Logged into GitHub securely as: {Colors.BOLD}{user}{Colors.ENDC}")
            return token, user

    print_header("🔑 GITHUB LOGIN")
    print("To save your files to the internet, we need a digital key (Personal Access Token / PAT) from your GitHub account.")
    print("You only have to do this once!\n")
    print(f"1. Hold CTRL (or CMD on Mac) and click this link: {Colors.CYAN}https://github.com/settings/tokens/new?scopes=repo{Colors.ENDC}")
    print("2. Log into GitHub if it asks you to.")
    print("3. In the 'Note' box, type something like 'My Setup Tool'.")
    print("4. Scroll all the way to the very bottom and click the green 'Generate token' button.")
    print("5. Copy the long string of letters and numbers it gives you.\n")
    
    while True:
        token = input(f"{Colors.BOLD}Paste your digital key (PAT) here and press Enter: {Colors.ENDC}").strip()
        print(f"{Colors.CYAN}Checking key...{Colors.ENDC}")
        
        res = requests.get("https://api.github.com/user", headers=get_headers(token))
        
        if res.status_code == 200:
            user = res.json().get('login')
            print(f"{Colors.GREEN}✔ Success! Welcome {user}. Saving your key securely so you don't have to do this again.{Colors.ENDC}")
            
            # Remove hidden attribute on Windows before overwriting to prevent PermissionError
            if TOKEN_FILE.exists():
                try:
                    if os.name == 'nt':
                        subprocess.run(["attrib", "-H", str(TOKEN_FILE)], capture_output=True)
                    TOKEN_FILE.chmod(stat.S_IWRITE | stat.S_IREAD)
                except Exception:
                    pass

            with open(TOKEN_FILE, 'w') as f:
                json.dump({"token": token}, f)
            # Restrict file permissions to owner only
            try:
                if os.name == 'nt':
                    subprocess.run(["attrib", "+H", str(TOKEN_FILE)], capture_output=True)
                else:
                    TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
            except Exception:
                pass
            return token, user
        else:
            print(f"{Colors.FAIL}✖ That key didn't work. Please make sure you copied the whole thing and try again.{Colors.ENDC}")

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
    
    print(f"{Colors.CYAN}Preparing your files for their first journey to the cloud (git init & git add)...{Colors.ENDC}")
    run_cmd("git init", cwd=target_dir) # Turns the folder into a Git folder
    run_cmd("git add .", cwd=target_dir) # Selects all files
    
    print("\nEvery time you save files to GitHub, you attach a little 'Save Note' (commit message) so you remember what you changed.")
    commit_msg = input(f"Type a short note (commit message, e.g. 'First upload of my website'): {Colors.GREEN}") or "First upload"
    print(Colors.ENDC, end="")
    
    run_cmd(["git", "commit", "-m", commit_msg], cwd=target_dir)
    run_cmd("git branch -M main", cwd=target_dir)
    run_cmd(["git", "remote", "add", "origin", repo_url], cwd=target_dir)
    
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
    
    print(f"\n1. {Colors.GREEN}Standard Update (Commit & Push):{Colors.ENDC} Upload my newest changes to GitHub.")
    print(f"2. {Colors.BLUE}Duplicate/Copy (Change Remote):{Colors.ENDC} Create a brand new separate copy of this project on GitHub.")
    print(f"3. {Colors.WARNING}Safe Playground (Git Worktree):{Colors.ENDC} Create a 'Git Worktree' (A safe, parallel folder for experimenting).")
    print(f"4. {Colors.CYAN}Skip (Do Nothing):{Colors.ENDC} Leave the repository exactly as it is.")
    
    choice = input(f"\nSelect an option (1-4): {Colors.GREEN}")
    print(Colors.ENDC, end="")
    
    if choice == '1':
        print("\nYou are about to upload your newest changes (git add & commit).")
        run_cmd("git add .", cwd=target_dir)
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
        print("\nWe are going to take your files and upload them as a brand new project (changing git remote).")
        repo_name = input(f"What do you want to call the NEW project (repository)? (No spaces): {Colors.GREEN}").strip().replace(" ", "-")
        print(Colors.ENDC, end="")
        is_private = input("Should this new project (repository) be Private? (Y/n): ").strip().lower() != 'n'
        
        repo_url = create_remote_repo(token, repo_name, is_private)
        
        run_cmd("git remote remove origin", cwd=target_dir, hide_output=True) # Disconnect from old
        run_cmd(["git", "remote", "add", "origin", repo_url], cwd=target_dir) # Connect to new
        run_cmd("git add .", cwd=target_dir)
        run_cmd(["git", "commit", "-m", "Copied to a new project"], cwd=target_dir)
        run_cmd("git branch -M main", cwd=target_dir)
        
        print(f"{Colors.CYAN}Uploading to the new cloud project (git push to new remote)...{Colors.ENDC}")
        run_cmd("git push -u origin main", cwd=target_dir)
        print(f"{Colors.GREEN}🎉 Success! You now have a fresh copy online.{Colors.ENDC}")
        
    elif choice == '3':
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
            
    elif choice == '4':
        print(f"{Colors.CYAN}Skipping GitHub update. Your repository remains unchanged.{Colors.ENDC}")
        return

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
    token, user = get_github_auth()
    
    # Foolproof Directory Selection
    current_folder = os.getcwd()
    print(f"\nYou are currently inside this folder on your computer:")
    print(f"{Colors.CYAN}{current_folder}{Colors.ENDC}\n")
    
    is_correct = input("Is this the folder you want to save to GitHub (initialize repository)? (Y/n): ").strip().lower()
    
    if is_correct == 'n':
        print(f"\n{Colors.WARNING}Ah, okay! Here is how to fix that:{Colors.ENDC}")
        print("1. Move this python script file into the folder you actually want to save (commit).")
        print("2. Run the script again from inside that folder.")
        sys.exit(0)
    
    # Check if the folder already has a hidden ".git" tracking folder inside it
    is_git_repo, _ = run_cmd("git rev-parse --is-inside-work-tree", cwd=current_folder, hide_output=True)
    
    if is_git_repo:
        handle_existing_project(token, current_folder)
    else:
        handle_new_project(token, current_folder)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Goodbye! Nothing was changed.{Colors.ENDC}")
        sys.exit(0)