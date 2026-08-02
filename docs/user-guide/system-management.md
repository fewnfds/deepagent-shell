# 数据、文件管理与系统配置

## `data/` 是实例数据根

Agent Shell 把用户持久数据集中在一个 `data/`：

```text
data/
  config/agent-shell.env
  state/agent-shell.sqlite3*
  files/
  resources/
    skills/
    custom_tools/
    custom_middlewares/
  logs/
```

- `config/` 保存启动设置和管理密码；
- `state/` 保存 SQLite、WAL/SHM、API Key、配置、历史和 Provider secret；
- `files/` 保存普通用户文件；
- `resources/` 保存用户 Skill、Custom Tool 和文件型 Middleware；
- `logs/` 保存有界的系统事件日志；Agent 运行日志保存在 `state/` 的 SQLite 中。

Agent Shell 不提供初始 Skill、Custom Tool 或 Custom Middleware 数据。配置、SQLite、用户文件、用户
资源和持久日志全部位于 `data/`；`runtime/` 只放 cache、tmp 和运行 HOME，可在程序停止后重新生成。

源码仓库不携带 `data/`，干净 Clone 可在首次启动前保持没有该目录。程序会创建缺失目录；如果用户先
停机复制了完整、有效且属于当前版本的 `data/`，程序会直接使用其中内容，不用产品默认数据覆盖。
`data/` 和 `runtime/` 都被 Git 忽略，pull 只更新源码。

Windows 便携版和源码运行默认使用程序目录下的 `data/`。Docker 的容器路径固定为 `/app/data`，
宿主目录名称和位置可以任意选择；正式启动脚本把它映射到同一个容器路径。

整个 `data/` 含密码和 Provider/API Key，应当按敏感数据保护，不要上传 Git 或公开分享。

## 停机复制与迁移

当前版本支持简单冷迁移：

1. 完全停止旧 Windows 进程或 Docker 容器；
2. 复制完整 `data/`，不要只复制 `.sqlite3`；
3. 安装同一当前版本，或准备新的同版本容器；
4. Windows 把 `data/` 放到新程序目录，Docker 把复制后的宿主目录映射到 `/app/data`；
5. 正常启动。

必须停机后复制，因为 SQLite 可能仍有已提交内容位于 `-wal`。外部 filesystem/workspace 不在这个
目录内，需要单独复制并保持相应映射。这个操作用于集中数据和普通迁移，不是在线备份、损坏修复或
跨版本降级方案。

## 文件管理

【系统 / 文件管理】首页只显示后端返回的四个相互隔离的根目录，不展示 `data/` 中的 config、state、logs
或其他宿主内容。进入根目录后，页面顶部使用可换行的 `文件管理 / 根目录 / 子目录` 面包屑表示当前位置：

| 页面 scope | 对应目录 | 用途 |
| --- | --- | --- |
| 普通文件 | `data/files/` | 用户文件 |
| Skill | `data/resources/skills/` | Skill 目录及配套文件 |
| Custom Tool | `data/resources/custom_tools/` | 用户 Tool Python 文件 |
| Custom Middleware | `data/resources/custom_middlewares/` | 文件型 Middleware 模板 |

页面支持：

- 浏览目录和面包屑返回；
- 新建文件夹或空 UTF-8 文本文件；
- 上传单个/多个文件以及浏览器选择的文件夹；
- 下载单个文件、重命名和递归删除；
- 下载文件夹，或多选文件和文件夹后打包下载 ZIP；
- 读取和保存 UTF-8 文本。

文件夹和多选下载会先统计待打包的普通文件数量、文件夹数量与压缩前原始大小。页面显示约计大小并
等待确认，确认后后端才生成 ZIP；压缩后的实际下载大小通常更小。ZIP 保留所选项目的顶层名称和
空文件夹，生成过程中使用的临时文件会在响应结束后删除。文件管理不提供移动操作；需要调整目录
位置时，可以删除后重新上传，或新建文件并复制文本内容。

文本编辑上限为 2 MiB。保存时会检查打开文件时的 revision；文件已被其他操作修改就拒绝静默覆盖，
刷新后再编辑即可。二进制文件可以上传和下载，但不能在页面预览或编辑。

页面不能访问 `config/`、`state/`、`logs/`、外部 workspace 或宿主任意路径，也不跟随
符号链接/reparse point。删除目录会递归执行且没有回收站，请先确认目标。第一版不提供 chmod、
权限账户、在线解压、Git clone/update、Office/媒体预览或协同编辑。

文件上传使用流式写入，不要求一次性把整个文件装入服务内存。项目不额外规定单文件、目录总量或
磁盘配额；请按宿主磁盘和网络能力控制超大文件、超大目录及同时上传数量。

Skill、Tool 或文件型 Middleware 保存后，回到对应组件页面刷新即可重新发现。静态发现成功不表示
Python 依赖或运行时构造一定成功；真实 Agent 仍会在选择该资源后执行现有运行校验。

## 系统配置

【系统 / 系统配置】修改 `data/config/agent-shell.env` 中的当前设置：

- 监听 host、应用端口和允许远程访问；
- 替换管理网站密码；
- 替换或清除 API Key；
- 设置一次 API 请求允许的初始消息条数上限；
- 开启或关闭拦截测试与详细诊断；
- CORS origins、可信代理 CIDR；

管理密码和 API Key 都是 write-only，只显示是否已经配置，不返回已保存明文。管理密码留空表示保持原值；
API Key 未编辑时保持原值，输入新值后保存会替换，编辑后清空再保存会清除。管理密码可以与 API Key
使用相同值。页面只提供一个【保存】动作：启动设置写入 `agent-shell.env`，API Key 与初始消息条数上限
写入 SQLite；拦截测试与详细诊断更新当前进程内的运行控制。

API Key、初始消息条数上限和拦截测试保存后立即生效并持久化。详细诊断不再位于本页，由日志中心
【保存策略】单独保存。
host、端口、远程访问、管理密码、CORS 和可信代理等启动设置不会修改正在运行的进程；Windows/source
停止后重新运行正式启动入口，Docker 重新运行
`start_docker.ps1` 或 `start_docker.sh`。Docker 内应保持 host 为 `0.0.0.0`；重建后
`AGENT_SHELL_PORT` 同时成为容器监听和宿主访问端口。

页面不负责终止进程、控制 Docker 或修改反向代理。远程部署、TLS、凭据和代理约束见
[安全与部署](../security-and-deployment.md)。
