# 装配 Primary 与 Subagent

## Primary

在【Agent / Primary Agent】选择已有配置或填写新名称，然后按顺序选择：模型、系统提示词、文件系统、
待办计划、自定义工具、Skill、自定义 Middleware、输出模式、异常重试、提示词预设和 Subagent。

模型和输出模式是必选项，缺少任一项时右侧草稿校验区会显示问题，服务端保存会拒绝；
文件系统及其他能力最多各选择一份，不选择就不装配。委派区域保存 `subagents[]`。每条 Subagent binding 固定以
当前 Primary 为基础，只保存可选的覆写策略 UUID，不复制被引用 payload。

保存后的 Primary 在 API Server 通过静态门禁并处于 running 时作为 `/v1/models` 中的 model
发布；页面本身没有单独“运行”按钮。

## Subagent 策略

【Agent / Subagent】保存可复用的 `capability_overrides[]` 和该 Subagent 自己的 `subagents[]`：

- 继承：不保存显式项，沿用当前 Primary 的同类引用；
- 替换：保存同类型 block UUID；
- 关闭：最终移除该能力。

model 只能继承或替换。filesystem 不可覆写；同一次请求中 Primary 与全部同步 Subagent 固定共享
同一个 workspace。output mode 与 Subagent 按 manifest 策略从 child 移除；提示词预设可以继承、替换
或关闭。

## 绑定

Primary 的每条 binding 添加后立即启用，并需要：

- 在该 Primary 内唯一、符合标识符规则的名称；
- 面向父 Agent 的用途说明；
- 可选的 Subagent 覆写策略；不选择表示完整继承当前 Primary。

真实请求按“当前 Primary + 可选覆写”构造同步 Subagent。父 Agent 的命名 bindings 不会隐式复制到
child；child 只使用目标覆写显式保存的 catalog。隐式 `general-purpose` 已全局关闭，空 catalog 没有
`task`；显式自引用或循环引用可提供递归委派。binding 不保存其他 Primary ID；完整继承能力时只把
`subagent_override_id` 留空，也不要求创建空覆写配置。binding 名称只要求在所属 catalog 内唯一；不同
Primary/Subagent 的 catalog 可以都使用同一个模型可见名称，例如 `worker`。

## Subagent 输入与缓存友好装配

child 的最终 Prompt Preset 是冻结客户端消息与 Startup conversation 的唯一门禁。选择到 Preset 时，
LangChain 原生 node-style `before_agent` Middleware 读取请求 context 中的冻结客户端消息，应用该 Preset，
追加 Startup conversation，再保留 Deep Agents 传入的 delegated task；最终没有 Preset 时不装配该节点，
child 只接收 delegated task。每次委派使用 fresh state，不继承 Primary 已产生的 AI/Tool 过程，也不包裹
`CompiledSubAgent` runnable。

Subagent 继续允许按策略自由装配，这是产品基线；普通组合不承诺跨 Agent Prompt Caching。缓存对齐只是
用户手工配置的理论特殊情况：让最终 model、system prompt、冻结客户端消息处理结果、按序 tool schema、
response schema 与相关 model settings 实际一致，只用不同 Preset 末尾的 Startup conversation 区分身份。
平台不比较或修正不同 Preset 的 Client tag replacements。工具不能假定为缓存键中的较后部分，默认
`task` 的 schema 会随命名 Subagent 列表变化。需要对齐时为两侧显式保存内容和顺序相同的 catalog；
实际缓存门槛、范围、TTL、计费和命中由具体 Provider/model 决定。

## 保存期与运行期

组件、Primary Agent 和 Subagent 覆写页把完整草稿发给同一个后端预校验入口。文本、数字等连续输入停止固定
1000ms 后刷新；能力选择等离散操作可立即刷新。清单明确区分“正在校验”“有效”“无效”和
“校验状态不可用”，并忽略晚到的旧草稿响应。问题项使用后端给出的 owner、字段 path、稳定
message key 和安全参数，并按当前页面语言显示；前端不重新判断 required、依赖、引用、最终
Subagent 或工具名。无效与不可用状态统一显示为默认收起的报警摘要，展开后才显示完整问题；每个问题
都必须有非空的问题位置、原因和处理方法，未知错误代码也使用安全通用兜底，不显示空字段名或空处理方法。

