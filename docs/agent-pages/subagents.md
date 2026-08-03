# Subagent

本页保存可复用策略。策略不绑定某个 Primary，只有被当前 Primary 的 binding 选中后才会应用：

```json
{
  "name": "read-only researcher",
  "capability_overrides": [
    {"type": "custom-tool", "mode": "disabled", "block_id": ""},
    {"type": "system-prompt", "mode": "replace", "block_id": "UUID"}
  ],
  "subagents": []
}
```

## 模式

- 某类型未出现：`inherit`；
- `replace`：必须引用同类型现有 block；
- `disabled`：必须没有 `block_id`。

model 允许 inherit/replace，但不能 disabled。system-prompt、todo-list、custom-tool、skill、
custom-middleware、exception-retry 和 prompt-preset 支持三种模式。filesystem 不出现在覆写策略中；
一次请求的 Primary 与全部同步 Subagent 固定使用同一个 workspace。output-mode 和 subagent 不由
Deep Agents Subagent 覆写，按 manifest 策略移除。

`subagents[]` 是该 Subagent 自己的命名 child catalog，字段与 Primary binding 相同。列表为空表示没有
`task`；可以引用任意已保存覆写，也可以引用当前覆写自身。平台不增加 inherit/custom/none 模式：每条
binding 的目标、名称和说明就是完整配置。名称只要求在当前 catalog 内唯一；不同 Primary/Subagent 的
catalog 可以使用相同的模型可见名称，例如都叫 `worker`。

覆写策略只在与 binding 所在的当前 Primary 组合后才有最终含义。model 丢失、引用失效或资源无法
物化仍会由集中装配校验拒绝保存、启动或真实 Agent 构建。

Primary 和所有同步 Subagent 双向共享请求级虚拟文件、初始文件与 mapped routes；child 不清空或重载
`files` state。Skill 仍按每个 Agent 的最终配置独立解析，并通过 consumer-specific 只读 `/skills/`
overlay 只暴露最终选中的目录；未选路径返回 not found。替换或关闭 Skill 不创建第二套普通 workspace，
也不影响 Primary 与 sibling 的 Skill 视图或宣告。

Prompt Preset 是 child 注入冻结客户端消息与 Startup conversation 的唯一门禁。child 最终选择到 Preset
时，LangChain 原生 `before_agent` Middleware 处理本次请求冻结的客户端消息，追加自己的 Startup
conversation，并在末尾保留 Deep Agents 传入的 delegated task；最终没有 Preset 时不装配该 Middleware，
child 只接收 delegated task。Preset 可继承、替换或关闭，不需要包装 `CompiledSubAgent` runnable。

不选择覆写策略只表示能力完整继承，不自动承诺 Prompt Caching。自由装配是基线；缓存对齐只是用户可以
手工构造的理论特殊情况。该特殊情况要求最终 model、system prompt、冻结客户端消息处理结果、按序 tool
schema、response schema 与相关 model settings 均保持一致，并可只用不同 Preset 的 Startup conversation
区分身份；任何自由覆写或上游 `task` schema 差异都可能让前缀提前分叉。是否实际命中缓存由
Provider/model 决定。

若某条 binding 不需要任何显式 replace/disabled，不选择覆写策略即可；binding 的
`subagent_override_id` 保存为空字符串，不需要创建一份空策略。

## 页面

页面与 Primary Agent 使用相同的双列能力选择板和下拉框样式。每个 Subagent 能力在对应的 Primary
选项基础上增加“继承”；选择已有配置表示 replace，可选能力还可选择“关闭”表示 disabled。配置选择
显示名称，payload 仍保存 UUID。页面只提供新建/载入/保存，删除在配置仓库执行。

桌面宽度下，右侧草稿校验区占页面三分之一，显示后端对覆写结构、替换引用和必需能力策略发现的问题；
窄屏下恢复为整行。全部正常时显示通过摘要。
replace 指向旧结构时会写出组件类型、配置名称和原因。保存按钮仍可提交当前草稿，但后端会用同一规则重新校验并
拒绝无效写入，直接 HTTP 请求也不能绕过。覆写策略尚未绑定具体 Primary 时不能独立判断最终 model
与最终装配组合；绑定后由后端把最终问题归到所属 Primary UUID 和 Subagent 名称。

配置仓库中的“复制”只提交源 UUID 和新名称，由 Subagent 覆写专用服务端 endpoint 重新检查当前
结构与 replace 引用、生成新 UUID 并保存。复制不会修改源策略，也不会把任何 Primary binding 自动
改指向副本；缺失源、重复名称或无效历史源都会在写入前失败。
