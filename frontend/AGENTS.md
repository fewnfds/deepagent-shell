# 前端开发入口

本目录是唯一前端源码。所有页面、组件、布局、主题、图标和样式改动先读取本文件，再读取
`ui-policy.json`；后端字段、权限、UUID、引用、路径和校验仍以后端 contract 为准。

## 唯一 UI 栈

- Vue 3 + Vite + Vue Router + vue-i18n；视觉只使用 AdminLTE 4.1、Bootstrap 5.3、官方
  `@adminlte/vue@0.3.0` 白名单组件和 Bootstrap Icons。
- 只做命名导入，不 `app.use(AdminLteVue)`，不导入 `@adminlte/vue/plugins`，不安装 Nuxt、第二套 UI、
  Chart、Table、Editor、Calendar、Map、Scrollbar 等 optional plugin。
- 禁止 Element Plus、第二套 UI、旧主题 token、旧 CSS 和迁移例外重新进入依赖、源码或测试环境；
  `ui-policy.json` 的 migration 数组必须保持为空。
- `OK / Close / Open / Light / Dark` 等简单基础英文可以使用；核心业务字段、动作、错误和安全提示继续
  使用现有 locale。不能为了形式上的完全 i18n 再造包装层。

## 写代码前的固定顺序

1. 判断任务属于 API/领域、页面编排、产品行为 host 还是壳层/主题。
2. 读取 `ui-policy.json` 中对应组件、class recipe、图标和路径例外。
3. 按任务读取正式参考页，不通过全仓搜索随机挑页面模仿：表单页用
   `src/pages/SystemSettingsPage.vue`，高密度实时页用 `src/pages/EventFeedPage.vue`，复杂配置工作区用
   `src/pages/ComponentsPage.vue` 及其 `src/editors/`。只复用对应职责和批准 recipe，不整页复制。
4. 直接复用批准组件和 recipe。没有匹配项时停止新增视觉能力，向用户说明真实场景并申请批准。
5. 获批后更新 `ui-policy.json` 中实际需要的组件、class、图标或路径白名单，再实现。只有形成跨页面、
   长期有效的设计原则或架构边界时才更新 UI contract；局部列宽、间距、颜色、对齐和页面微调不写入
   Agent 提示词。

正常复用批准项、修复 bug、机械模板绑定和 API 调整不需要重复审批。

## 责任和文件边界

- 页面拥有本页请求、状态和任务编排；`api/` 负责 transport；`domain/` 负责机械字段映射；后端拥有全部
  领域与安全判断。
- 前端信息架构按用户任务组织，禁止按 JSON/object/schema 的嵌套层级机械生成视觉层级。标题默认使用
  普通 heading；只有具有独立状态、操作或可移动边界的内容才使用 Card。
- Card 是主要内容单位，但必须作为当前路径最外层的原子任务；Card 内只放字段、普通列表行和操作，
  不再套子 Card 或伪 Card。Accordion 作为完整模块时不再套 Card；作为 Card 内列表时必须使用 flush
  结构直接继承边界，不套 `card-body` 或逐项伪 Card。
- 同一集合只使用一个 Card，重复条目用 `list-group-flush / list-group-item` 继承主体分隔线；同级项目仅在
  各自具有独立任务、状态或操作时使用并列 Card，外面不再增加“总览”父 Card。
- 组件 editor 的普通配置默认直接平铺，不折叠进 Accordion；文件工具等独立项目使用并列原子 Card。
  新增、刷新、恢复默认和删除等局部动作默认靠右，选项 Button 群按内容自然平铺。
- 同一内容路径只允许一个主要视觉容器拥有边界。Card、Accordion、bordered panel 或重复项不能因为
  “需要显示这一层名称”而互相嵌套；详细判定和文案价值测试见 UI contract 第 4 节。
- 自有组件只允许是产品行为 host（鉴权、焦点、Toast/确认、Validation）或有真实领域交互的稳定组合。
  不建立 Button/Input/Card wrapper、schema form、页面 builder、组件 registry 或 Storybook。
- 页面和 editor 不写 `<style>`、`style=`、硬编码颜色、未知 class 或动态视觉 class。唯一项目样式入口是
  policy 指定的 `src/styles/management-console.css`；确有缺口必须先批准并记录。
- 图标只用 policy 中批准的 Bootstrap Icons。icon-only button 必须有清楚的可访问名称，简单英文可接受。
- 不 patch/fork `node_modules`。上游成品不合格时使用官方 Bootstrap/AdminLTE 结构和现有产品行为层。

## 按任务读取

- 只改 API 或字段映射：读取相关 `api/`、`domain/`、后端 schema 和直接测试，不扩大到视觉层。
- 改表单或页面：读取 `.docs/management-console-ui-contract.md` 对应章节、policy 和同 archetype 页面。
- 改壳层、主题、Modal、Toast、确认或导航：完整读取 UI contract、policy 和对应集成测试。
- 改运行、构建、依赖或发布入口：同时读取 `../docs/development-and-release.md`。

## 最小验证

在 `frontend/` 内先运行：

```powershell
npm run ui:check
```

再按直接风险选择一项：`npm run typecheck`、相关 `npm test -- <file>` 或明确需要的 `npm run build`。
视觉判断使用隔离 Debug + 浏览器查看受影响主题/宽度；按钮、表单和业务路径优先用自动化脚本，不靠浏览器
逐个点击回归。最终收口才运行 Goal 指定的完整门禁。
