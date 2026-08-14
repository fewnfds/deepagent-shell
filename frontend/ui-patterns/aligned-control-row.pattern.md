# Aligned control row

Find as: 并排字段、统一高度、搜索工具栏、筛选工具栏、操作按钮、switch 同排、aligned controls、control row。

Use: 同一网格并排放置 label、input、input-group、switch 或操作按钮。Source of truth: `management-control-field`。

Contract:

- 同级标签统一使用 `.form-label`，不在 pattern 或页面单独设字号；标题层级使用 `h2/h3`。
- 控件区使用同一最小行高，按钮、input-group 和 switch 通过父级对齐，不互相追加视觉补丁。
- 操作和筛选属于控件区，不另起一套按钮尺寸；没有匹配项时不要自创局部布局。

Correct:

```vue
<div class="management-control-field">
  <label class="form-label" for="query">Search</label>
  <div class="input-group">
    <input id="query" class="form-control" type="search">
    <button class="btn btn-primary" type="submit">Search</button>
  </div>
</div>
```

Verify: `src/components/data-table/DataTableWorkbench.vue`、`src/pages/EventFeedPage.vue`、`src/pages/WorkflowsPage.vue`。
