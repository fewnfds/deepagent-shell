# 文件化 Python 扩展

Agent Shell 的文件化 Python 扩展分为模板、私有包和组件配置三层：

- 静态模板是 `data/templates/` 下的公共代码资源，只用于创建配置；
- 保存新配置时，系统把所选模板复制成该配置独占的私有包；
- 私有包位于 `data/config/python_package_instances/`，复制完成后与原模板彻底解耦；
- 组件 YAML 只保存私有包文件夹引用和满足 Schema 的普通 `config`。

模板不会被导入、执行或收集依赖。修改或删除模板不会影响已经保存的配置，也没有模板继承、同步或升级关系。
源码不附带实例模板，也不会在启动时自动播种。管理员通过【系统 / 文件管理】的 Python templates scope，或直接在
`data/templates/` 对应类别下创建第一个模板；模板目录为空是合法状态。

## 目录类别

```text
data/
  templates/
    workflow/condition_router/<template-key>/
    agent/custom_middleware/<template-key>/
  config/
    components/<type>/<configuration-uuid>.yaml
    python_package_instances/
      condition-router/
        <configuration-uuid>--<template-slug>--<instance-uuid>/
      agent-middleware/
        <configuration-uuid>--<template-slug>--<instance-uuid>/
```

模板至少包含 `template.json` 和 `main.py`，可以包含 `requirements.txt`、本地模块、实体第三方包和测试。模板目录名是小写
`template-key`；模板没有 package UUID，也不属于任何配置。

私有包至少包含 `package.json` 和 `main.py`。文件夹首段必须是拥有它的组件配置 UUID，末段是该私有包的 UUID；
`package.json.id` 必须等于末段 UUID。系统据此拒绝配置引用其他配置的私有包。

## Manifest

模板使用没有 `id` 的 `template.json`：

```json
{
  "format_version": 1,
  "family": "workflow-node",
  "adapter": "condition-router",
  "name": "Risk router",
  "description": "Route high-risk work for review.",
  "config_schema": {
    "type": "object",
    "properties": {
      "threshold": {
        "type": "integer",
        "title": "Threshold",
        "default": 80,
        "minimum": 0,
        "maximum": 100
      }
    },
    "required": ["threshold"],
    "additionalProperties": false
  }
}
```

保存新配置时，系统从该文件生成带新 `id` 的 `package.json`，删除副本中的 `template.json`，并保留模板的其他文件。
`config_schema` 只支持管理台能机械渲染的扁平字符串、整数、数字、布尔和枚举。

## 配置引用

Condition Router 和 Custom Middleware 使用同一 YAML 外壳：

```yaml
python_package:
  folder: aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa--risk-router--bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb
  config:
    threshold: 80
```

YAML 不保存源码、requirements、manifest 投影、模板引用、revision 或绝对路径。复制组件配置时会复制一份新的私有包；删除组件
配置时会删除其私有包。

新配置编辑器自动读取对应类别的模板目录。选择模板后可编辑完整 `main.py`、`requirements.txt` 和 Schema 生成的输入框；
首次保存才创建私有包。已有配置每次打开都从自己的私有包读取文件，保存时只能更新原文件夹，不能改指向另一模板或私有包。
Schema 输入只修改 YAML 的 `python_package.config`，不会改写包文件。

当前编辑器只直接维护 `main.py` 和 `requirements.txt`。私有包中的额外模块、vendor 目录和其他文件保持原样，用户可在文件夹中
直接维护；前端不解析或管理这些额外文件。文件保存使用 revision，若目录已被外部修改，必须重新载入后再保存。

## Condition Router

Router 使用 `family: workflow-node`、`adapter: condition-router`。同步工厂返回固定签名的 async callable：

```python
def create_router(config):
    threshold = config["threshold"]

    async def route(state, context):
        risk = state.get("shared_vars", {}).get("risk", 0)
        branch = "review" if risk >= threshold else "otherwise"
        return {"activate": [branch], "update": {}}

    return route
```

`route(state, context)` 返回 `activate` 和 `update`。画布 compiler 将结果映射为 LangGraph `Command`；包不接触 Node ID，
也不直接返回 `Command`。

## Custom Middleware

Middleware 使用 `family: middleware`、`adapter: agent-middleware`。工厂返回官方 `AgentMiddleware` 或非空
`list`/`tuple`：

```python
from langchain.agents.middleware import ModelCallLimitMiddleware


def create_middleware(config, agent):
    return ModelCallLimitMiddleware(run_limit=config["limit"])
```

`agent` 是 Agent Shell 提供的身份字典，只包含 `id`、`type`、`name` 和 `package_id`，不是 LangChain Agent 对象。
返回值直接进入 Agent 的 middleware 列表。Agent Shell 不代理官方 hook、state schema、tools 或 stream transformer。运行链使用
异步执行；自定义类覆盖同步 hook 时也必须提供对应 async hook。

## Imports 与依赖

Python 名称仍需显式 `import`。本地模块使用正常相对导入，例如 `from .helpers import build_route`。非核心直接依赖逐行写入私有包
的可选 `requirements.txt`。

启动器只从启用 Workflow 可达的 Condition Router、Main Agent 和其 Subagent 引用中收集私有包 requirements。静态模板和
未被运行配置触达的私有包不进入依赖指纹，也不影响全局依赖。依赖层生成在
`runtime/python_packages/site-packages/`；requirements 修改后重启生效，Python 源码在下一次请求重新加载。

依赖只接受普通 PyPI requirement、与核心约束兼容且提供 Windows wheel 的版本，不接受 URL、本地路径、`.pth` 或只有源码
发行包的依赖。

## 安全

私有包是受信任的任意代码，以 Agent Shell 服务进程权限运行，不是 sandbox。不要在模板、私有包、manifest 或普通 config 中
保存 secret。请求级模块使用独立命名空间加载，并在请求结束时从模块缓存清理。
