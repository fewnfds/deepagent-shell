# 装配 Primary、Subagent 与 Context Worker

## Primary

在【Agent / Primary Agent】选择已有配置或填写新名称，然后按顺序选择：模型、系统提示词、文件系统、
待办计划、自定义工具、Skill、自定义 Middleware、输出模式、异常重试、提示词预设、Subagent 和
Context Worker 委派。

模型和输出模式是必选项，缺少任一项时右侧草稿校验区会显示问题，服务端保存会拒绝；
文件系统及其他能力最多各选择一份，不选择就不装配。委派区域分别保存 `subagents[]` 与 `workers[]`。
每条 Subagent binding 固定以
当前 Primary 为基础，只保存可选的覆写策略 UUID，不复制被引用 payload。

保存后的 Primary 在 API Server 通过静态门禁并处于 running 时作为 `/v1/models` 中的 model
发布；页面本身没有单独“运行”按钮。

## Subagent 策略

【Agent / Subagent】保存可复用的 `capability_overrides[]`：

- 继承：不保存显式项，沿用当前 Primary 的同类引用；
- 替换：保存同类型 block UUID；
- 关闭：最终移除该能力。

model 只能继承或替换。项目 filesystem 在当前 Primary 选择时固定继承；未选择项目 Filesystem 时，Subagent
仍使用 Deep Agents 默认 StateBackend 文件工具；
output mode、提示词预设、Subagent 和 Context Worker 委派按 manifest 策略从 Subagent 移除，不提供覆写选项。

## 绑定

Primary 的每条 binding 添加后立即启用，并需要：

- 在该 Primary 内唯一、符合标识符规则的名称；
- 面向父 Agent 的用途说明；
- 可选的 Subagent 覆写策略；不选择表示完整继承当前 Primary。

真实请求按“当前 Primary + 可选覆写 - 顶层专属能力”构造同步 Subagent。当前 Primary 的自身
bindings 不会继续解析，因此不会递归委派。binding 不保存其他 Primary ID；完整继承时只把
`subagent_override_id` 留空，也不要求创建空覆写配置。

## Context Worker Profile 与绑定

【Agent / Context Worker】保存独立 Worker 的 `include_client_messages` 和组件覆写。允许覆写的能力可继承
当前 Primary、替换为同类型组件或关闭可选能力；具体范围由后端 manifest 的 Worker 策略决定。

Primary 的每条 `workers[]` binding 必须有唯一名称、用途说明和 Worker Profile UUID。Primary 同时选择
Context Worker 委派组件后，LangChain Agent 获得 `run_worker(worker, task)` Tool；一个模型响应可产生
多个并行调用。Worker 从冻结客户端消息副本和自己的 Prompt Preset 启动，不继承 Primary 的 AI/Tool
过程。DeepAgents Subagent 与 Context Worker 是并列能力，互不覆盖。

## 保存期与运行期

组件、Primary Agent、Subagent 覆写和 Context Worker Profile 页把完整草稿发给同一个后端预校验入口。文本、数字等连续输入停止固定
1000ms 后刷新；能力选择等离散操作可立即刷新。清单明确区分“正在校验”“有效”“无效”和
“校验状态不可用”，并忽略晚到的旧草稿响应。问题项使用后端给出的 owner、字段 path、稳定
message key 和安全参数，并按当前页面语言显示；前端不重新判断 required、依赖、引用、最终
Subagent、Context Worker 或工具名。无效与不可用状态统一显示为默认收起的报警摘要，展开后才显示完整问题；每个问题
都必须有非空的问题位置、原因和处理方法，未知错误代码也使用安全通用兜底，不显示空字段名或空处理方法。

保存按钮不依赖最近一次实时报告是否显示“通过”；点击后服务端一定用当前 payload 再校验，因此直接 API
调用和绕过页面脚本得到相同结果。保存失败会一次显示本次报告中的全部问题；网络或鉴权失败不会
显示成绿色。Subagent 的继承与覆写由后端解析。

