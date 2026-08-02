# Skill

## 资源发现

页面扫描 `data/resources/skills/` 的一级目录。有效资源必须包含 UTF-8 大写 `SKILL.md`，其 YAML
frontmatter 必须有 `name` 和 `description`。`name` 为 1–64 个小写字母或数字，可用单个连字符
分隔，不能以连字符开头/结尾或包含连续 `--`，并且必须与目录名相同；小写 Unicode 字母也合法。
`description` 为 1–1024 个字符。扫描只读取 frontmatter，不执行 Skill 正文、脚本或其中的指令；
错误目录通过 catalog 的 `errors` 展示。页面 catalog 只返回并显示目录、`name` 和字符串
`description`；其他 YAML 字段不递归投影，也不进入页面 payload。真正运行时需要的 `license`、
`compatibility`、`metadata` 或 `allowed-tools` 由 DeepAgents 自己读取。

## Payload

```json
{
  "name": "写作技能",
  "skills": ["outline", "continuity-check"],
  "system_prompt_enabled": true,
  "instruction_override": null
}
```

- `skills` 最多 200 项，名称遵守上面的当前 Agent Skills 规则，去重并保序。
- Skill block 至少选择一个 Skill；Agent 引用该 block 即构造 `SkillsMiddleware`。
- `system_prompt_enabled=true` 时使用 DeepAgents 默认提示词或 `instruction_override` 覆写；设为 `false`
  时固定要求 `instruction_override=null`，并向 `SkillsMiddleware` 传入 `system_prompt=None`。
- 页面从服务端管理 catalog 取得当前默认 system prompt；未修改保存 `null`，修改后保存完整文本。
- 覆写最多 100,000 字符，必须保留 `{skills_locations}`、`{skills_load_warnings}`、
  `{skills_list}`。
- 除这三个完整字段外，不允许其他单层花括号字段，也不允许属性/索引、conversion 或 format
  spec。JSON、集合等普通花括号必须写成 `{{` 和 `}}`；服务端在保存和装配前检查，页面只显示
  后端校验报告且不自动改写正文。

## Runtime

集中装配器按每个消费者完成继承、替换、关闭和顶层移除后的最终能力集合决定文件模式：已有真实
Filesystem 时使用共享工作空间；有 Skill 但无真实 Filesystem 时自动使用消费者独立的空只读
fallback；两者都没有时不构造文件能力。该规则不按 Primary、Subagent 或其他 Agent 类型分别写死。
若想关闭 Skill，应在 Agent 装配中不引用该 block。运行时重新确认每个选中目录位于 skills
根目录，并重新读取当前 `SKILL.md` 的 name/description 结构；文件保存后变为不合规时不会继续
使用。验证通过后挂载到 `/skills/{name}/`，再构造：

```python
SkillsMiddleware(backend=backend, sources=["/skills/outline/"], ...)
```

关闭 Skill 系统提示词只会阻止 Middleware 向模型系统消息追加 Skill 位置和列表。Middleware 仍加载
`skills_metadata`，选中的 Skill 目录和 `read_file` 能力保持可用；它不等于从 Agent 装配中移除 Skill。

同一消费者的 SkillsMiddleware 与 FilesystemMiddleware 使用同一个消费者级 backend，顺序为 Skill
在 Filesystem 之前。整个 `/skills/` namespace 由该消费者自己的只读 allowlist 接管：自己的 Skill
可读，未选择的 Skill not found，写、改、删和上传均拒绝，不能回落到共享请求 state。Skill 的
`allowed-tools` 只是一段能力提示，不自动改变真实工具列表。

Subagent 可以继承、替换或关闭 Skill。custom Subagent 的最终 Skill 集合独立于 Primary 和 sibling；
继承同一真实 Filesystem 只表示共享普通工作文件，不会共享彼此的 Skill。没有真实 Filesystem 的
Skill 消费者只看到 `read_file`，其空 fallback 不连接父级或其他消费者的文件 state。

Skill 目录是实时外部资源，不进入请求的数据库配置快照，也不会被复制或锁定。运行中的 Agent
可能在较晚的工具步骤才读取 `SKILL.md` 或配套文件；此时若维护者修改、删除或替换目录，当前
Agent 后续读取就可能看到变化。项目不会为这种资源变化提供一致性保证，使用者应自行安排维护时机。
