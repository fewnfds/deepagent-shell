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

一次请求只使用一个普通 Filesystem workspace。集中装配器根据每个 Agent 最终选择的 Skill，为其叠加
consumer-specific 只读 `/skills/` overlay；`SkillsMiddleware.sources`、提示词和 overlay 都只包含该
Agent 自己选择的 Skill，未选路径返回 not found。没有项目 Filesystem 时，普通文件仍使用请求共享的
默认 StateBackend，且模型只获得读取 Skill 所需的 `read_file`，不会为 Skill 创建第二套 workspace。
若想关闭 Skill，应在 Agent 装配中不引用该
block。运行时重新确认每个选中目录位于 skills 根目录，并重新读取当前 `SKILL.md` 的 name/description
结构；文件保存后变为不合规时不会继续使用。验证通过后构造：

```python
SkillsMiddleware(backend=backend, sources=["/skills/outline/"], ...)
```

关闭 Skill 系统提示词只会阻止 Middleware 向模型系统消息追加 Skill 位置和列表。Middleware 仍加载
`skills_metadata`，选中的 Skill 目录和 `read_file` 能力保持可用；它不等于从 Agent 装配中移除 Skill。

每个 Agent 的 SkillsMiddleware 与 FilesystemMiddleware 复用请求级普通 workspace，但用自己的只读
`/skills/` overlay 覆盖该 namespace：只有最终选中的 Skill 可读，未选路径 not found，写、改、删和
上传均拒绝，不能回落到普通请求 state。Skill 的 `allowed-tools` 只是一段能力提示，不自动改变真实
工具列表。

Subagent 可以继承、替换或关闭 Skill。custom Subagent 的最终 Skill 提示和 sources 独立于 Primary 和
sibling，其 `/skills/` overlay 同样相互隔离；这不会分裂普通 workspace，也不会清空或替换父级的普通
虚拟文件 state。

Skill 目录是实时外部资源，不进入请求的数据库配置快照，也不会被复制或锁定。运行中的 Agent
可能在较晚的工具步骤才读取 `SKILL.md` 或配套文件；此时若维护者修改、删除或替换目录，当前
Agent 后续读取就可能看到变化。项目不会为这种资源变化提供一致性保证，使用者应自行安排维护时机。
