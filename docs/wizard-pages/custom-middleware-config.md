# 自定义 Middleware

一个 block 保存最多 100 条有序 Python 构造配方：

```json
{
  "name": "可靠性中间件",
  "middlewares": [
    {
      "name": "工具重试",
      "enabled": true,
      "source": "from langchain.agents.middleware import ToolRetryMiddleware\n\nmiddleware = ToolRetryMiddleware(max_retries=3)"
    }
  ]
}
```

`source` 是作者原生 Python 用法，不是 deepagent-shell 自定义 JSON 参数规范。它可以 import 已安装
包并构造对象，最终必须在模块顶层绑定 `middleware`。单段最多 100,000 字符。

## 模板与发现

`data/resources/custom_middlewares/*.py` 是用户维护的可复制模板，不是生态插件安装目录。页面也能
创建空白项并粘贴第三方文档中的构造代码。目录扫描只做 UTF-8 读取、AST 语法、顶层绑定和
docstring 首行提取，不 import/exec。页面不执行 pip/uv；依赖由维护者在 `server/` 安装。

## Runtime

只有 Agent 明确选择该 block 后，runtime 才按保存顺序执行 enabled 源码。每条使用独立
namespace；顶层 `middleware` 可以是一个 `AgentMiddleware` 或有序 list/tuple，随后展平并
校验。disabled 项和空数组是 no-op。

构造、缺依赖或类型错误在 Provider 前失败且不返回 traceback。源码进入普通配置 JSON，禁止
在其中保存 secret。Subagent 对整份 block 使用 inherit/replace/disabled。

页面项目的 `name` 只用于显示，不等于 LangChain 对象最终的 `.name`。每个 Primary 和每个
Subagent 的最终 Middleware 栈都要求运行名称唯一；物化后若重名，请求会在 Provider 前返回
`agent_middleware_name_conflict`，并指出冲突属于哪个 Agent 和哪个运行名。项目不会替用户自动
改名；应修改自定义类的官方命名方式、换用不同 Middleware，或删除重复项。
