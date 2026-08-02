# 启动并认识管理台

## 启动

支持 Windows 10/11 x64。需要持续更新的用户安装 Git 和 Node.js 22（含 npm），Clone 滚动 `dev`
分支后运行：

```powershell
git clone --branch dev https://github.com/fewnfds/deepdeepagent-shell.git
cd deepagent-shell
.\start_server.bat
```

干净 Clone 一开始不包含 `data/` 或 `runtime/`。需要沿用当前版本的已有实例时，先完全停止旧实例并把
完整 `data/` 复制到新目录；否则首次启动会创建缺失的数据目录。已有的有效 `data/` 会被直接加载，
启动和后续 pull 都不会用源码默认值覆盖它。

源码 Clone 首次运行会联网准备固定 Python runtime、锁定前端依赖和 production 管理台；以后只有
runtime 或前端输入变化时刷新对应部分。正常启动不会运行 Vite Debug，也不会构建 ZIP、Docker 或
其他正式发行物。

停止服务后使用 `git pull --ff-only` 更新，再重新运行 `start_server.bat`。运行目录自己的 `data/` 被
Git 忽略，不会被 pull 覆盖；不要在这个运行目录中切换 `main/dev` 或手工编辑源码。只需要稳定源码时
改为 Clone 默认 `main`。

只有 [GitHub Releases](https://github.com/fewnfds/deepdeepagent-shell/releases) 中实际存在的版本才提供 Windows
ZIP。ZIP 解压后同样运行：

```powershell
.\start_server.bat
```

ZIP 已包含固定 CPython、锁定依赖、DeepAgent Shell wheel 和管理台；普通使用不需要 Git、Python、
Node.js、uv、编译器或首次启动网络。是否已有可下载版本以 Release 页面为准，不能只根据源码版本号
推断。自行构建见[从源码构建 Windows 发行包](../building-windows-release.md)。

没有已有配置时，控制台随后引导输入并确认管理网站密码，输入过程不会显示。脚本创建
`data/config/deepagent-shell.env`；以后双击时检测到已有密码便直接启动，不会再次询问或覆盖。该步骤只
设置管理网站密码。用户调用 `/v1/*` 使用的 API Key 随后在【系统 / 系统配置】设置；两项凭据可以使用相同值。

端口被占用时，脚本会显示 PID，并让用户选择关闭该进程、输入另一个端口或取消；没有监听进程但端口
被 Windows 保留时，也会在启动前识别并要求选择其他端口。临时选择只影响本次启动；进入【系统 / 系统
配置】保存新端口后，下一次启动才会继续使用它。启动脚本始终把当前脚本所在目录作为 application
home：`data/` 是完整用户持久数据，`runtime/` 是可重新生成的运行态。复制或移动整个目录后，再次
启动会使用新位置，不会引用原目录。便携入口还会忽略宿主 `DEEPAGENT_SHELL_*`、`PYTHONHOME` 和
`PYTHONPATH`。

新实例当前默认打开 <http://127.0.0.1:19100/admin>；已有实例或本次临时选择了其他端口时，以启动器
实际打印的地址为准。首次读取管理数据时输入上述管理密码。密码只保存在当前
页面内存，刷新或关闭页面后需要重新输入。右上角提供语言图标、浅色/深色/跟随系统三态主题图标，以及
带状态提示的 API Server 启停图标；语言和主题偏好保存在当前浏览器中，不进入配置或后端 payload。

## 六个一级入口

1. 【首页】：查看 API 接入地址和配置报警；API Server 状态与启停位于全局右上角。
2. 【系统】：系统配置、用户文件管理、日志中心和历史会话。
3. 【Agent】：装配 Primary，并配置可复用 Subagent 与 Context Worker 策略。
4. 【组件】：按 manifest 顺序编辑十二类能力。
5. 【配置仓库】：查看、复制、编辑和删除配置。
6. 【术语】：搜索 AI/Agent 中英术语，不保存配置。

## 第一份可调用 Agent

1. 在【组件 / 模型】先选择当前版本内置的 LangChain Provider，再填写 Base URL、可选 Key、模型名和
   该 Provider 的原生参数；Vertex AI 使用 ADC，不填写普通 Key。
2. 保存模型配置。
3. 在【组件 / 文件系统】填写名称并保存。即使暂时不映射目录，也必须保存一份配置；路径列表可以
   留空，工具可见性按实际需要选择。
4. 在【组件 / 输出模式】填写名称，确认需要输出的事件和模板后保存。
5. 在【Agent / Primary Agent】填写 Primary 名称，并分别选择刚才保存的模型、文件系统和输出模式。
6. 确认服务端草稿校验显示绿色勾选且没有问题，再保存 Primary；少选任一必需组件时，报告会明确列出问题，
   服务端保存也会拒绝。
7. 在【系统 / 系统配置】设置用户调用使用的 API Key 并保存，再点击右上角停止状态图标启动；全部公开
   Primary 通过后端静态门禁后，图标会切换为运行状态。失败报告不会关闭管理网站，可返回配置页修复。
8. 携带该 Key 从 `/v1/models` 查看公开名称，或直接调用 `/v1/chat/completions`。

API Server 开启后仍可继续编辑配置；每个新请求在构造 Agent 前捕获当时最新提交的数据库配置，
已经开始的请求不会被后续数据库修改改变。Skill、Custom Tool 和 filesystem 路径属于实时外部资源，
不在这份数据库快照内。

保存的 Primary 名称就是公开 model ID，不暴露内部 UUID。管理台载入已有 UUID 后保存会始终更新
该 UUID，包括改名；旧名称随即失效。只有明确选择“新建”草稿时才创建新 UUID。

## 保存规则

组件、Primary 和 Subagent 覆写都使用页面标题区的“保存”：

- “新建”草稿没有 UUID，保存时由服务端创建新 UUID；
- 从下拉框或仓库“编辑”载入已有配置后，表单携带明确 UUID，保存始终对该 UUID 执行更新；
- 名称不会用于猜测更新目标、修复引用或覆盖另一项；同类型重名由服务端拒绝；
- 若要基于已有记录创建新 UUID，使用配置仓库的“复制”，或先明确点击“新建”再录入；
- 删除统一在【配置仓库】执行。

装配引用始终只认 UUID。更新既有配置的名称不会改变引用 UUID；复制或新建得到新 UUID 后，需要在
Primary 或 Subagent 装配页显式选择它。
