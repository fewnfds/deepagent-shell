# Docker 部署

Docker 是 DeepAgent Shell 正式版本的 Linux amd64/服务器交付方式，不是 Windows 便携版的前置环境。
只有 GitHub Releases 中实际存在的版本才有对应 GHCR image；源码版本字段本身不代表镜像已经发布。
已有正式版本时使用：

```text
ghcr.io/fewnfds/deepdeepagent-shell:<version>
```

## 首次启动

从对应版本的源码包或 tag 取得 `compose.yaml` 和启动脚本。Windows 使用：

```powershell
.\start_docker.ps1
```

Linux 使用：

```sh
sh ./start_docker.sh
```

首次启动会分别要求输入并确认管理密码和 API Key，长度由用户决定；两项输入可以使用相同值。
管理密码写入 `data/config/deepagent-shell.env`，API Key 写入 SQLite。已有有效配置保持原值。

默认访问 <http://127.0.0.1:19100/admin/>。查看服务状态和日志：

```powershell
docker compose ps
docker compose logs --tail 100 deepagent-shell
```

这两条查看命令假定使用默认仓库目录和默认 `./data`。通过参数选择了其他 data 目录时，最简单的
更新方式是继续使用同一参数重新运行启动脚本；手工执行 Compose 命令则必须提供相同的
`COMPOSE_DATA_DIR`、image 和 env file 上下文。

## 持久数据目录

Compose 只把一个宿主目录挂载为容器内固定的 `/app/data`。宿主目录叫什么、放在哪里都可以；
它的名称不属于应用契约。Windows 可这样指定其他磁盘：

```powershell
.\start_docker.ps1 -DataDirectory H:\deepagent-shell-data
```

Linux 启动脚本的第一个参数是数据目录：

```sh
sh ./start_docker.sh /srv/deepagent-shell-data
```

这个目录包含启动配置、SQLite、用户文件、Skill/Tool/Middleware 和持久日志。停止服务、删除容器、
更新镜像后，只要继续挂载同一目录，实例数据就仍然存在。`runtime/` 使用容器临时文件系统，不需要
保存。

停止实例但保留数据：

```powershell
docker compose down
```

不要用 `docker compose down -v` 或删除宿主数据目录来清理单项配置。完整目录结构、冷迁移和文件
管理说明见[数据、文件管理与系统配置](user-guide/system-management.md)。

## 端口与设置

`data/config/deepagent-shell.env` 保存应用设置。Docker 首次初始化的默认值为：

```dotenv
DEEPAGENT_SHELL_HOST=0.0.0.0
DEEPAGENT_SHELL_PORT=19100
```

- `DEEPAGENT_SHELL_PORT` 同时用于容器监听端口和宿主映射端口；
- Docker 中应保持 `DEEPAGENT_SHELL_HOST=0.0.0.0`，否则端口映射无法连接到容器内服务；
- 保存【系统配置】后重新运行正式 Docker 启动脚本，Compose 会重建服务并应用新端口。
- 管理密码保存在 env 文件中；API Key 在【系统 / 系统配置】修改并立即生效。

远程部署仍应只通过外部 HTTPS 反向代理和防火墙暴露。应用本身提供 HTTP，不内置 TLS。

## 更新或选择镜像

需要更新时拉取目标版本或 `latest`，再重新运行启动脚本：

```powershell
docker pull ghcr.io/fewnfds/deepdeepagent-shell:latest
.\start_docker.ps1
```

Windows 可显式选择镜像：

```powershell
.\start_docker.ps1 -Image ghcr.io/fewnfds/deepdeepagent-shell:<version>
```

Linux 可设置 `DEEPAGENT_SHELL_IMAGE`：

```sh
DEEPAGENT_SHELL_IMAGE=ghcr.io/fewnfds/deepdeepagent-shell:<version> sh ./start_docker.sh
```

当前构建链只发布 Linux amd64/glibc image，不承诺 ARM64、Alpine/musl 或 Linux 原生便携包。容器
主服务以非 root 用户运行，并通过 `/api/health` healthcheck。

## 外部文件系统映射

【文件管理】只管理 `/app/data` 中的四个用户数据 scope。Agent 的 filesystem 组件若要访问另一个
宿主项目目录，需要额外挂载到容器，例如 `/workspaces/project`，并在页面填写这个容器内 POSIX
路径。Windows 的 `H:\...` 不能直接作为容器内路径。

外部 workspace 不属于 DeepAgent Shell 的 `data/`，迁移实例时要单独处理。远程 Docker daemon 的 bind
source 位于 daemon 主机，不是运行 Docker CLI 的客户端电脑。
