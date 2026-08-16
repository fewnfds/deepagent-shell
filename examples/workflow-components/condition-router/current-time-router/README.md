# 当前时间条件路由示例

这个 Condition Router 每次运行时读取一次本地当前时间，根据秒的个位数选择一个分支，
并把同一时刻的 ISO 8601 时间写入 `shared_vars.current_time`。

| 秒的个位数 | 激活的 branch key |
| --- | --- |
| `0`-`3` | `first` |
| `4`-`6` | `second` |
| `7`-`9` | `otherwise` |

## 使用

1. 在 Workflow 组件的 Condition Router 页面刷新模板目录。
2. 选择 `内置示例-current-time-router` 并保存配置。
3. 在画布上从 Condition Router 节点连接三条 Branch Edge，branch key 分别填写
   `first`、`second` 和 `otherwise`。

路由结果会更新：

```python
{"shared_vars": {"current_time": "2026-08-16T12:34:56"}}
```

时间使用运行服务所在机器的本地时区；`current_time` 只保留到秒。
