import json
import os
import sys
from datetime import datetime, timezone

from utils import *

def try_push_git_repo(
        local_repo_path: str,
        remote_repo_url: str) -> bool:
    try:
        cwd = os.getcwd()

        Logger.info(f"Try push repo from local repo: {local_repo_path}, remote repo url: {remote_repo_url}.")
        remote_name = "mirror"
        
        # cd workspace
        os.chdir(local_repo_path)
        
        # Stage 1: Push all branch to remote repo
        Logger.info("Start Stage 1: Push all branch to remote repo.")

        # git remote add mirror mirror_repo-url
        git_add_remote_cmd = [
            "git",
            "remote",
            "add",
            remote_name,
            remote_repo_url
        ]
        returncode, _, _ = run_cmd(git_add_remote_cmd)
        if returncode != 0:
            Logger.error("Failed to add remote repo url as remote.")
            return False
        
        # git push mirror --all
        git_push_all_to_mirror_cmd = [
            "git",
            "push",
            remote_name,
            "--all"
        ]
        returncode, _, _ = run_cmd(git_push_all_to_mirror_cmd)
        if returncode != 0:
            Logger.error("Failed to push all branch to remote.")
            return False

        # git push mirror --tags
        git_push_tags_to_mirror_cmd = [
            "git",
            "push",
            remote_name,
            "--tags"
        ]
        returncode, _, _ = run_cmd(git_push_tags_to_mirror_cmd)
        if returncode != 0:
            Logger.error("Failed to push tags to remote.")
            return False
        
        Logger.info("End Stage 1: Push all branch to remote repo.")

        # Stage 2: Write log
        Logger.info("Start Stage 2: Write log.")
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
            "local repo path": local_repo_path,
            "remote repo url": remote_repo_url,
            "branches": branch_data_list,
            "tags": tag_data_list
        }
        Logger.info(log_data)

        Logger.info("End Stage 2: Write log.")

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
        Logger.init(".log")

        # Configuration Parsing
        Logger.info("Configuration Parsing.")

        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_json_path = os.path.join(current_dir, "push-git-repo-config.json")
        with open(config_json_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        push_needed_repos = data["push-needed-repos"]

        push_needed_repo_pair_list = []
        for repo_pair in push_needed_repos:
            local_repo_path = os.path.normpath(repo_pair["local-repo-path"])
            if not os.path.exists(local_repo_path) :
                Logger.error(f"The given local git path {local_repo_path} does not exist.")
                return -2
            remote_repo_ssh_url = repo_pair["remote-repo-ssh-url"]
            push_needed_repo_pair_list.append((local_repo_path, remote_repo_ssh_url))

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
            return -6

        returncode = 0
        for local_repo_path, remote_repo_ssh_url in push_needed_repo_pair_list:
            hostname = extract_hostname_from_git_url(remote_repo_ssh_url)
            if hostname:
                if not configure_ssh_host(hostname):
                    Logger.warning(f"Failed to configure SSH host for {hostname}")
                    returncode = -3
                    continue
            else:
                Logger.warning(f"Failed to extract hostname from remote_repo_ssh_url: {remote_repo_ssh_url}")
                returncode = -4
                continue

            if not try_push_git_repo(local_repo_path, remote_repo_ssh_url):
                Logger.error(f"Failed to push repo from local path {local_repo_path} to {remote_repo_ssh_url}.")
                returncode = -5

        return returncode

    except Exception as e:
        Logger.error(f"Error: {e}")
        return -1


if __name__ == "__main__":
    returncode = main()
    sys.exit(returncode)