保存按钮不依赖最近一次实时报告是否显示“通过”；点击后服务端一定用当前 payload 再校验，因此直接 API
调用和绕过页面脚本得到相同结果。保存失败会一次显示本次报告中的全部问题；网络或鉴权失败不会
显示成绿色。Subagent 的继承与覆写由后端解析。

Primary 保存和每次真实请求现在复用同一个后端静态装配校验，统一检查 required、失效 UUID、
委派 binding、有效 Subagent 最终引用、被引用组件当前结构、请求级 Filesystem workspace 和可静态确定的工具
重名。自定义 Tool 的静态名称来自 AST 可确定的函数默认名或字面量 `@tool` 名，不使用资源文件名
猜测。组件、Primary 和覆写自身的
严格 contract 错误会使用统一问题报告返回稳定 code、字段路径与安全说明，不回显原始输入。
所有组件、Primary 和 Subagent 覆写在新建、覆盖或从仓库复制时都会由服务端重新校验；直接调用
management API 也不能绕过。更新已有组件或覆写时，服务端会用拟保存内容检查正在引用它的
Primary 与绑定的 Subagent；如果新增装配问题，本次写入会被拒绝，数据库仍保留原内容。已有的
无关旧问题不会阻止修复其他配置。
仓库复制只把源 UUID 和新名称提交给对应服务端 copy endpoint；服务端读取当前源记录并复用上述
校验后生成新 UUID。页面不再用 GET、改名、POST 模拟复制，副本也不会改写源配置或移动任何引用。
管理页面通过一个通用的 `POST /api/validation/draft` 提交 `target` 与完整草稿做不落库预校验；
block、Primary 和 Subagent 覆写共用同一入口与保存规则。后端返回稳定 code、message key 和安全
参数；页面通过 vue-i18n 显示当前语言，不解析英文 fallback，也不弹出只有错误码的对话框。
输出模式模板的未闭合双花括号、未知变量和空启用模板使用专用稳定 code，并定位到具体事件模板；
Subagent binding 的名称缺失、名称格式、说明缺失和重复名称分别使用专用稳定 code，
并精确定位到对应数组字段；不会退化成 Primary 的整份配置错误。
其余普通 contract 错误至少提示所属配置、字段或整份配置，并建议检查格式、JSON 结构或模板语法。
Python 资源能否物化、
DeepAgents 是否安装、磁盘资源是否仍存在、Provider 能否连接，以及动态 Middleware 最终公开的
工具名，在每次 API 请求构建 Agent 时重新检查。自定义 Tool 源码、Skill frontmatter 和输出模式
当前结构也会在运行前复查；无效输出模式在任何用户源码和 Provider 前失败。后端报告显示“通过”表示当前
结构可保存并参与装配，不表示外部状态以后不会变化。

请求准备期的静态和动态配置问题都归入后端 `request_prepare` 报告，内部保留稳定 code、
Primary/Subagent owner、领域 path 和安全 message；OpenAI-compatible API 用同一问题生成现有错误
外壳。报告对象在统一边界脱敏用户可控的 owner、path 和 message，不把 secret、Bearer token、
源码、宿主路径或 traceback 返回给调用者。Primary 与同步 Subagent owner 成功物化的 Tool、Middleware、
model 和 filesystem 对象直接交给本次唯一 `create_deep_agent()`，不会先“试构造”再重复构造。
Provider/Tool/graph 真正执行后的失败仍属于 runtime，不混进配置报告。

修改组件、当前 Primary、覆写策略或 Provider credential 后，后续请求使用新配置；正在运行的请求
继续使用其已经构造的对象。每个新推理请求先在一次 SQLite 读事务中复制配置和 secret，再从该
query-only 内存快照解析 model 与完整装配，因此不会在同一次 `create_deep_agent()` 中混用修改前后的记录。
请求仍只由 Primary 加载一次请求级初始文件；同一请求中的 Primary 与全部同步 Subagent 双向共享完整
虚拟 `files` state 和 mapped filesystem，请求结束后不会保留到下一请求。Skill 仍可按 Agent 选择提示
与 sources；每个 Agent 在共享普通 workspace 上叠加 consumer-specific 只读 `/skills/` 视图，只能读取
最终选中的 Skill，未选路径返回 not found，且不创建第二套普通 workspace。
