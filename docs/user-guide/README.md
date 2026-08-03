# Agent Shell 用户指南

Agent Shell 通过管理台组合 Deep Agents 配置，并把 Primary Agent 暴露为 OpenAI-compatible model。

推荐顺序：

1. [启动并认识管理台](getting-started.md)
2. [创建组件](capabilities.md)
3. [装配 Primary 与 Subagent](configuration-workflow.md)
4. [管理配置仓库](configuration-library.md)
5. [调用 API Server](api-server.md)
6. [查看最终 ModelRequest](interception-test.md)
7. [查看日志与历史会话](runtime-observability.md)
8. [管理数据、文件与系统设置](system-management.md)

使用时记住三条边界：Primary 必须选择模型和输出模式；客户端负责在每次请求中提交完整消息；
`data/` 是需要备份和迁移的完整实例数据根。
