import json
import os
import re
import sys
import shutil
from datetime import datetime, timezone

from utils import *

def try_make_mirror_git_repo(
        origin_repo_url: str, mirror_repo_url: str,
        local_workspace: str) -> bool:
    try:
        cwd = os.getcwd()

        Logger.info(f"Try run make mirror git repo, origin repo url: {origin_repo_url}, mirror repo url: {mirror_repo_url}, local workspace: {local_workspace}.")
        origin_remote_name = "origin"
        mirror_remote_name = "mirror"

        # Stage 1: Init local workspace
        Logger.info("Start Stage 1: Init local workspace.")

        match = re.match(r'.+/([^/]+)\.git$', origin_repo_url)
        if match:
            repo_name = match.group(1)
        else:
            Logger.error(f"Failed to match repo name in origin_repo_url: {origin_repo_url}.")
            return False
        
        git_repo_path = os.path.join(local_workspace, f"{repo_name}")
        if not os.path.exists(local_workspace):
            os.makedirs(local_workspace)

        if os.path.exists(git_repo_path):
            make_files_writable(git_repo_path)
            shutil.rmtree(git_repo_path)
        os.makedirs(git_repo_path)
        Logger.info(f"Target working folder: {git_repo_path}.")

        Logger.info("End Stage 1: Init local workspace.")

        # Stage 2: Fetch all tags and branch from origin repo
        Logger.info("Start Stage 2: Fetch all branch and tags from origin repo.")

        # git clone -o origin --tags git_repo_path
        git_clone_from_origin_cmd = [
            "git",
            "clone",
            "-o",
            origin_remote_name,
            "--tags",
            origin_repo_url,
            git_repo_path
        ]
        returncode, _, _ = run_cmd(git_clone_from_origin_cmd)
        if returncode != 0:
            Logger.error("Failed to clone from origin repo")
            return False
        
        # cd workspace
        os.chdir(git_repo_path)
        
        # git branch --show-current
        git_get_default_branch_cmd = [
            "git",
            "branch",
            "--show-current"
        ]
        returncode, default_branch_name, _ = run_cmd(git_get_default_branch_cmd)
        if returncode != 0:
            Logger.error("Failed to get origin default branch name.")
            return False
        default_branch_name = default_branch_name.strip()
        if not default_branch_name:
            Logger.error("Default branch name is empty.")
            return False
        
        # git branch -r --list origin
        git_branch_remote_cmd = [
            "git",
            "branch",
            "-r",
            "--list",
            f"{origin_remote_name}/*"
        ]
        returncode, origin_remote_branch_str, _ = run_cmd(git_branch_remote_cmd)
        if returncode != 0:
            Logger.error("Failed to fetch origin remote branches.")
            return False

        remote_branches_withfullref = [branch.strip()
            for branch in origin_remote_branch_str.split("\n")
                if branch.strip() and not branch.strip().startswith(f"{origin_remote_name}/HEAD ->")]
        
        remote_branches = []
        for branch in remote_branches_withfullref:
            # Eg. for string "github/main", "main" will be captured
            match = re.match(r'^[^/]+/(.+)$', branch)
            if match:
                branch_name = match.group(1)
                remote_branches.append(branch_name)
            else:
                Logger.error(f"Failed to parse remote branch name: {branch}.")
                return False
        
        no_default_remote_branches = [b
            for b in remote_branches
                if b != default_branch_name]
        Logger.info(no_default_remote_branches)

        # Create branches for all non-default remote branches
        for b in no_default_remote_branches:
            git_branch_track_cmd = [
                "git",
                "branch",
                "-f",
                f"{b}",
                f"{origin_remote_name}/{b}"
            ]
            returncode, _, _ = run_cmd(git_branch_track_cmd)
            if returncode != 0:
                Logger.error(f"Failed to create branch {b} from remote branch {origin_remote_name}/{b}.")
                return False

        Logger.info("End Stage 2: Fetch all branch and tags from origin repo.")
        
        # Stage 3: Push all branch to empty mirror repo
        Logger.info("Start Stage 3: Push all branch to empty mirror repo.")

        # git remote add mirror mirror_repo-url
        git_add_remote_cmd = [
            "git",
            "remote",
            "add",
            mirror_remote_name,
            mirror_repo_url
        ]
        returncode, _, _ = run_cmd(git_add_remote_cmd)
        if returncode != 0:
            Logger.error("Failed to add mirror repo url as remote.")
            return False
        
        # git push mirror --all
        git_push_all_to_mirror_cmd = [
            "git",
            "push",
            mirror_remote_name,
            "--all"
        ]
        returncode, _, _ = run_cmd(git_push_all_to_mirror_cmd)
        if returncode != 0:
            Logger.error("Failed to push all branch to mirror.")
            return False

        # git push mirror --tags
        git_push_tags_to_mirror_cmd = [
            "git",
            "push",
            mirror_remote_name,
            "--tags"
        ]
        returncode, _, _ = run_cmd(git_push_tags_to_mirror_cmd)
        if returncode != 0:
            Logger.error("Failed to push tags to mirror.")
            return False
        
        Logger.info("End Stage 3: Push all branch to empty mirror repo.")

        # Stage 4: Write log
        Logger.info("Start Stage 4: Write log.")
        dt_utc = datetime.now(timezone.utc).isoformat()
        Logger.info(f"Time: {dt_utc}")

        # get local branches data
        git_get_branch_data_cmd = [
            "git",
            "show-ref",
            "--branches"
        ]
        returncode, branches_str, _ = run_cmd(git_get_branch_data_cmd)
        if returncode != 0:
            Logger.error("Failed to get branches data.")
            return False

        branch_data_list = {}
        for line in branches_str.splitlines():
            if line.strip():
                hash_part, ref_part = line.split()
                branch_name = ref_part.split('/')[-1]
                branch_data_list[branch_name] = hash_part

        # get local tags data
        git_get_tags_data_cmd = [
            "git",
            "show-ref",
            "--tags"
        ]
        returncode, tags_str, stderr = run_cmd(git_get_tags_data_cmd)
        if returncode != 0 and len(stderr) != 0:
            Logger.error("Failed to get tags data.")
            return False

        tag_data_list = {}
        for line in tags_str.splitlines():
            if line.strip():
                hash_part, ref_part = line.split()
                tag_name = ref_part.split('/')[-1]
                tag_data_list[tag_name] = hash_part

        # Log
        log_data = {
            "time": f"{dt_utc}",
            "origin repo url": origin_repo_url,
            "mirror repo url": mirror_repo_url,
            "local repo path": git_repo_path,
            "branches": branch_data_list,
            "tags": tag_data_list
        }
        Logger.info(log_data)

        Logger.info("End Stage 4: Write log.")

        Logger.info("Finished to make mirror git repo.")
        return True

    except Exception as e:
        Logger.error(f"Error: {e}")
        return False
    finally:
        os.chdir(cwd)

