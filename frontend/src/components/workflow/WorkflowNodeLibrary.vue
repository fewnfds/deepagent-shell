<script setup lang="ts">
import type { WorkflowNodeCatalogItem } from '@/api'
import { WORKFLOW_NODE_DRAG_MIME } from '@/domain/workflowGraph'

const props = defineProps<{
  agent: WorkflowNodeCatalogItem | null
  condition: WorkflowNodeCatalogItem | null
  collapsed: boolean
  agentDisabled: boolean
  conditionDisabled: boolean
}>()

const emit = defineEmits<{
  addAgent: []
  addCondition: []
  toggle: []
}>()

function startDrag(
  event: DragEvent,
  item: WorkflowNodeCatalogItem | null,
  disabled: boolean,
): void {
  if (!item || disabled || !event.dataTransfer) {
    event.preventDefault()
    return
  }
  event.dataTransfer.setData(WORKFLOW_NODE_DRAG_MIME, item.type)
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
        :disabled="agentDisabled"
        :draggable="!agentDisabled"
        type="button"
        @click="emit('addAgent')"
        @dragstart="startDrag($event, agent, agentDisabled)"
      >
        <span class="workflow-node-library-icon" aria-hidden="true">
          <i class="bi bi-robot" />
        </span>
        <span class="workflow-node-library-copy">
          <span class="workflow-node-library-title">{{ $t('workflows.editor.agent') }}</span>
          <span class="workflow-node-library-meta">{{ $t('workflows.editor.compiledAgent') }}</span>
        </span>
      </button>
      <button
        v-if="condition"
        class="workflow-node-library-item"
        :disabled="conditionDisabled"
        :draggable="!conditionDisabled"
        type="button"
        @click="emit('addCondition')"
        @dragstart="startDrag($event, condition, conditionDisabled)"
      >
        <span class="workflow-node-library-icon" aria-hidden="true">
          <i class="bi bi-circle-half" />
        </span>
        <span class="workflow-node-library-copy">
          <span class="workflow-node-library-title">{{ $t('workflows.editor.condition') }}</span>
          <span class="workflow-node-library-meta">{{ $t('workflows.editor.stateCondition') }}</span>
        </span>
      </button>
    </div>
  </aside>
</template>
