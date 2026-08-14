# Agent Shell

Agent Shell 是本地 Workflow 与 Deep Agents 管理台。启用的 Workflow 作为 OpenAI-compatible model；每个 Workflow
保存一份当前 Vue Flow 图和共享 Filesystem。画布支持 Start、Agent、Condition 与 End：Agent 节点引用完整
Main Agent 装配，Condition 通过官方 LangGraph conditional edges 按 Workflow State 或 Runtime Context 选择分支，
Agent 内部可通过官方 `SubAgentMiddleware` 同步委派 Subagent。

## 开始

Windows 用户请先阅读[启动指南](docs/user-guide/getting-started.md)，然后运行：

```powershell
.\start_server.bat
```

完整说明请查看[文档索引](docs/README.md)。
