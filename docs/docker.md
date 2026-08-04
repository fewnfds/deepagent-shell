# Docker 部署

正式镜像为 Linux amd64：

```text
ghcr.io/fewnfds/deepagent-shell:<version>
```

版本使用仓库的 `v<project.version>` tag，并发布到 GitHub Container Registry。

## 启动

从相同 tag 的仓库内容运行：

```powershell
.\start_docker.ps1 -Image ghcr.io/fewnfds/deepagent-shell:<version>
```

```sh
AGENT_SHELL_IMAGE=ghcr.io/fewnfds/deepagent-shell:<version> sh ./start_docker.sh
```

三个启动入口都不默认选择镜像。PowerShell 缺少 `-Image`、Linux 缺少 `AGENT_SHELL_IMAGE`，或 Compose
没有该环境变量时会立即失败；调用方必须明确选择精确 tag 或 digest。

脚本在宿主准备 `data/config/agent-shell.env`，并把宿主 `data/` 映射到容器 `/app/data`。默认访问
<http://127.0.0.1:19100/admin/>。

## 数据与端口

- `/app/data` 是唯一需要持久化的实例目录；升级容器前先停止并备份完整宿主 `data/`；
- Linux 脚本的第一个可选位置参数是宿主 data 路径，镜像通过 `AGENT_SHELL_IMAGE` 指定；
- 容器内 `AGENT_SHELL_HOST` 应保持 `0.0.0.0`；
- `AGENT_SHELL_PORT` 同时决定容器监听端口和官方脚本的宿主映射端口；
- 外部 filesystem 路径必须另外 bind mount，并在组件中填写容器内绝对路径；
- `runtime/`、应用 wheel 和前端产物属于镜像或可重建运行态，不应写入持久卷。

选择新版本时只替换显式 image tag，保留同一个宿主 `data/`。不要使用 `latest` 代替可复现部署所需的精确
版本；启动器不会自动查询或推导版本。远程访问、TLS 和代理要求见[安全与部署](security-and-deployment.md)。
