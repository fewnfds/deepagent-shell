<script setup lang="ts">
import type { WorkflowNodeCatalogItem } from '@/api'
import { WORKFLOW_NODE_DRAG_MIME } from '@/domain/workflowGraph'

const props = defineProps<{
  agent: WorkflowNodeCatalogItem | null
  collapsed: boolean
  disabled: boolean
}>()

const emit = defineEmits<{
  addAgent: []
  toggle: []
}>()

function startDrag(event: DragEvent): void {
  if (!props.agent || props.disabled || !event.dataTransfer) {
    event.preventDefault()
    return
  }
  event.dataTransfer.setData(WORKFLOW_NODE_DRAG_MIME, props.agent.type)
  event.dataTransfer.effectAllowed = 'copy'
}
</script>

<template>
  <aside class="workflow-sidebar workflow-sidebar--library" :data-collapsed="collapsed">
    <header class="workflow-sidebar-header">
      <h2 v-if="!collapsed" class="workflow-sidebar-title">
        {{ $t('workflows.editor.nodeLibrary') }}
      </h2>
      <button
        class="workflow-sidebar-toggle"
        :aria-label="$t(collapsed ? 'workflows.editor.expandNodeLibrary' : 'workflows.editor.collapseNodeLibrary')"
        :title="$t(collapsed ? 'workflows.editor.expandNodeLibrary' : 'workflows.editor.collapseNodeLibrary')"
        type="button"
        @click="emit('toggle')"
      >
        <i v-if="collapsed" class="bi bi-boxes" aria-hidden="true" />
        <i v-else class="bi bi-chevron-left" aria-hidden="true" />
      </button>
    </header>

    <div v-if="!collapsed" class="workflow-sidebar-body">
      <h3 class="workflow-sidebar-section-title">{{ $t('workflows.editor.executionNodes') }}</h3>
      <button
        v-if="agent"
        class="workflow-node-library-item"
        :disabled="disabled"
        :draggable="!disabled"
        type="button"
        @click="emit('addAgent')"
        @dragstart="startDrag"
      >
        <span class="workflow-node-library-icon" aria-hidden="true">
          <i class="bi bi-robot" />
        </span>
        <span class="workflow-node-library-copy">
          <span class="workflow-node-library-title">{{ $t('workflows.editor.agent') }}</span>
          <span class="workflow-node-library-meta">{{ $t('workflows.editor.compiledAgent') }}</span>
        </span>
      </button>
    </div>
  </aside>
</template>