Primary 保存和每次真实请求现在复用同一个后端静态装配校验，统一检查 required、失效 UUID、
委派 binding、有效 Subagent/Context Worker 最终引用、被引用组件当前结构、最终 Filesystem 装配模式和可静态确定的工具
重名。自定义 Tool 的静态名称来自 AST 可确定的函数默认名或字面量 `@tool` 名，不使用资源文件名
猜测。组件、Primary 和覆写自身的
严格 contract 错误会使用统一问题报告返回稳定 code、字段路径与安全说明，不回显原始输入。
所有组件、Primary、Subagent 覆写和 Worker Profile 在新建、覆盖或从仓库复制时都会由服务端重新校验；直接调用
management API 也不能绕过。更新已有组件或覆写时，服务端会用拟保存内容检查正在引用它的
Primary 与绑定的 Subagent；如果新增装配问题，本次写入会被拒绝，数据库仍保留原内容。已有的
无关旧问题不会阻止修复其他配置。
仓库复制只把源 UUID 和新名称提交给对应服务端 copy endpoint；服务端读取当前源记录并复用上述
校验后生成新 UUID。页面不再用 GET、改名、POST 模拟复制，副本也不会改写源配置或移动任何引用。
管理页面通过一个通用的 `POST /api/validation/draft` 提交 `target` 与完整草稿做不落库预校验；
block、Primary、Subagent 覆写和 Worker Profile 共用同一入口与保存规则。后端返回稳定 code、message key 和安全
参数；页面通过 vue-i18n 显示当前语言，不解析英文 fallback，也不弹出只有错误码的对话框。
输出模式模板的未闭合双花括号、未知变量和空启用模板使用专用稳定 code，并定位到具体事件模板；
Subagent 与 Context Worker binding 的名称缺失、名称格式、说明缺失和重复名称分别使用专用稳定 code，
并精确定位到对应数组字段；不会退化成 Primary 的整份配置错误。
其余普通 contract 错误至少提示所属配置、字段或整份配置，并建议检查格式、JSON 结构或模板语法。
Python 资源能否物化、
DeepAgents 是否安装、磁盘资源是否仍存在、Provider 能否连接，以及动态 Middleware 最终公开的
工具名，在每次 API 请求构建 Agent 时重新检查。自定义 Tool 源码、Skill frontmatter 和输出模式
当前结构也会在运行前复查；无效输出模式在任何用户源码和 Provider 前失败。后端报告显示“通过”表示当前
结构可保存并参与装配，不表示外部状态以后不会变化。

请求准备期的静态和动态配置问题都归入后端 `request_prepare` 报告，内部保留稳定 code、
Primary/Subagent/Context Worker owner、领域 path 和安全 message；OpenAI-compatible API 用同一问题生成现有错误
外壳。报告对象在统一边界脱敏用户可控的 owner、path 和 message，不把 secret、Bearer token、
源码、宿主路径或 traceback 返回给调用者。Primary 与同步 Subagent owner 成功物化的 Tool、Middleware、
model 和 filesystem 对象直接交给本次唯一 `create_deep_agent()`；当前 Context Worker 仍直接交给自己的 `create_agent()`，不会先“试构造”再重复
构造。Provider/Tool/graph 真正执行后的失败仍属于 runtime，不混进配置报告。

修改组件、当前 Primary、覆写策略或 Provider credential 后，后续请求使用新配置；正在运行的请求
继续使用其已经构造的对象。每个新推理请求先在一次 SQLite 读事务中复制配置和 secret，再从该
query-only 内存快照解析 model 与完整装配，因此不会在同一次 `create_deep_agent()` 中混用修改前后的记录。
请求仍会重新加载 Primary 配置的请求级初始文件；同一请求中的 Primary 与同步 Subagent 共享这份
临时文件 state，请求结束后不会保留到下一请求。Skill 和 mapped filesystem 等磁盘资源保持实时。
共享普通工作空间不等于共享 Skill：每个消费者只挂载自己最终选择的只读 Skill 集合。没有真实
Filesystem、但有 Skill 的消费者使用独立空 fallback，不参与该共享 state。
