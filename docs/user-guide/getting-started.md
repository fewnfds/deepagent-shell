# 启动并认识管理台

## 启动

Windows 源码 Clone 从项目根运行：

```powershell
.\start_server.bat
```

首次启动输入两次管理密码。默认管理台地址是 <http://127.0.0.1:19100/admin>。管理密码用于 `/admin` 与
`/api/*`；首页的 API Key 用于 `/v1/*`。

## 管理台入口

- 【Workflow】：管理公开 model、共享 Filesystem 和 Vue Flow 画布；
- 【系统】：系统配置、文件管理、日志中心和历史会话；
- 【Agent】：Main Agent 与一层可复用 Subagent；
- 【组件】：十四类可复用能力，包括 Filesystem、权限和独立 Middleware 装配；
- 【配置仓库】：查看、复制、编辑和删除配置；
- 【词库】与【样式实验室】：术语查询和 UI 样式实验。

## 第一份可运行 Workflow

1. 在【组件 / Filesystem】创建共享空间配置。
2. 创建模型、输出模式和 Main Agent；需要把客户端多轮消息整理到 Agent 初始上下文时，创建并装配
   `Workflow 输入上下文`组件，或按需使用自定义 `before_agent` Middleware 包。
3. 在【Workflow】新建记录，选择该 Filesystem；点击【编辑 Flow】进入全屏画布。
4. 添加 Agent 节点，选择 Main Agent，连接 `Start -> Agent -> End` 并保存。
5. 启用 Workflow，在首页设置 API Key 并启动 API Server。
6. 调用 `/v1/models` 确认名称，再使用该名称调用 `/v1/chat/completions`。
