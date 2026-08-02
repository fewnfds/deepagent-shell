# 创建组件

【组件】按以下顺序提供十二类配置。保存组件不会自动加入任何 Agent；需要回到【Agent / Primary Agent】
明确选择。

左侧导航中的组件子项和页面标题下方的快速切换按钮都由后端 capability manifest 按顺序生成，不维护
另一份固定页面清单。桌面宽度下，页面左侧三分之二用于配置，右侧三分之一显示草稿报警；窄屏恢复
单列。配置区不再使用一个无语义的大 Card 包住编辑器内部的字段分组。

## 1. 模型

Provider 位于编辑器顶部；当前版本内置 OpenAI、Anthropic、Google Vertex AI、Google GenAI、
DeepSeek 和 xAI 的官方 LangChain integration。选择后显示该 Provider 的原生参数组，切换 Provider
会清空这组参数。字段按原名保存到 `provider_settings` 并直接传给 LangChain，不做跨 Provider 映射。

Provider 包只随 DeepAgent Shell 发行版统一安装和升级，管理台不提供安装入口。连接保存 Base URL、模型
名称和 write-only Key；只有 Provider 与 Base URL 都未改变时，Key 输入留空才会保持已有值。Vertex AI
使用 Application Default Credentials，不接受普通 Key。其他 Provider 不探测宿主模型 Key 环境变量。

【获取模型】只用于兼容 `${base_url}/models` + Bearer Key 的目录 wire；原生服务不支持时直接填写模型
ID。目录请求与 OpenAI-compatible LangChain Provider 的普通/流式模型调用共享内置 curl transport，
避免“目录可用但 Agent 使用另一套 HTTP 实现”的差异。普通响应只显示凭据为 `masked` 或 `missing`。
完整字段见[模型](../wizard-pages/model-config.md)。

## 2. 系统提示词

保存非空 `system_prompt`。Primary 选择后，正文传给
`create_deep_agent(system_prompt=...)`。

## 3. 文件系统

可配置：

- 磁盘映射：Agent 对虚拟目录的读写直接作用于本地目录；
- 请求级临时目录：每次推理请求开始时把目录内容复制到内存 state 文件空间；
- 请求级临时文件：每次推理请求复制单个文件，虚拟文件名必须与源文件名相同。

`read_file` 固定对模型可见，`execute` 固定关闭。页面可以开关
`ls`、`write_file`、`edit_file`、`delete`、`glob`、`grep`；递归删除工具 `delete` 默认关闭，
显式开启后会作用于该 Agent 的普通可写虚拟命名空间，包括请求级工作文件和实时磁盘映射；
`/skills/` 始终是消费者独有的只读命名空间，不受这些写工具开关影响。删除操作无法撤销。
`write_file` 会新建或完整覆盖文件；局部修改使用 `edit_file`。

页面还提供 filesystem 自定义 system prompt、工具说明和大结果卸载阈值。DeepAgents 0.7 默认不再
注入旧的通用 filesystem 工具使用 prose；默认空白只表示没有这段附加 prose，不影响 Primary 系统
提示词、Skill 或 Todo。`execute` 的说明覆写会随完整配置保存，但不会启用命令执行。

默认文字直接显示在编辑框；未修改就保存 `null` 并沿用上游默认，修改后保存完整覆写。
真实请求重新检查路径，并构造 DeepAgents backend、Middleware 与请求级初始文件。
分页读取会返回总行数、剩余行数和下一 offset；空文件查询返回 `No files found`。glob/grep 大结果
可能只返回有效的部分结果与截断提示，grep 默认上限是 1,000 个匹配。产品不解析这些工具正文。

文件系统是可选能力。最终既没有 Filesystem 也没有 Skill 时，不构造 `FilesystemMiddleware`，
Primary 与同步 Subagent 都没有文件工具。最终有 Skill、但没有有效 Filesystem 时，后端自动为该
消费者装配独立的空只读空间，只暴露 `read_file`，用于按需读取该消费者自己的 Skill；它不连接
Primary 或 sibling 的请求级 `files` state，不创建持久 block，也不提供写、搜索、执行或宿主目录。

