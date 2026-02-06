import json
import os
import re
import sys
import shutil
import traceback
from typing import TypedDict

from utils import *


class BranchChanges(TypedDict):
    originAdded: list[str]
    originUpdated: list[str]


class TagChanges(TypedDict):
    originAdded: list[str]
    originUpdated: list[str]


def parse_ls_remote_tags(ls_remote_output: str) -> dict[str, str]:
    """
    Parse git ls-remote --tags output into {tag_name: hash}.
    For annotated tags (which have both a tag object line and a ^{} deref line),
    use the ^{} (dereferenced commit) hash as the comparison value,
    so we compare actual commits rather than tag object hashes.
    For lightweight tags, use the single hash directly.
    """
    tag_dict = {}
    for line in ls_remote_output.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2:
            Logger.warning(f"Unexpected ls-remote tag output, skipping: {line}")
            continue
        hash_val, ref = parts
        if not ref.startswith("refs/tags/"):
            # Skip non-tag lines, e.g. "From https://..."
            continue
        if ref.endswith("^{}"):
            # Dereferenced annotated tag - overwrite the tag object hash
            tag_name = ref.removeprefix("refs/tags/").removesuffix("^{}")
            tag_dict[tag_name] = hash_val
        else:
            tag_name = ref.removeprefix("refs/tags/")
            # Only set if not already set by a ^{} line
            if tag_name not in tag_dict:
                tag_dict[tag_name] = hash_val
    return tag_dict


