# 启动并认识管理台

## 启动

Windows 源码 Clone 从项目根运行：

```powershell
.\start_server.bat
```

首次启动输入两次管理密码。默认管理台地址是 <http://127.0.0.1:19100/admin>。管理密码用于 `/admin` 与
`/api/*`；首页的 API Key 用于 `/v1/*`。

## 管理台入口

- 【Workflow】：管理公开 model 与 Main Agent 的根图入口；
- 【系统】：系统配置、文件管理、日志中心和历史会话；
- 【Agent】：Main Agent 与一层可复用 Subagent；
- 【组件】：十二类可复用能力，包括 Middleware 包装配；
- 【配置仓库】：查看、复制、编辑和删除配置；
- 【词库】与【样式实验室】：术语查询和 UI 样式实验。

## 第一份可调用 Workflow

1. 在【组件 / 模型】保存一个可用模型。
2. 在【组件 / 输出模式】保存一套输出模板。
3. 在【Agent / Main Agent】选择这两个必选组件并保存。
4. 在【Workflow】新建记录，选择刚才的 Main Agent 并启用。
5. 在首页设置 API Key 并启动 API Server。
6. 使用 Workflow 名称调用 `/v1/chat/completions`。

需要把客户端消息传给 Agent 时，配置一个自定义 Middleware 包；Shell 不隐式把完整聊天正文塞入活动 messages。
