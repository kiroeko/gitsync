import json
import os
import re
import sys
import shutil
from typing import TypedDict

from utils import *


class BranchChanges(TypedDict):
    originAdded: list[str]
    originUpdated: list[str]


def get_origin_branch_changes(
        origin_branch_dict: dict[str, str],
        mirror_branch_dict: dict[str, str],
        changed_branch_accept_rules: list[str]
    ) -> BranchChanges:
    """
    Compare branches between origin and mirror repos.
    
    Args:
        origin_branch_dict: Dict of {branch_name: commit_hash} for origin repo
        mirror_branch_dict: Dict of {branch_name: commit_hash} for mirror repo
        changed_branch_accept_rules: List of regex patterns to filter branches
    
    Returns:
        BranchChanges with originAdded (new branches) and originUpdated (branches with different commits)
    """
    branch_added_list = []
    branch_updated_list = []

    for branch_name, origin_commit in origin_branch_dict.items():
        matched = False
        for reg in changed_branch_accept_rules:
            match = re.match(reg, branch_name)
            if match:
                matched = True
                break

        if not matched:
            continue

        if branch_name in mirror_branch_dict:
            # Only add to updated list if commits are different
            mirror_commit = mirror_branch_dict[branch_name]
            if origin_commit != mirror_commit:
                branch_updated_list.append(branch_name)
                Logger.info(f"Branch '{branch_name}' needs update: origin={origin_commit[:8]}, mirror={mirror_commit[:8]}")
            else:
                Logger.info(f"Branch '{branch_name}' is already up-to-date: commit={origin_commit[:8]}")
        else:
            branch_added_list.append(branch_name)
    
    return {
        "originAdded": branch_added_list,
        "originUpdated": branch_updated_list,
    }


