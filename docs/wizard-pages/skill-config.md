# Skill

页面扫描 `data/resources/skills/` 的一级目录。每个 Skill 必须包含 UTF-8 `SKILL.md`，frontmatter 至少有
与目录名相同的 `name` 和非空 `description`。发现阶段只读取 frontmatter，不执行正文或脚本。

```json
{
  "name": "写作技能",
  "skills": ["outline", "continuity-check"],
  "system_prompt_enabled": true,
  "instruction_override": null
}
```

组件至少选择一个 Skill，最多 200 个。启用系统提示时，`null` 使用 Deep Agents 默认 Skill 提示；
非空覆写必须保留 `{skills_locations}`、`{skills_load_warnings}` 和 `{skills_list}`。关闭系统提示时
`instruction_override` 必须为 `null`，但选中的 Skill 和读取能力仍然存在。

每个 Agent 只看到自己最终选择的 `/skills/` 目录；该 namespace 只读，未选择的 Skill 返回 not found。
Subagent 可以继承、替换或关闭 Skill。资源文件不进入数据库快照，真实请求会重新校验当前磁盘内容。
