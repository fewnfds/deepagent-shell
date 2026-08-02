# 文件系统

文件系统 block 构造 DeepAgents `CompositeBackend(default=StateBackend(), routes=...)`、
`FilesystemMiddleware` 和请求级 `initial_files`。

## Payload

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

三类路径各最多 100 项，路径最长 4096 字符。提示词和工具 description 覆写最多 100,000
字符。卸载阈值必须是正整数或 `null`；`null` 关闭 DeepAgents 的大工具结果文件卸载。

这里的 100 项只限制配置中填写的来源条目，不限制一个来源目录展开后的文件数量，也不限制文件
内容体积。本版不设置单文件、展开文件数或请求级总字节硬上限。

## 路径语义

- `mapped_directories`：虚拟路径与现有本地绝对目录实时映射；Agent 修改会写入磁盘。
- `virtual_directories`：保存时检查现有本地目录；每次推理请求构造时重新扫描并把文件复制到
  本次请求的内存 state；不复制空目录，后续修改不回写源目录。源目录及其扫描到的所有条目都必须
  是普通目录或普通文件，符号链接、junction 和其他 reparse point 会使本次请求在读取前失败。
- `virtual_files`：每次推理请求复制一个现有本地文件到内存 state；虚拟文件名必须与源文件名
  相同，后续修改不回写源文件。读取使用不跟随链接的安全文件描述符，并要求普通文件。

虚拟目录以 `/` 开头和结尾，虚拟文件以 `/` 开头但不能以 `/` 结尾；不允许 `..`。虚拟路径
按 POSIX 形式归一化。

保存时拒绝重叠映射、重复本地映射、映射与临时目标重叠、重复目标、文件/目录冲突和不存在的
源路径。运行时会再次扫描，因为磁盘可能在保存后变化。冲突直接失败，不定义覆盖顺序。

以下虚拟命名空间保留给 LangChain/DeepAgents 的文件能力、Skill 和 Memory 等上游用途，不能作为
用户映射或临时目标：

```text
/large_tool_results/
/conversation_history/
/skills/
/memory/
/memories/
```

DeepAgent Shell 只在 filesystem 配置入口阻止用户来源误占这些名称；它不提供 Memory 配置，也不创建、
挂载、读取、写入或管理这些上游目录。自定义 Middleware 的内部 backend 和目录生命周期仍由该
Middleware 与 LangChain/DeepAgents 自己负责。

## 工具与提示词

`read_file` 是 DeepAgents 0.7 filesystem 的必需工具，固定可见；`execute` 固定不可见。
`ls`、`write_file`、`edit_file`、`delete`、`glob`、`grep` 可以独立开关，其中具有递归删除能力的
`delete` 默认关闭，其余默认开启。后端保存 contract 和运行时构造期 allowlist 是最终权限边界；
disabled 控件或旧记录中的相反值不会改变 `read_file` / `execute` 的固定状态。

`description_override=null` 表示省略工具说明覆写。`system_prompt_override=null` 表示不向
`FilesystemMiddleware` 传入自定义提示词；DeepAgents 0.7 默认不再额外注入旧的通用 filesystem
使用 prose，工具用途由各自 schema description 说明。这不清空 Primary 的系统提示词、Skill 或 Todo
提示词。页面从服务端管理 catalog 取得与当前锁定依赖一致的默认文本，直接显示并按逐字比较自动保存
`null|string`；浏览器不再保存第二份 DeepAgents 默认快照。
`execute` 的说明覆写也会随完整配置保存，但当前 backend 固定不暴露该工具；修改说明不会启用
命令执行，也不会改变任何运行结果。

`write_file` 用于新建文件或完整替换已有文件，不要求先读；只修改局部内容时使用要求精确匹配的
`edit_file`。`delete` 会永久删除文件，或递归删除目录及其全部内容，无法撤销。显式启用后，它和
write/edit 一样覆盖该 Agent 的普通可写虚拟命名空间：请求级 StateBackend 和 mapped directory；
`/skills/` 整体由消费者独有的只读 backend 接管，任何写、改、删或上传都被拒绝。`delete` 不是只
清理临时文件的开关。

`read_file` 的分页结果会说明总行数、剩余行数和下一次 `offset`。空 `ls` / `glob` 返回
`No files found`；`glob` / `grep` 在超时或达到结果上限时返回已经找到的部分结果和截断说明。
`grep` 默认最多 1,000 个匹配，模型可通过工具参数传入更小或更大的 `max_count`；管理台不再建立
第二个阈值字段。DeepAgent Shell 不解析或转换这些上游工具正文，只把完整 ToolMessage 交给模型和既定
事件投影。当前页面不修改其他工具参数 schema。

filesystem 是可选的项目能力。最终既没有项目 Filesystem 也没有 Skill 时，Shell 不构造自定义 backend
或同名 Middleware，`create_deep_agent()` 会保留默认 StateBackend 和默认文件工具。最终有 Skill
但没有项目 Filesystem 时，后端自动装配消费者独立的空只读 fallback，并只开放 `read_file`；它不
读取或更新请求级 StateBackend，不创建宿主临时目录或持久配置。选择真实 Filesystem 后，StateBackend
与临时文件只活在本次 API 请求；映射目录的磁盘内容按本地文件系统自然持久。

## 请求内共享与资源成本

filesystem 不能被 Subagent 覆写。选择后，一次请求只由根 Primary 读取并创建一份初始临时文件
state，全部同步 Subagent 固定继承当前 Primary 的 filesystem、backend 和这份 state，不会在启动
每个 Subagent 时再次复制初始目录或创建独立映射。这里共享的是普通工作文件；每个消费者的
`/skills/` 只读视图仍按自己的最终 Skill 配置隔离。Primary 未选择项目 Filesystem 时，Subagent 可
正常运行；无 Skill 者保留 Deep Agents 默认 StateBackend 工具，有 Skill 者使用自己的只读 fallback。
顺序调用时，后调用的 Primary/Subagent 可以
看到前序调用者新建、覆盖、修改或删除的临时文件。

并行 Subagent 从同一父状态快照开始；不同路径的更新由现有 state 通道合并，但本版不为同一路径
增加锁或冲突仲裁。不要让并行 Subagent 同时修改同一个临时文件。命中 `mapped_directories` route
的路径始终直接读写磁盘，不属于这份内存临时文件。

每个新的 `/v1/chat/completions` 请求都会重新构造 Agent，并重新从磁盘完整读取配置的临时来源；
上一请求在内存中创建的文件不会恢复。读取不是流式，二进制内容还会编码为 Base64，通常比原始
字节再大约三分之一。由于本版没有文件体积或展开数量硬上限，请谨慎选择目录，避免媒体文件、
依赖缓存、构建产物和大型工程；即使多数文档目录只有几十 MB，重复请求仍会反复承担读取时间与
内存成本。
