# AdminLTE control row

Find as: 并排字段、搜索工具栏、筛选工具栏、switch 同排、操作按钮、control row。

Use: 直接复用 AdminLTE/Bootstrap 现成结构，不增加项目级布局 class。

Contract:

- 普通字段使用 `.form-label` + `.form-control` / `.form-select`；需要字段语义、help 或 error 时使用 `FormField`。
- 单位或同行动作使用 `.input-group`；开关使用 `.form-check.form-switch`。
- 并排布局使用 Bootstrap `row g-3` 和列 class；确需底部对齐时只在该行使用 `align-items-end`。
- 控件保持组件默认宽高。禁止为统一外观增加固定高度、最小行高、等高 grid、slot flex wrapper 或页面私有尺寸补丁。
- `btn-sm` 只用于现有表格/列表行的紧凑操作；普通搜索、提交和表单动作沿用参考源码中的尺寸。

Reference: `src/components/data-table/DataTableWorkbench.vue`、`src/editors/CustomMiddlewareEditor.vue`、`src/editors/WorkflowInputContextEditor.vue`。