# return code:
#      0 : successed.
#     -1 : main function exception occured.
#     -2 : try multiple times, still failed.
def main() -> int:
    try:
        Logger.init("make_mirror_git_repo_log")

        # Configuration Parsing
        Logger.info("Configuration Parsing.")

        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_json_path = os.path.join(current_dir, "make-mirror-git-repo-config.json")
        with open(config_json_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        local_workspace = os.path.normpath(data["local-workspace"])
        mirror_needed_repo_pairs = data["mirror-needed-repo-pairs"]

        mirror_needed_repo_pair_list = []
        for repo_pair in mirror_needed_repo_pairs:
            origin_repo_url = repo_pair["origin-repo-ssh-url"]
            mirror_repo_url = repo_pair["mirror-empty-repo-ssh-url"]
            mirror_needed_repo_pair_list.append((origin_repo_url, mirror_repo_url))

        Logger.info("End of Configuration Parsing.")

        git_config_global_coreautocrlf_false_cmd = [
            "git",
            "config",
            "--global",
            "core.autocrlf",
            "false"
        ]
        returncode, _, _ = run_cmd(git_config_global_coreautocrlf_false_cmd)
        if returncode != 0:
            Logger.error("Failed to close git autocrlf.")
            return -3

        returncode = 0
        for origin_repo_url, mirror_repo_url in mirror_needed_repo_pair_list:
            if not try_make_mirror_git_repo(origin_repo_url, mirror_repo_url, local_workspace):
                Logger.warning(f"Failed to make mirror from {origin_repo_url} to {mirror_repo_url}.")
                returncode = -2

        return returncode

    except Exception as e:
        Logger.error(f"Error: {e}")
        return -1


if __name__ == "__main__":
    returncode = main()
    sys.exit(returncode)