def get_origin_tag_changes(
        origin_tag_dict: dict[str, str],
        mirror_tag_dict: dict[str, str]
    ) -> TagChanges:
    """
    Compare tags between origin and mirror repos.
    Only detects added and updated tags. Does not handle deletions.
    """
    tag_added_list = []
    tag_updated_list = []

    for tag_name, origin_hash in origin_tag_dict.items():
        if tag_name in mirror_tag_dict:
            if origin_hash != mirror_tag_dict[tag_name]:
                tag_updated_list.append(tag_name)
                Logger.info(f"Tag '{tag_name}' needs update: origin={origin_hash[:8]}, mirror={mirror_tag_dict[tag_name][:8]}")
            else:
                Logger.info(f"Tag '{tag_name}' is already up-to-date: hash={origin_hash[:8]}")
        else:
            tag_added_list.append(tag_name)

    return {
        "originAdded": tag_added_list,
        "originUpdated": tag_updated_list,
    }


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
    cwd = os.getcwd()
    try:
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
                parts = line.split()
                if len(parts) != 2:
                    Logger.warning(f"Unexpected ls-remote output line in remote {origin_repo_url}, skipping: {line}")
                    continue
                commit_hash, ref_part = parts
                branch_name = ref_part.removeprefix("refs/heads/")
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
                parts = line.split()
                if len(parts) != 2:
                    Logger.warning(f"Unexpected ls-remote output line in remote {mirror_repo_url}, skipping: {line}")
                    continue
                commit_hash, ref_part = parts
                branch_name = ref_part.removeprefix("refs/heads/")
                mirror_branches_dict[branch_name] = commit_hash

        # get origin branch changes
        origin_branch_changes = get_origin_branch_changes(origin_branches_dict, mirror_branches_dict, changed_branch_accept_rules)
        origin_branch_added = origin_branch_changes["originAdded"]
        origin_branch_updated = origin_branch_changes["originUpdated"]
        Logger.info(f"Origin branch changes: {origin_branch_changes}")

        Logger.info("End Stage 3: Diff origin changed branches")

        # Handle with origin updated branches
        Logger.info("Handle with origin updated branches")
        has_updated_branch_error = False
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
                Logger.error(f"Failed to fetch mirror {mirror_remote_name} branch {b}, return code: {returncode}")
                has_updated_branch_error = True
                continue

            git_switch_branch_cmd = [
                "git",
                "switch",
                b
            ]
            returncode, _, _ = run_cmd(git_switch_branch_cmd)
            if returncode != 0:
                Logger.error(f"Failed to switch to branch {b}, return code: {returncode}")
                has_updated_branch_error = True
                continue

            git_pull_origin_remote_branch_cmd = [
                "git",
                "pull",
                origin_remote_name,
                b,
                "--no-edit"
            ]
            returncode, _, _ = run_cmd(git_pull_origin_remote_branch_cmd)
            if returncode != 0:
                Logger.error(f"Failed to pull (auto merge) changes of origin {origin_repo_url} branch {b} into mirror {mirror_repo_url}, return code: {returncode}. "
                      "Maybe some conflict occurs, need manual merge this branch before push it to mirror.")
                abort_returncode, _, _ = run_cmd(["git", "merge", "--abort"])
                if abort_returncode != 0:
                    Logger.error(f"Failed to abort merge on branch {b}, return code: {abort_returncode}. Working tree may be in a dirty state, stopping.")
                    return -14
                has_updated_branch_error = True
                continue

            git_push_mirror_cmd = [
                "git",
                "push",
                mirror_remote_name,
                b
            ]
            returncode, _, _ = run_cmd(git_push_mirror_cmd)
            if returncode != 0:
                Logger.error(f"Failed to push branch {b} from {origin_remote_name} to {mirror_remote_name}, return code: {returncode}. Perhaps during the sync, the {mirror_remote_name} received new commits, so it might need to be run again.")
                has_updated_branch_error = True
                continue
            
        # Handle with origin added branches
        Logger.info("Handle with origin added branches")
        has_added_branch_error = False
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
                Logger.error(f"Failed to fetch origin {origin_remote_name} added branch {b}, return code: {returncode}")
                has_added_branch_error = True
                continue

            git_push_origin_added_branch_to_mirror_cmd = [
                "git",
                "push",
                mirror_remote_name,
                b
            ]
            returncode, _, _ = run_cmd(git_push_origin_added_branch_to_mirror_cmd)
            if returncode != 0:
                Logger.error(f"Failed to push added branch {b} from {origin_remote_name} to {mirror_remote_name}, return code: {returncode}. Perhaps during the sync, the {mirror_remote_name} received new branch {b}, please check it.")
                has_added_branch_error = True
                continue

        if has_updated_branch_error or has_added_branch_error:
            Logger.warning("Some branches failed to sync, but will continue with tag sync since tags do not depend on branch sync.")

        # Handle tag change using ls-remote diff
        Logger.info("Handle tag changes")

        git_ls_origin_tags_cmd = ["git", "ls-remote", "--tags", origin_remote_name]
        returncode, origin_tags_str, _ = run_cmd(git_ls_origin_tags_cmd)
        if returncode != 0:
            Logger.error(f"Failed to ls-remote tags from {origin_remote_name}, return code: {returncode}")
            return -11

        git_ls_mirror_tags_cmd = ["git", "ls-remote", "--tags", mirror_remote_name]
        returncode, mirror_tags_str, _ = run_cmd(git_ls_mirror_tags_cmd)
        if returncode != 0:
            Logger.error(f"Failed to ls-remote tags from {mirror_remote_name}, return code: {returncode}")
            return -12

        origin_tag_dict = parse_ls_remote_tags(origin_tags_str)
        mirror_tag_dict = parse_ls_remote_tags(mirror_tags_str)

        tag_changes = get_origin_tag_changes(origin_tag_dict, mirror_tag_dict)
        tags_to_sync = tag_changes["originAdded"] + tag_changes["originUpdated"]
        Logger.info(f"Tag changes: {tag_changes}")

        has_tag_error = False
        for tag_name in tags_to_sync:
            Logger.info(f"Syncing tag '{tag_name}' from {origin_remote_name} to {mirror_remote_name}")

            git_fetch_tag_cmd = ["git", "fetch", origin_remote_name, "tag", tag_name, "--force"]
            returncode, _, _ = run_cmd(git_fetch_tag_cmd)
            if returncode != 0:
                Logger.error(f"Failed to fetch tag '{tag_name}' from {origin_remote_name}, return code: {returncode}")
                has_tag_error = True
                continue

            git_push_tag_cmd = ["git", "push", mirror_remote_name, f"refs/tags/{tag_name}", "-f"]
            returncode, _, _ = run_cmd(git_push_tag_cmd)
            if returncode != 0:
                Logger.error(f"Failed to push tag '{tag_name}' to {mirror_remote_name}, return code: {returncode}")
                has_tag_error = True
                continue

        Logger.info("Finished to pull origin update to mirror")
        if has_updated_branch_error:
            return -9
        if has_added_branch_error:
            return -10
        if has_tag_error:
            return -13
        return 0

    except Exception as e:
        Logger.error(f"Error: {e}\n{traceback.format_exc()}")
        return -14
    finally:
        os.chdir(cwd)


def main() -> int:
    try:
        Logger.init("sync_origin_and_mirror_log")

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
            origin_repo_url = repo_pair["origin-repo-url"]
            mirror_repo_url = repo_pair["mirror-repo-url"]
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
            return -2

        # Sync between two repos.
        Logger.info("Sync between two repos.")

        has_sync_error = False
        for origin_repo_url, mirror_repo_url in mirror_needed_repo_pair_list:
            returncode = try_sync_origin_updates_into_mirror(origin_repo_url, mirror_repo_url, local_workspace, origin_changed_branch_accept_rules)
            if returncode != 0:
                Logger.error(f"Failed to sync {origin_repo_url} -> {mirror_repo_url}, return code: {returncode}. ")
                has_sync_error = True

            returncode = try_sync_origin_updates_into_mirror(mirror_repo_url, origin_repo_url, local_workspace, mirror_changed_branch_accept_rules)
            if returncode != 0:
                Logger.error(f"Failed to sync {mirror_repo_url} -> {origin_repo_url}, return code: {returncode}")
                has_sync_error = True

        if has_sync_error:
            return -3
        return 0

    except Exception as e:
        Logger.error(f"Error: {e}\n{traceback.format_exc()}")
        return -1


if __name__ == "__main__":
    returncode = main()
    sys.exit(returncode)