选择 filesystem 后，同一请求中的 Primary 与全部同步 Subagent 固定继承同一配置，并共享这份临时
文件 state；顺序委派时，后调用者能看到前面新建或修改的临时文件。请求结束后临时文件丢弃，下一次
请求会从配置的磁盘来源重新完整复制。临时文件不设内容体积或展开文件数上限，读取会一次性完成：
大目录、大文件和二进制 Base64 会明显增加启动时间与内存，请避免选择媒体、缓存或大型工程目录。
并行 Subagent 会从同一快照开始，适合修改不同路径；不要安排它们同时写同一个临时文件。

## 4. 待办计划

选择后构造 LangChain `TodoListMiddleware`，向该 Agent 提供 `write_todos` 和独立 `todos`
state。页面允许完整覆写 system prompt 与工具 description；未修改时保存 `null`。

Primary 和 Subagent 都能装配。每个 Agent 的 Todo state 独立，且只活在当前 API 请求中；
没有服务端跨请求计划记忆。

## 5. 自定义工具

页面静态扫描 `data/resources/custom_tools/*.py`，只保存选中的资源名称。扫描不 import/exec；
非法资源名、缺少参数类型/显式 `args_schema`、缺少 docstring/显式 description 等可静态确定的
问题显示在逐文件错误区，不进入选择列表。真实请求只有在选中该 block 后才重新扫描并 import
当前文件，并要求导出对象是 LangChain `BaseTool`。数据库不保存或比较源码 hash；保存后修改会
在下一次请求生效。

文件资源名不等于最终 Tool 名。后端保存、仓库与启动规则只使用 AST 能确定的函数默认名或
`@tool("字面量名称")` 检查静态冲突；动态表达式名称、文件缺失、import 失败、对象类型不对或最终
模型可见工具名冲突会在真实请求访问 Provider 前失败，并返回标明 Primary/Subagent 所属对象的
安全配置错误；不会回显源码、宿主路径或 traceback。

## 6. Skill

扫描 `data/resources/skills/` 一级子目录。有效目录包含大写 `SKILL.md`；frontmatter `name` 遵守
1–64 字符、小写字母/数字和单个连字符规则并匹配目录，`description` 必填且最多 1024 字符。
选择 Skill block 时，runtime 会重新校验当前 frontmatter，再将该消费者选中的目录挂载到其独有、
只读的 `/skills/{name}/` 视图并构造 `SkillsMiddleware`。若最终没有真实 Filesystem，装配器自动增加
只含 `read_file` 的独立空 fallback；无需为此额外创建 Filesystem 配置。

Primary 与每个 custom Subagent 的 Skill 集合按各自最终配置独立解析。继承同一 Filesystem 只共享
普通工作文件，不会让 sibling 看到彼此的 Skill；未选择的 `/skills/...` 路径返回 not found，不能
回落到共享请求 state，Skill 文件也不能通过 filesystem 写、改、删或上传。

Skill 配置至少选择一个 Skill；Agent 不需要 Skill 时，在装配页不引用该 block。配置可以关闭 Skill 系统
提示词，此时仍加载 Skill 元数据并保留所选目录的只读访问，只是不向模型的系统消息追加 Skill 位置和列表。
启用时，自定义 Skill 提示词必须保留 `{skills_locations}`、`{skills_load_warnings}`、`{skills_list}`，不得
使用其他单层花括号字段；普通花括号用 `{{`、`}}` 转义。

## 7. 自定义 Middleware

一个配置保存有序 Python 构造配方。每项可单独启停；源码最终必须把单个 LangChain
Middleware 或有序序列绑定到模块级 `middleware`。

`data/resources/custom_middlewares/` 是用户维护的可复制模板目录，第三方作者无需适配额外插件规范。
配置扫描和保存只做 AST/语法检查；真实请求只执行 enabled 配方。所需第三方包由维护者在
`server/` 自行安装，页面不运行 pip/uv，也不要在源码中写凭据。

物化后的最终 `.name` 在每个 Primary/Subagent Middleware 栈内必须唯一；冲突会在 Provider 前
返回 `agent_middleware_name_conflict` 并指出所属 Agent 与运行名，不会自动重命名。每个请求只执行
当前 Agent owner 的 enabled 配方一次；未选择配置和 disabled 配方不会执行。

## 8. 输出模式

