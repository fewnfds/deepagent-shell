# 自定义 Middleware

自定义 Middleware 组件保存最多 100 个有序包引用：

```json
{
  "name": "Request Middleware",
  "middlewares": [{
    "package_id": "request-context",
    "enabled": true,
    "config": {}
  }]
}
```

每个 `package_id` 指向 `data/resources/custom_middlewares/<package-id>/` 下的一个 Middleware 包。启用项按保存顺序
装配，`config` 必须满足包清单声明的 Schema；禁用项不导入、不执行。

包结构、`middleware.json`、`create_middleware(config, agent)` 入口、依赖与安全边界见
[自定义 Middleware 包](../user-guide/middleware-packages.md)。包代码会在真实请求中执行，不要写入 secret。
Subagent 可继承、替换或关闭整份组件。
