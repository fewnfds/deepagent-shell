# deepagent-shell 用户指南

管理台用于创建组件、装配 Agent，并把保存的 Primary 作为 OpenAI-compatible model 调用。
表单保存成功只说明字段和当前 UUID 引用有效；每次真实请求仍会复查依赖、磁盘资源、Python
构造配方和 Provider。

## 阅读顺序

1. [启动并认识管理台](getting-started.md)
2. [创建组件](capabilities.md)
3. [装配 Primary、Subagent 与 Context Worker](configuration-workflow.md)
4. [使用配置仓库](configuration-library.md)
5. [调用 API Server](api-server.md)
6. [查看最终 ModelRequest](interception-test.md)
7. [查看日志中心与历史会话](runtime-observability.md)
8. [管理数据、文件与系统配置](system-management.md)

最短可运行路径是：分别保存一份模型、文件系统和输出模式配置，在【Agent / Primary Agent】选择这三项，
等服务端装配报告显示绿色勾选且没有问题后保存，通过右上角 API Server 状态图标启动，然后从
`/v1/chat/completions` 使用 Primary 名称调用。其余八类组件都可以随后按需增加。

## 重要边界

- 配置名称只用于显示；管理台用草稿携带的显式 UUID 决定更新目标，装配引用也始终使用服务端 UUID。
- 客户端每轮提交完整 `messages[]`。服务端不自动恢复或合并旧聊天历史。
- `data/` 是用户持久数据，不要通过删除数据库文件清理单项配置。
- 【系统 / 文件管理】只操作 `data/files/` 与三类用户资源；【系统配置】保存后重启生效。
- 资源发现只做静态读取；自定义 Python 内容只有被运行中的 Agent 明确选择后才会物化。
- 模型凭据与 API Server Key 都是 write-only；页面不会重新显示已保存明文。
- 管理网站密码用于 `/api/*`，API Key 用于 `/v1/*`；两者可以使用相同值，权限按请求路径判断。
- 日志中心统一浏览 API 调用、拦截记录、系统日志和 Agent 运行日志；历史会话保留独立的模型请求 Timeline。
