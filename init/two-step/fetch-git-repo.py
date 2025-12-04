import json
import os
import re
import sys
import shutil
import time
from datetime import datetime, timezone

from utils import *

def try_fetch_git_repo(
        origin_repo_url: str,
        local_workspace: str) -> bool:
    try:
        cwd = os.getcwd()

        Logger.info(f"Try fetch git repo, origin repo url: {origin_repo_url}, local workspace: {local_workspace}.")
        origin_remote_name = "origin"

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
        Logger.info("Start Stage 2: Clone all branch and tags from origin repo.")

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

        Logger.info("End Stage 2: Clone all branch and tags from origin repo.")
        
        # Stage 3: Write log
        Logger.info("Start Stage 3: Write log.")
        dt_utc = datetime.now(timezone.utc).isoformat()
        Logger.info(f"Time: {dt_utc}")

        # get local branches data
        git_get_branch_data_cmd = [
            "git",
            "show-ref",
            "--branches"
        ]
        returncode, branches_str, stderr = run_cmd(git_get_branch_data_cmd)
        if returncode != 0:
            Logger.error(f"Failed to get branches data. Error message: {stderr}.")
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
            Logger.error(f"Failed to get tags data. Error message: {stderr}.")
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
            "local repo path": git_repo_path,
            "branches": branch_data_list,
            "tags": tag_data_list
        }
        Logger.info(log_data)

        Logger.info("End Stage 3: Write log.")

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
#     -2 : failed to extract hostname from origin_repo_url.
#     -3 : failed to configure SSH host.
#     -4 : try multiple times, still failed.
def main() -> int:
    try:
        Logger.init(".log")

        # Configuration Parsing
        Logger.info("Configuration Parsing.")

        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_json_path = os.path.join(current_dir, "fetch-git-repo-config.json")
        with open(config_json_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        max_retry_times = data["max-retry-times"]
        retry_cooldown_sec = data["retry-cooldown-sec"]
        local_workspace = os.path.normpath(data["local-workspace"])
        fetch_needed_repos = data["fetch-needed-repos"]

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
            return -5

        returncode = 0
        for origin_repo_url in fetch_needed_repos:
            # 从 origin_repo_url 中提取主机名并配置 SSH
            hostname = extract_hostname_from_git_url(origin_repo_url)
            if hostname:
                if not configure_ssh_host(hostname):
                    Logger.warning(f"Failed to configure SSH host for {hostname}")
                    returncode = -2
                    continue
            else:
                Logger.warning(f"Failed to extract hostname from origin_repo_url: {origin_repo_url}")
                returncode = -3
                continue

            failed_times = 0
            while failed_times < max_retry_times:
                if try_fetch_git_repo(origin_repo_url, local_workspace):
                    break
                failed_times += 1
                time.sleep(retry_cooldown_sec)
            if failed_times >= max_retry_times:
                Logger.error(f"Failed to fetch repo from {origin_repo_url} after try {failed_times} times.")
                returncode = -4

        return returncode

    except Exception as e:
        Logger.error(f"Error: {e}")
        return -1


if __name__ == "__main__":
    returncode = main()
    sys.exit(returncode)