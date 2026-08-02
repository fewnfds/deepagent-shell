# 使用说明

`docs/` 只保存当前版本的公开说明，面向安装、配置、调用以及从源码调试/构建 `deepagent-shell` 的用户。
这些文档描述当前功能和可执行流程，不记录开发计划、设计推演、TODO、测试过程或完成日志。

## 开始使用

1. [启动并认识管理台](user-guide/getting-started.md)
2. [创建组件](user-guide/capabilities.md)
3. [装配 Primary 与 Subagent](user-guide/configuration-workflow.md)
4. [使用配置仓库](user-guide/configuration-library.md)
5. [调用 API Server](user-guide/api-server.md)
6. [查看最终 ModelRequest](user-guide/interception-test.md)
7. [查看日志中心与历史会话](user-guide/runtime-observability.md)
8. [管理数据、文件与系统配置](user-guide/system-management.md)
9. [使用 Docker 部署 Linux/服务器版本](docker.md)
10. [从源码构建 Windows 发行包](building-windows-release.md)
11. [源码运行、Debug、tag 与发布](development-and-release.md)

完整阅读入口：[deepagent-shell 用户指南](user-guide/README.md)。

## 页面说明

- [组件页面](wizard-pages/README.md)
- [Agent 页面](agent-pages/README.md)
- [Deep Agents 升级基线](deep-agents-migration.md)
- [中英术语](agent-pages/terminology.md)
- [安全与部署](security-and-deployment.md)

## 开发与发布

- [源码运行、Debug 与发布流程](development-and-release.md)：滚动 Clone、显式 HMR、验证、版本、tag、
  GitHub Actions 与发布后复验的唯一入口；
- [从源码构建 Windows 发行包](building-windows-release.md)：Windows 自包含 runtime 与 ZIP 的平台细节；
- [Docker 部署](docker.md)：image、Compose、端口和单目录持久化。
