import os
import re
from utils import Logger

def configure_ssh_host(hostname: str) -> bool:
    """
    检查并配置 SSH config 文件
    如果不存在，创建并添加配置
    如果存在，检查是否有对应的 Host 配置，没有或不一致则更新
    
    Args:
        hostname: SSH 主机名（如 gitlab.com）
    
    Returns:
        bool: 配置成功返回 True，失败返回 False
    """
    try:
        ssh_config_path = os.path.join(os.path.expanduser("~"), ".ssh", "config")
        ssh_dir = os.path.dirname(ssh_config_path)
        
        # 确保 .ssh 目录存在
        if not os.path.exists(ssh_dir):
            os.makedirs(ssh_dir, mode=0o700)
            Logger.info(f"Created .ssh directory: {ssh_dir}")
        
        # 需要添加的配置
        host_config = f"Host {hostname}\n    StrictHostKeyChecking no\n"
        
        # 如果 config 文件不存在，创建并添加配置
        if not os.path.exists(ssh_config_path):
            with open(ssh_config_path, "w", encoding="utf-8") as f:
                f.write(host_config)
            os.chmod(ssh_config_path, 0o600)
            Logger.info(f"Created SSH config file and added configuration for {hostname}")
            return True
        
        # 读取现有配置
        with open(ssh_config_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 检查是否已存在该 Host 配置
        host_pattern = re.compile(rf'^Host\s+{re.escape(hostname)}\s*$', re.MULTILINE)
        match = host_pattern.search(content)
        
        if match:
            # 找到 Host 配置的起始位置
            start_pos = match.start()
            
            # 查找下一个 Host 或文件结尾
            next_host_match = re.search(r'^Host\s+', content[match.end():], re.MULTILINE)
            if next_host_match:
                end_pos = match.end() + next_host_match.start()
            else:
                end_pos = len(content)
            
            # 提取当前 Host 配置块
            current_host_block = content[start_pos:end_pos]
            
            # 检查是否包含 StrictHostKeyChecking no
            if re.search(r'^\s*StrictHostKeyChecking\s+no\s*$', current_host_block, re.MULTILINE):
                Logger.info(f"SSH config for {hostname} already exists with correct configuration")
                return True
            else:
                # 配置不一致，需要替换
                Logger.info(f"SSH config for {hostname} exists but configuration differs, updating...")
                new_content = content[:start_pos] + host_config + "\n" + content[end_pos:].lstrip('\n')
                with open(ssh_config_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                Logger.info(f"Updated SSH config for {hostname}")
                return True
        else:
            # 不存在该 Host 配置，追加到文件末尾
            Logger.info(f"SSH config for {hostname} not found, adding...")
            with open(ssh_config_path, "a", encoding="utf-8") as f:
                if not content.endswith('\n'):
                    f.write('\n')
                f.write(host_config)
            Logger.info(f"Added SSH config for {hostname}")
            return True
            
    except Exception as e:
        Logger.error(f"Failed to configure SSH for {hostname}: {e}")
        return False