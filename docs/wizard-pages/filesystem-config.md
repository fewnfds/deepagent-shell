# 文件系统

文件系统组件配置请求级 workspace、宿主目录映射、初始虚拟文件和模型可见文件工具。

```json
{
  "name": "写作工作区",
  "mapped_directories": [
    {"virtual_path": "/output/", "local_path": "H:\\novel\\output"}
  ],
  "virtual_directories": [
    {"virtual_path": "/drafts/", "source_path": "H:\\novel\\drafts"}
  ],
  "virtual_files": [
    {"virtual_path": "/instructions/AGENT.md", "source_path": "H:\\novel\\AGENT.md"}
  ],
  "system_prompt_override": null,
  "tool_token_limit_before_evict": 20000,
  "tool_configs": {
    "ls": {"visible": true, "description_override": null},
    "read_file": {"visible": true, "description_override": null},
    "write_file": {"visible": true, "description_override": null},
    "edit_file": {"visible": true, "description_override": null},
    "delete": {"visible": false, "description_override": null},
    "glob": {"visible": true, "description_override": null},
    "grep": {"visible": true, "description_override": null},
    "execute": {"visible": false, "description_override": null}
  }
}
```

## 两档运行模式

- 未选择项目 Filesystem：使用请求级默认 StateBackend，普通 workspace 初始为空；模型默认获得 `ls`、
  `read_file`、`write_file`、`edit_file`、`glob`、`grep`。
- 选择项目 Filesystem：使用配置的共享 workspace，并按 `tool_configs` 开放 `ls`、`read_file`、
  `write_file`、`edit_file`、`delete`、`glob`、`grep`。`read_file` 固定可见；`execute` 固定不可见；
  `delete` 默认关闭。

同一次请求中的 Primary 与同步 Subagent 共享普通 StateBackend、初始文件和 mapped routes；Subagent settings
不能单独替换文件系统。每个 Agent 的 `/skills/` 仍按最终 Skill 选择建立只读视图。需要让不同 Agent 对共享
workspace 使用不同路径权限、文件工具或文件系统提示词时，另行选择[文件系统权限](filesystem-permissions-config.md)。

## 来源类型

- `mapped_directories`：把虚拟目录实时映射到现有宿主绝对目录；写入直接落盘；
- `virtual_directories`：每次请求开始时把现有目录文件复制到内存 workspace，不回写来源；
- `virtual_files`：每次请求复制一个现有普通文件，不回写来源。

虚拟目录必须以 `/` 开头和结尾；虚拟文件以 `/` 开头且文件名与来源相同。不允许 `..`、重叠 route、
重复目标、文件/目录冲突、符号链接、junction 或其他 reparse point。以下 namespace 保留：
`/large_tool_results/`、`/conversation_history/`、`/skills/`、`/memory/`、`/memories/`。

`system_prompt_override=null` 使用当前 Deep Agents 默认行为；工具 `description_override=null` 保留默认说明。
`tool_token_limit_before_evict` 为正整数或 `null`，`null` 关闭大工具结果卸载。
没有装配文件系统权限时，路径默认可读写，文件系统组件中的提示词和工具配置直接生效。

虚拟来源会在每个新请求中重新完整读取，当前没有单文件、展开文件数或总字节配额。不要选择依赖缓存、
构建产物、媒体目录或其他大型路径。并行 Subagent 不应同时修改同一临时文件。
