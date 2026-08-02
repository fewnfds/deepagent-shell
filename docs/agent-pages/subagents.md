# Subagent

本页保存可复用策略。策略不绑定某个 Primary，只有被当前 Primary 的 binding 选中后才会应用：

```json
{
  "name": "read-only researcher",
  "capability_overrides": [
    {"type": "custom-tool", "mode": "disabled", "block_id": ""},
    {"type": "system-prompt", "mode": "replace", "block_id": "UUID"}
  ]
}
```

## 模式

- 某类型未出现：`inherit`；
- `replace`：必须引用同类型现有 block；
- `disabled`：必须没有 `block_id`。

model 允许 inherit/replace，但不能 disabled。system-prompt、todo-list、custom-tool、skill、
custom-middleware 和 exception-retry 支持三种模式。filesystem 在当前 Primary 选择时固定继承，未选择时保持缺失，且不显示覆写按钮；output-mode、
prompt-preset、subagent 和 worker-delegation 不由 DeepAgents Subagent 覆写，按 manifest 策略移除。

覆写策略只在与 binding 所在的当前 Primary 组合后才有最终含义。最终有 Skill 但没有真实
filesystem 时，该 Subagent 自动得到独立、只读、仅 `read_file` 的空 fallback；不会因此拒绝保存。
model 丢失、引用失效或资源无法物化仍会由集中装配校验拒绝保存、启动或真实 Agent 构建。

多个 Subagent 即使继承同一 filesystem，也只共享普通工作文件。Skill 按每个 Subagent 最终配置
独立解析；替换或关闭 Skill 不影响 Primary 与 sibling，未选择的 `/skills/...` 路径不可见。

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
