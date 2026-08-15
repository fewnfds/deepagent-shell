# 分数阈值条件路由模板

这是一个不依赖任何额外 Python 库的 Condition Router 模板。它读取
`state["shared_vars"]` 中的一个分数字段，并根据阈值激活匹配分支或兜底分支。

## 文件

- `template.json`：声明模板身份和组件页面显示的配置输入。
- `main.py`：提供同步工厂 `create_router(config)`，返回异步路由函数。
- `requirements.txt`：默认内容为空，因此不会引入额外依赖；需要第三方库时再逐行填写。

## 安装模板

把整个 `rule-based-router` 文件夹复制到当前实例 data root：

```text
data/templates/workflow/condition_router/rule-based-router/
```

也可以在【系统 / 文件管理】的 Python templates scope 中建立同样的目录和文件。
模板是静态资源；只有从模板保存组件配置后生成的 Python 扩展才会参与运行和依赖准备。

## 创建配置

1. 打开 Workflow 组件中的 Condition Router 页面，新建配置并刷新模板目录。
2. 选择“分数阈值条件路由”。
3. 填写配置名称，并按需要修改 State 变量名、阈值和两个分支 key。
4. 保存配置。首次保存会为该配置复制一份独立的 Python 扩展，后续修改不会影响本模板。

默认配置读取：

```python
state["shared_vars"]["score"]
```

当分数大于或等于 `60` 时返回 `matched`，否则返回 `otherwise`。分数缺失、不是数字或是布尔值时也使用
`otherwise`。

## 连接 Workflow

1. 在 Workflow 画布中加入 Condition Router Node，并引用刚保存的配置。
2. 从该节点建立两条 Branch Edge。
3. 一条 Edge 的 branch key 填 `matched`，另一条填 `otherwise`。
4. 上游节点需要在进入路由前把分数写入 `shared_vars.score`，或者把组件配置中的 State 变量名改成实际字段。

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

- 在 `template.json` 的 `config_schema.properties` 中增加或修改前端配置字段。
- 在 `main.py` 标有“在这里填写自己的条件判断”的位置编写判断。
- 返回的 branch key 必须与画布 Edge 完全一致；未知、重复或未连接的 key 会使本次 Workflow 失败。
- `state` 是完整 Workflow State 的副本，`context` 是完整 Workflow Runtime Context 的副本。
- 保存配置后，可以继续在组件页面编辑 `main.py`，也可以直接编辑该配置的扩展代码目录。
