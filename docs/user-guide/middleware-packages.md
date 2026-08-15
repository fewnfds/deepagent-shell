# 文件化 Python 扩展

Agent Shell 的文件化 Python 扩展分为扩展模板、配置扩展和组件配置三层：

- 静态模板是 `data/templates/` 下的公共代码资源，只用于创建配置；
- 保存新配置时，系统把所选模板复制成由该配置独占的 Python 扩展；
- 配置扩展位于 `data/config/python_package_instances/`，复制完成后与原模板彻底解耦；
- 组件 YAML 只保存扩展代码目录引用和管理台显示的有序相对文件路径。

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
        <configuration-uuid>/
      agent-middleware/
        <configuration-uuid>/
```

模板至少包含 `main.py`，可以包含 `requirements.txt`、本地模块、实体第三方包和测试。模板目录名是小写
`template-key`；模板没有 package UUID，也不属于任何配置。

配置扩展至少包含 `package.json` 和 `main.py`。文件夹名就是拥有它的组件配置 UUID，`package.json.id` 必须等于该 UUID。
系统据此拒绝配置引用其他配置的扩展代码目录，也避免模板名和额外 UUID 增加 Windows 路径长度。

## Manifest

模板没有 manifest；所属目录类别决定 `family` 和 `adapter`。保存新配置时，系统生成实例自己的 `package.json`：

```json
{
  "format_version": 1,
  "family": "workflow-node",
  "adapter": "condition-router",
  "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
}
```

`package.json` 由 Agent Shell 管理，不能列入前端可编辑文件。它只承担配置 UUID 与 adapter 身份校验。

## 配置引用

Condition Router 和 Custom Middleware 使用同一 YAML 外壳：

```yaml
python_package:
  folder: aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
  editable_files:
    - main.py
    - helpers/rules.py
```

YAML 不保存源码、requirements、manifest 投影、模板引用、revision 或绝对路径。复制组件配置时会复制一份新的配置扩展；删除组件
配置时会删除其扩展代码目录。

新配置编辑器读取对应类别的模板目录。用户可以选择模板，或【套用空模板】得到空的 `main.py` 草稿；最终保存时仍必须补全
对应 adapter 要求的有效工厂。用户可以在两行高的文件清单中逐行增加
包内相对路径，编辑器按该顺序显示文本文件内容；
首次保存才创建配置扩展。已有配置每次打开都从自己的扩展代码目录读取文件，保存时只能更新原目录，不能改指向另一模板或配置扩展。
不存在的相对路径显示非阻塞警告；填写内容后保存会创建文件，保持空内容则继续缺失。未列出的文件保持原样。
绝对路径、`..`、反斜杠路径、重复路径和 `package.json` 会被拒绝。文件保存使用 revision，若目录已被外部修改，必须重新载入后再保存。

## Condition Router

Router 使用 `family: workflow-node`、`adapter: condition-router`。同步工厂返回固定签名的 async callable：

```python
def create_router():
    threshold = 80

    async def route(state, context):
        risk = state.get("shared_vars", {}).get("risk", 0)
        branch = "review" if risk >= threshold else "otherwise"
        return {"activate": [branch], "update": {}}

    return route
```

`route(state, context)` 返回 `activate` 和 `update`。画布 compiler 将结果映射为 LangGraph `Command`；包不接触 Node ID，
也不直接返回 `Command`。

## Custom Middleware

Middleware 使用 `family: middleware`、`adapter: agent-middleware`。每个配置的工厂只返回一个官方 `AgentMiddleware`：

```python
from langchain.agents.middleware import ModelCallLimitMiddleware


def create_middleware(agent):
    return ModelCallLimitMiddleware(run_limit=20)
```

`agent` 是 Agent Shell 提供的身份字典，只包含 `id`、`type`、`name` 和 `package_id`，不是 LangChain Agent 对象。
Main Agent/Subagent 的有序 `middleware_refs` 决定多个实例进入列表的顺序。一个实例可以实现多个官方 hook，但 hook 不作为独立
排序项。LangChain 对 `before_*` 正序执行、对 `after_*` 逆序执行，并把 `wrap_*` 按列表嵌套。Agent Shell 不代理官方
hook、state schema、tools 或 stream transformer。运行链使用
异步执行；自定义类覆盖同步 hook 时也必须提供对应 async hook。

## Imports 与依赖

Python 名称仍需显式 `import`。本地模块使用正常相对导入，例如 `from .helpers import build_route`。非核心直接依赖逐行写入配置扩展
的可选 `requirements.txt`。

启动器只从启用 Workflow 可达的 Condition Router、Main Agent 和其 Subagent 引用中收集配置扩展 requirements。静态模板和
未被运行配置触达的扩展不进入依赖指纹，也不影响全局依赖。依赖层生成在
`runtime/python_packages/site-packages/`；requirements 修改后重启生效，Python 源码在下一次请求重新加载。

依赖只接受普通 PyPI requirement、与核心约束兼容且提供 Windows wheel 的版本，不接受 URL、本地路径、`.pth` 或只有源码
发行包的依赖。

## 安全

配置扩展是受信任的任意代码，以 Agent Shell 服务进程权限运行，不是 sandbox。不要在模板、配置扩展或 manifest 中
保存 secret。请求级模块使用独立命名空间加载，并在请求结束时从模块缓存清理。