把 LangChain v3 事件归一化为八类语义事件，再按事件开关、字段精确匹配条件和单一模板生成用户字符串。
Primary 的 text/reasoning 在模板和过滤结果可于首字节前确定时按 block start/delta/finish 真流式；
其他配置等待完整 block。工具结果仍只使用 `tool-finished`。`message-finish` 保存逐次模型 usage、
response metadata 和真实 finish reason，不重复正文。

流式响应按 v3 到达顺序写入 `delta.content`，非流式消费同一序列，因此两种传输完成后
正文逐字一致。完整工具调用在当前模型周期内等待匹配结果，并按 `tool_call_id` 成对相邻输出；缺少结果
时在下一模型周期或请求结束前单独输出。一个模型消息可以包含多个 finished block，全部按 finish 到达
顺序保留；Subagent 内部模型正文不公开，其最终回答通过完整工具结果返回。

过滤条件支持 `事件类型.字段 → 值` 和不限定事件类型的 `字段 → 值`，多条按任一命中处理。
变量可选择 HTML 转义或原样文本；HTML 转义只处理填入模板的变量值，不改变模板本身。新建配置
默认使用原样文本并开启全部八类事件：模型回答仍只输出 `{{message}}`，其余事件提供可折叠参考模板，
正文与元数据之间保留一个空行。

输出模式与模型同为 Primary 必选能力；页面不能清除，管理 API 也拒绝缺失配置。
流式、非流式和 Provider 前拦截测试都使用所选模式，不存在隐藏的默认文本投影。
配置仓库会标出不符合当前八类 `enabled + template` 结构的持久记录，并保留完整原始 JSON。记录可
载入编辑器修复；草稿只保留当前 catalog 的事件和类型正确的字段，其余使用当前默认。只有明确保存
才覆盖成新结构，复制和运行不会自动补齐。

## 9. 异常重试

可选的模型调用韧性组件。它在 Provider 原生重试与 LangChain 官方 ModelRetryMiddleware 之间选择唯一
retry owner，并可强制完整、非流式模型响应；不改变 tool choice、response format、并行工具调用或 Agent
终止。完整字段见
[异常重试](../wizard-pages/exception-retry-config.md)。

## 10. 提示词预设

在对应 Agent graph 启动前，对冻结客户端消息副本执行一次可选的字面量标签替换，然后按顺序追加
`user`/`assistant` 启动消息。只扫描原始客户端 user 字符串正文；未命中不处理，空 replacement 删除
标签，同一标签多次出现会在 Provider 前拒绝。替换结果与后续 Agent 消息不会再次扫描。

Primary 与每次 Context Worker 调用分别选择自己的 Preset；框架不内置业务标签、角色或协作流程。
DeepAgents Subagent 不经过该输入预处理。完整字段见
[提示词预设](../wizard-pages/prompt-preset-config.md)。

## 11. 同步子代理（Synchronous Subagents）

保存同步 `SubAgentMiddleware` 的附加系统说明和 task 工具说明。DeepAgents 0.7 默认不额外注入
旧的长篇 task system prose，只保留精简的 task 工具 description；填写非空 override 才加入自定义
附加说明。Primary 引用该 block 即启用同步
委派；具体 Subagent 绑定在 Primary 页面维护。引用后，真实请求中必须至少有一条完整且已启用的
binding，否则构建失败。

当前只支持 raw synchronous Subagent；不包含异步、dynamic 或递归委派。

## 12. Context Worker 委派

向 Primary 提供 `run_worker(worker, task)` 标准 LangChain Tool。具体 Worker 在 Primary 页面绑定，
装配内容在独立 Worker Profile 页面设置。一个模型响应可以发出多个 Tool Call，由 LangChain ToolNode
并行执行；结果分别作为 ToolMessage 返回 Primary。Worker 当前是完整 `create_agent()` graph，使用冻结
客户端消息副本和自己的 Prompt Preset，不继承 Primary 的 AI/Tool 过程。

Context Worker 的 Deep Agents 迁移在本阶段暂停；未来是否由带 message adapter 的同步 Subagent 取代，另行决定。

本组件与 DeepAgents 同步 Subagent 并列，不侵入其配置或运行。完整字段见
[Context Worker 委派](../wizard-pages/worker-delegation-config.md)。
