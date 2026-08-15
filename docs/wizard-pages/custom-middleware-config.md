# 自定义 Middleware

自定义 Middleware 组件保存最多 100 个有序包引用：

```json
{
  "name": "Request Middleware",
  "python_package_bindings": [{
    "package_id": "11111111-1111-4111-8111-111111111111",
    "enabled": true,
    "config": {}
  }]
}
```

每个 `package_id` 指向 `data/resources/python_packages/<package-uuid>/` 下的一个 `middleware/agent-middleware` 包。启用项按保存顺序
装配，`config` 必须满足包清单声明的 Schema；禁用项不导入、不执行。

包结构、`package.json`、`create_middleware(config, agent)` 入口、依赖与安全边界见
[文件化 Python 扩展包](../user-guide/middleware-packages.md)。包代码会在真实请求中执行，不要写入 secret。
Subagent 可继承、替换或关闭整份组件。