def try_sync_origin_updates_into_mirror(
        origin_repo_url: str, mirror_repo_url: str,
        local_workspace: str,
        changed_branch_accept_rules: list[str]
    ) -> int:
    try:
        hostname = extract_hostname_from_git_url(origin_repo_url)
        if hostname:
            if not configure_ssh_host(hostname):
                Logger.error(f"Failed to configure SSH host for {hostname}")
                return -2
        else:
            Logger.warning(f"Failed to extract hostname from remote_repo_ssh_url: {origin_repo_url}")
            return -3

        cwd = os.getcwd()

        Logger.info(f"Run try sync origin updates into mirror, origin is {origin_repo_url}, mirror is {mirror_repo_url}.")
        origin_remote_name = "origin"
        mirror_remote_name = "mirror"

        # Stage 1: Init local workspace
        Logger.info("Start Stage 1: Init local workspace")

        if os.path.exists(local_workspace):
            make_files_writable(local_workspace)
            shutil.rmtree(local_workspace)
        os.makedirs(local_workspace)

        Logger.info("End Stage 1: Init local workspace")

        # Stage 2: Bind local workspace to origin and mirror
        Logger.info("Start Stage 2: Bind local workspace to origin and mirror")
        
        # cd workspace
        os.chdir(local_workspace)

        # git init
        git_init_cmd = [
            "git",
            "init",
            "--initial-branch=false"
        ]
        returncode, _, _ = run_cmd(git_init_cmd)
        if returncode != 0:
            Logger.error("Failed to git init")
            return -4

        # git remote add origin
        git_add_remote_origin_cmd = [
            "git",
            "remote",
            "add",
            origin_remote_name,
            origin_repo_url
        ]
        returncode, _, _ = run_cmd(git_add_remote_origin_cmd)
        if returncode != 0:
            Logger.error("Failed to add origin repo url as remote")
            return -5
        
        # git remote add mirror
        git_add_remote_mirror_cmd = [
            "git",
            "remote",
            "add",
            mirror_remote_name,
            mirror_repo_url
        ]
        returncode, _, _ = run_cmd(git_add_remote_mirror_cmd)
        if returncode != 0:
            Logger.error("Failed to add mirror repo url as remote")
            return -6

        Logger.info("End Stage 2: Bind local workspace to origin and mirror")

        # Stage 3: Diff origin changed branches base mirror
        Logger.info("Start Stage 3: Diff origin changed branches base mirror")

        # Get origin remote branch info
        git_ls_origin_remote_branch_cmd = [
            "git",
            "ls-remote",
            "-h",
            origin_remote_name
        ]
        returncode, origin_branches_str, _ = run_cmd(git_ls_origin_remote_branch_cmd)
        if returncode != 0:
            Logger.error("Failed to ls-remote origin repo branches")
            return -7
        
        origin_branches_dict = {}
        for line in origin_branches_str.splitlines():
            if line.strip():
                commit_hash, ref_part = line.split()
                branch_name = ref_part.split('/')[-1]
                origin_branches_dict[branch_name] = commit_hash

        # Get mirror remote branch info
        git_ls_mirror_remote_branch_cmd = [
            "git",
            "ls-remote",
            "-h",
            mirror_remote_name
        ]
        returncode, mirror_branches_str, _ = run_cmd(git_ls_mirror_remote_branch_cmd)
        if returncode != 0:
            Logger.error("Failed to ls-remote mirror repo branches")
            return -8
        
        mirror_branches_dict = {}
        for line in mirror_branches_str.splitlines():
            if line.strip():
                commit_hash, ref_part = line.split()
                branch_name = ref_part.split('/')[-1]
                mirror_branches_dict[branch_name] = commit_hash

        # get origin branch changes
        origin_branch_changes = get_origin_branch_changes(origin_branches_dict, mirror_branches_dict, changed_branch_accept_rules)
        origin_branch_added = origin_branch_changes["originAdded"]
        origin_branch_updated = origin_branch_changes["originUpdated"]
        Logger.info(f"Origin branch changes: {origin_branch_changes}")

        Logger.info("End Stage 3: Diff origin changed branches")

        # Handle with origin updated branches
        Logger.info("Handle with origin updated branches")
        for b in origin_branch_updated:
            Logger.info(f"Handling updated origin {origin_remote_name} branch {b} into mirror {mirror_remote_name}")

            git_fetch_mirror_remote_branch_cmd = [
                "git",
                "fetch",
                mirror_remote_name,
                f"{b}:{b}",
                "--force"
            ]
            returncode, _, _ = run_cmd(git_fetch_mirror_remote_branch_cmd)
            if returncode != 0:
                Logger.error(f"Failed to fetch mirror remote branch {b}")
                return -9
            
            git_switch_branch_cmd = [
                "git",
                "switch",
                b
            ]
            returncode, _, _ = run_cmd(git_switch_branch_cmd)
            if returncode != 0:
                Logger.error(f"Failed to swith to branch: {b}")
                return -10
            
            git_pull_origin_remote_branch_cmd = [
                "git",
                "pull",
                origin_remote_name,
                b,
                "--no-edit"
            ]
            returncode, _, _ = run_cmd(git_pull_origin_remote_branch_cmd)
            if returncode != 0:
                Logger.error(f"Failed to pull (auto merge) changes of origin {origin_repo_url} branch {b} into mirror {mirror_repo_url}.\n"
                      "Maybe some conflict occurs, need manual merge this branch before push it to mirror.")
                return -101
            
            git_push_mirror_cmd = [
                "git",
                "push",
                mirror_remote_name,
                b
            ]
            returncode, _, _ = run_cmd(git_push_mirror_cmd)
            if returncode != 0:
                Logger.error(f"Failed to push branch {b} to mirror {mirror_remote_name}. Perhaps during the sync, the {mirror_remote_name} received new commits, so it might need to be run again.\n")
                return -11
            
        # Handle with origin added branches
        Logger.info("Handle with origin added branches")
        for b in origin_branch_added:
            Logger.info(f"Handling added origin {origin_remote_name} branch {b} into mirror {mirror_remote_name}")

            git_fetch_origin_remote_branch_cmd = [
                "git",
                "fetch",
                origin_remote_name,
                f"{b}:{b}",
                "--force"
            ]
            returncode, _, _ = run_cmd(git_fetch_origin_remote_branch_cmd)
            if returncode != 0:
                Logger.error(f"Failed to fetch origin remote added branch {b}")
                return -12

            git_push_origin_added_branch_to_mirror_cmd = [
                "git",
                "push",
                mirror_remote_name,
                b
            ]
            returncode, _, _ = run_cmd(git_push_origin_added_branch_to_mirror_cmd)
            if returncode != 0:
                Logger.error(f"Failed to push origin remote added branch {b} on mirror. Perhaps during the sync, the {mirror_remote_name} received new branch {b}, please check it.")
                return -13

        # Handle tag change
        git_fetch_mirror_tags_cmd = [
            "git",
            "fetch",
            mirror_remote_name,
            "--tags"
        ]
        returncode, _, _ = run_cmd(git_fetch_mirror_tags_cmd)
        if returncode != 0:
            Logger.error("Failed to fetch tags on mirror")
            return -14

        # origin override mirror tags
        git_fetch_origin_tags_cmd = [
            "git",
            "fetch",
            origin_remote_name,
            "--tags"
        ]
        returncode, _, _ = run_cmd(git_fetch_origin_tags_cmd)
        if returncode != 0:
            Logger.error("Failed to fetch tags on origin")
            return -15
    
        git_push_tags_to_mirror_cmd = [
            "git",
            "push",
            mirror_remote_name,
            "-f"
            "--tags"
        ]
        returncode, _, _ = run_cmd(git_push_tags_to_mirror_cmd)
        if returncode != 0:
            Logger.error("Failed to push tags on mirror")
            return -16
        
        Logger.info("Finished to pull origin update to mirror")
        return 0

    except Exception as e:
        Logger.error(f"Error: {e}")
        return -1
    finally:
        os.chdir(cwd)


def main() -> int:
    try:
        Logger.init(".log")

        # Configuration Parsing
        Logger.info("Configuration Parsing.")

        current_dir = os.path.dirname(os.path.abspath(__file__))
        config_json_path = os.path.join(current_dir, "sync-origin-and-mirror-config.json")
        with open(config_json_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        local_workspace = os.path.normpath(data["local-workspace"])
        sync_needed_repo_pairs = data["sync-needed-repo-pairs"]

        # 从配置文件读取正则表达式规则
        origin_changed_branch_accept_rules = data["origin-changed-branch-accept-rules"]
        mirror_changed_branch_accept_rules = data["mirror-changed-branch-accept-rules"]

        mirror_needed_repo_pair_list = []
        for repo_pair in sync_needed_repo_pairs:
            origin_repo_url = repo_pair["origin-repo-ssh-url"]
            mirror_repo_url = repo_pair["mirror-empty-repo-ssh-url"]
            mirror_needed_repo_pair_list.append((origin_repo_url, mirror_repo_url))

        Logger.info("End of Configuration Parsing.")

        # Sync between two repos.
        Logger.info("Sync between two repos.")
        
        returncode = try_sync_origin_updates_into_mirror(origin_repo_url, mirror_repo_url, local_workspace, origin_changed_branch_accept_rules)
        if returncode != 0:
            return returncode

        return_code = try_sync_origin_updates_into_mirror(mirror_repo_url, origin_repo_url, local_workspace, mirror_changed_branch_accept_rules)
        if return_code != 0:
            return returncode

        return 0

    except Exception as e:
        Logger.error(f"Error: {e}")
        return -1


if __name__ == "__main__":
    returncode = main()
    sys.exit(returncode)