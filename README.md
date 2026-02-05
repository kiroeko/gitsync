# GitSync

Git 仓库跨平台同步工具。支持在不同 Git 托管平台（如 GitHub、GitLab）之间自动同步分支与标签。

## 前置条件

### 1. Git 权限配置（必须先完成）

脚本通过 `git` 命令行操作远程仓库，运行前**必须**确保当前 Windows 用户已配置好对所有相关仓库的访问权限。

**SSH 方式（推荐）：**

```powershell
# 生成 SSH 密钥（如尚未生成）
ssh-keygen -t rsa -C "xx@x.com"

# 将公钥添加到 GitHub / GitLab 等平台的 SSH Keys 设置中
cat ~/.ssh/id_rsa.pub

# 验证连接
ssh -T git@github.com
ssh -T git@gitlab.com
```

**HTTPS 方式：**

```powershell
# 使用 Git Credential Manager 缓存凭据
git config --global credential.helper manager
# 首次操作时会弹出登录窗口，后续自动使用缓存的凭据
```

> 如果同步涉及多个平台（如 GitHub 到 GitLab），需要分别在每个平台上配置好对应的访问权限。

### 2. 系统要求

- **Windows** 操作系统
- **Python** >= 3.10
- **Git** 已安装并可在命令行中使用

## 运行方式

**所有脚本必须以 Windows 用户态的进程/子进程运行**，不要以 SYSTEM 账户或服务方式直接调用。这是因为：

- Git 凭据（SSH 密钥、Credential Manager）绑定在当前用户的 profile 下
- 以 SYSTEM 或其他服务账户运行时，无法访问用户的 `~/.ssh/` 密钥和凭据存储
- 如需通过计划任务或服务触发，应配置为以**目标用户身份**运行，或通过该用户的会话启动进程/子进程

## 构建

```powershell
# 在线构建（需要网络）
.\build.ps1

# 离线构建（需要先下载依赖包）
.\offline_get.ps1          # 下载依赖到 offline_packages/
.\offline_build.ps1        # 从本地包安装
```

构建过程会创建 `.venv` 虚拟环境并以开发模式安装项目。

## 幂等性

所有操作均设计为**幂等**的——多次执行与单次执行产生相同的最终结果，不会引入副作用。因此：

- 脚本执行中断后可以放心重跑，无需手动清理（除非 git/ssh 进程意外无法退出占用工作目录的情况，这时只需要停止进程）
- 定时任务重复触发不会导致数据不一致
- 网络波动、进程异常退出等情况下，重新运行即可恢复到正确状态

初始化脚本每次运行都会清理并重建本地工作目录，确保起始状态一致；同步脚本通过比对远程引用来判断差异，仅推送实际变更，已同步的内容会被跳过。

## 使用

### 初始化镜像仓库

首次同步前，需要先将源仓库的完整内容推送到目标空仓库。提供两种方式：

#### 一步式

编辑 `init/one-step/make-mirror-git-repo-config.json`：

```json
{
    "local-workspace": "C:/public/gitsync_workspace",
    "mirror-needed-repo-pairs": [
        {
            "origin-repo-ssh-url": "git@github.com:user/repo.git",
            "mirror-empty-repo-ssh-url": "git@gitlab.com:user/repo.git"
        }
    ]
}
```

运行：

```powershell
.venv\Scripts\python.exe init\one-step\make-mirror-git-repo.py
```

#### 两步式

适用于需要分阶段操作的场景（如先拉取到本地审查，再推送到目标）。

```powershell
# 第一步：从源仓库拉取到本地
.venv\Scripts\python.exe init\two-step\fetch-git-repo.py

# 第二步：推送到目标仓库
.venv\Scripts\python.exe init\two-step\push-git-repo.py
```

配置文件分别为 `fetch-git-repo-config.json` 和 `push-git-repo-config.json`。

### 持续同步

编辑 `sync/sync-origin-and-mirror-config.json`：

```json
{
    "local-workspace": "C:/public/gitsync_workspace",
    "sync-needed-repo-pairs": [
        {
            "origin-repo-url": "https://github.com/user/repo.git",
            "mirror-repo-url": "git@gitlab.com:user/repo.git"
        }
    ],
    "origin-changed-branch-accept-rules": [".*"],
    "mirror-changed-branch-accept-rules": ["^mirror/.*"]
}
```

运行：

```powershell
.\sync\sync.ps1
```

#### 配置说明

| 字段 | 说明 |
|------|------|
| `local-workspace` | 本地工作目录，用于临时存放 git 数据 |
| `sync-needed-repo-pairs` | 需要同步的仓库对列表 |
| `origin-changed-branch-accept-rules` | 正则表达式列表，匹配的 origin 分支变更会同步到 mirror |
| `mirror-changed-branch-accept-rules` | 正则表达式列表，匹配的 mirror 分支变更会同步回 origin |

#### 定时执行

可通过 Windows 任务计划程序定期运行同步脚本。**务必将任务配置为以拥有 Git 权限的用户身份运行：**

```powershell
# 示例：创建每 30 分钟执行一次的计划任务（以当前用户身份运行）
schtasks /create /tn "GitSync" /tr "powershell -ExecutionPolicy Bypass -File C:\public\workspace\gitsync\sync\sync.ps1" /sc minute /mo 30 /ru %USERNAME%
```

## 项目结构

```
gitsync/
├── sync/                           # 持续同步
│   ├── sync-origin-and-mirror.py   # 同步主脚本
│   ├── sync-origin-and-mirror-config.json
│   └── sync.ps1                    # PowerShell 入口
├── init/                           # 初始化镜像
│   ├── one-step/                   # 一步式初始化
│   └── two-step/                   # 两步式初始化
├── utils/                          # 工具模块
│   ├── cmdutils.py                 # 命令执行
│   ├── fileutils.py                # 文件权限处理
│   └── logger.py                   # 线程安全日志
├── build.ps1                       # 在线构建
├── offline_build.ps1               # 离线构建
├── offline_get.ps1                 # 下载离线依赖
└── pyproject.toml
```
