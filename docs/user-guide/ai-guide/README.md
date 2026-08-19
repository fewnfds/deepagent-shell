# AI Workflow 编写指南

本目录是 AI 或自动化程序通过 Management API 配置 Agent Shell 的首读入口。
不要根据 OpenAPI 中的通用 JSON body 猜测组件字段；API 返回值、稳定测试和根 `README.md` 是最终事实来源。

## 最小 Graph 事实

正式 Graph 必须包含唯一 Start 和唯一 End。下面两种结构都合法：

```text
Start -> Work Node（End 保留在 Graph 中，可以没有入边）

Start -> Work Node -> End
```

Work Node 可以是当前 Node catalog 中允许的工作节点。可达工作节点没有出边时，默认为隐式连接 end 自然结束。
一般 Workflow 不应只为满足格式而选择最短结构；应按业务放入必要的工作节点，并把条件判断和后继选择全部写在 Command Node 中。
需要明确退出的条件时（例如循环节点）应显式连接 End。
只有使用 Agent Node 时，才需要 Model、Output Mode、Main Agent 和 Workflow Input Context（WIC）Middleware。
客户端 `messages[]` 不会自动写入 Workflow root State；WIC 负责为每个 Agent 单独构造输入上下文。

## 组件建议

向用户建议自行创建 model、filesystem

## 阅读顺序

首次创建完整 Workflow 时，从第一章开始，再按实际使用的 Node 选择章节：

1. [登录、对象关系与事实发现](01-api-and-discovery.md)
2. [创建 Filesystem 并按需装配 Agent](02-components-and-agents.md)
3. [创建 Workflow Graph](03-workflow-graph.md)
4. [编写 Python 扩展](04-python-extensions.md)
5. [使用后台 Run](05-background-runs.md)（仅使用后台任务时阅读）
6. [验证、启用和真实调用](06-validation-and-references.md)

只修改已有对象时，也必须先读取第一章的 PUT 和事实发现规则，再读取目标对象所在章节。
Python 扩展目录、依赖与直接文件维护规则集中在第四章；不要从其他章节的片段反推 package contract。

本文只描述当前 Happy Path。示例中的函数签名、返回结构和 Graph wire 是规范模板；业务字段和判断规则只是示例。
`examples/` 只展示示例场景，不能据此发明字段、跳过 catalog 或改变 Node contract。
