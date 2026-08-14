<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core'
import { useI18n } from 'vue-i18n'

import type { WorkflowNodeHandleSpec } from '@/api'
import type { WorkflowEndpointDirection } from '@/domain/workflowGraph'

const props = defineProps<{
  direction: WorkflowEndpointDirection
  endpoints: WorkflowNodeHandleSpec[]
}>()

const { t } = useI18n()

function endpointTypeLabel(endpoint: WorkflowNodeHandleSpec): string {
  if (endpoint.edge_type === 'normal') return t('workflows.editor.normalEdge')
  if (endpoint.edge_type === 'conditional') return t('workflows.editor.conditionalEdge')
  return endpoint.edge_type
}

function endpointAriaLabel(endpoint: WorkflowNodeHandleSpec): string {
  return t(
    props.direction === 'input'
      ? 'workflows.editor.inputEndpointAria'
      : 'workflows.editor.outputEndpointAria',
    { id: endpoint.id, type: endpointTypeLabel(endpoint) },
  )
}
</script>

<template>
  <div class="workflow-node-endpoints" :data-direction="direction">
    <div v-for="endpoint in endpoints" :key="endpoint.id" class="workflow-node-endpoint">
      <span class="workflow-node-endpoint-label">{{ endpoint.id }}</span>
      <Handle
        v-if="endpoint.edge_type === 'normal'"
        :id="endpoint.id"
        class="workflow-port workflow-port--normal"
        :type="direction === 'input' ? 'target' : 'source'"
        :aria-label="endpointAriaLabel(endpoint)"
        :connectable="endpoint.max_connections ?? true"
        :position="direction === 'input' ? Position.Left : Position.Right"
      />
      <Handle
        v-else
        :id="endpoint.id"
        class="workflow-port workflow-port--conditional"
        :type="direction === 'input' ? 'target' : 'source'"
        :aria-label="endpointAriaLabel(endpoint)"
        :connectable="endpoint.max_connections ?? true"
        :position="direction === 'input' ? Position.Left : Position.Right"
      />
    </div>
  </div>
</template>
