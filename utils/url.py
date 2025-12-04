import re

def extract_hostname_from_git_url(git_url: str) -> str | None:
    """
    从 Git URL 中提取主机名
    
    Args:
        git_url: Git URL，格式如 git@github.com:kiroeko/kiroeko_doc.git
    
    Returns:
        str: 主机名（如 github.com），如果无法匹配则返回 None
    """
    # 匹配 git@hostname: 格式
    match = re.match(r'git@([^:]+):', git_url)
    if match:
        return match.group(1)
    return None