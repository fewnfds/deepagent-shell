# 分数阈值条件路由模板

这是一个不依赖任何额外 Python 库的 Condition Router 模板。它读取
`state["shared_vars"]` 中的一个分数字段，并根据阈值激活匹配分支或兜底分支。

## 文件

- `main.py`：提供同步工厂 `create_router()`，返回异步路由函数；规则参数直接在这里声明。
- `requirements.txt`：默认内容为空，因此不会引入额外依赖；需要第三方库时再逐行填写。

## 使用示例

源码启动时，管理台会自动把本目录发现为 `内置示例-rule-based-router`。不需要复制到 data root；只有从示例保存
组件配置后生成的独立 Python 扩展才会参与运行和依赖准备。如需维护自己的同名模板，仍可在
`data/templates/workflow/condition_router/rule-based-router/` 创建它，两个 catalog 项不会冲突。

## 创建配置

1. 打开 Workflow 组件中的 Condition Router 页面，新建配置并刷新模板目录。
2. 选择 `内置示例-rule-based-router`。
3. 填写配置名称；保存后在组件页面编辑 `main.py` 来修改规则。
4. 保存配置。首次保存会为该配置复制一份独立的 Python 扩展，后续修改不会影响本模板。

默认代码读取：

```python
state["shared_vars"]["score"]
```

当分数大于或等于 `60` 时返回 `matched`，否则返回 `otherwise`。分数缺失、不是数字或是布尔值时也使用
`otherwise`。

## 连接 Workflow

1. 在 Workflow 画布中加入 Condition Router Node，并引用刚保存的配置。
2. 从该节点建立两条 Branch Edge。
3. 一条 Edge 的 branch key 填 `matched`，另一条填 `otherwise`。
4. 上游节点需要在进入路由前把分数写入 `shared_vars.score`，或者直接把 `main.py` 中的 `state_key` 改成实际字段。

路由返回格式固定为：

```python
{
    "activate": ["matched"],
    "update": {},
}
```

`activate` 可以包含多个不同的 branch key，以并行激活多条分支。`update` 可以返回 Workflow State 的局部更新；
不需要更新时使用空字典。不要在模板中直接返回 LangGraph `Command`，Agent Shell 会把路由结果转换为
`Command(update=..., goto=...)`。

## 改成自己的规则

- 在 `main.py` 顶部修改规则参数，或在标有“在这里填写自己的条件判断”的位置编写判断。
- 返回的 branch key 必须与画布 Edge 完全一致；未知、重复或未连接的 key 会使本次 Workflow 失败。
- `state` 是完整 Workflow State 的 detached 可变副本；`runtime` 是 LangGraph 注入的官方 Runtime，身份与 Prepare 从
  `runtime.context` 读取，Lifecycle Store 从 `runtime.store` 读取。
- 保存配置后，可以继续在组件页面编辑 `main.py`，也可以直接编辑该配置的扩展代码目录。
