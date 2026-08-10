<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { MainAgent } from '@/api'
import FormField from '@/components/FormField.vue'
import type { WorkflowCanvasEdge, WorkflowCanvasNode } from '@/domain/workflowGraph'

const props = defineProps<{
  collapsed: boolean
  edge: WorkflowCanvasEdge | null
  mainAgents: MainAgent[]
  node: WorkflowCanvasNode | null
  stateContract: string
  workflowName: string
}>()

const emit = defineEmits<{
  removeEdge: [edgeId: string]
  removeNode: [nodeId: string]
  toggle: []
  updateAgent: [nodeId: string, mainAgentId: string]
}>()

const { t } = useI18n()

const contextTitle = computed(() => {
  if (props.node) return t(`workflows.editor.${props.node.data.nodeType}`)
  if (props.edge) return t('workflows.editor.normalEdge')
  return t('workflows.editor.workflowProperties')
})

function updateAgent(event: Event): void {
  if (!props.node || props.node.data.nodeType !== 'agent') return
  emit('updateAgent', props.node.id, (event.target as HTMLSelectElement).value)
}
</script>

<template>
  <aside class="workflow-sidebar workflow-sidebar--inspector" :data-collapsed="collapsed">
    <header class="workflow-sidebar-header">
      <button
        class="workflow-sidebar-toggle"
        :aria-label="$t(collapsed ? 'workflows.editor.expandInspector' : 'workflows.editor.collapseInspector')"
        :title="$t(collapsed ? 'workflows.editor.expandInspector' : 'workflows.editor.collapseInspector')"
        type="button"
        @click="emit('toggle')"
      >
        <i v-if="collapsed" class="bi bi-sliders" aria-hidden="true" />
        <i v-else class="bi bi-chevron-right" aria-hidden="true" />
      </button>
      <h2 v-if="!collapsed" class="workflow-sidebar-title">
        {{ $t('workflows.editor.inspector') }}
      </h2>
    </header>

    <div v-if="!collapsed" class="workflow-sidebar-body">
      <h3 class="workflow-inspector-context">{{ contextTitle }}</h3>

      <template v-if="node">
        <div class="workflow-inspector-field">
          <span class="workflow-inspector-label">{{ $t('workflows.editor.nodeId') }}</span>
          <span class="workflow-inspector-value">{{ node.id }}</span>
        </div>
        <div class="workflow-inspector-field">
          <span class="workflow-inspector-label">{{ $t('workflows.editor.nodeType') }}</span>
          <span class="workflow-inspector-value">{{ node.data.nodeType }}</span>
        </div>
        <div class="workflow-inspector-field">
          <span class="workflow-inspector-label">{{ $t('workflows.editor.typeVersion') }}</span>
          <span class="workflow-inspector-value">1</span>
        </div>

        <template v-if="node.data.nodeType === 'agent'">
          <FormField
            field-path="definition.nodes[].config.main_agent_id"
            label-key="workflows.editor.mainAgent"
          >
            <select
              class="form-select workflow-inspector-select"
              :value="node.data.mainAgentId"
              @change="updateAgent"
            >
              <option v-if="mainAgents.length === 0" value="">
                {{ $t('workflows.editor.noMainAgents') }}
              </option>
              <option v-for="agent in mainAgents" :key="agent.id" :value="agent.id">
                {{ agent.name }}
              </option>
            </select>
          </FormField>
          <button class="workflow-inspector-delete" type="button" @click="emit('removeNode', node.id)">
            <i class="bi bi-trash" aria-hidden="true" />
            {{ $t('workflows.editor.removeAgent') }}
          </button>
        </template>

        <p v-else class="workflow-inspector-note">{{ $t('workflows.editor.fixedNode') }}</p>
      </template>

      <template v-else-if="edge">
        <div class="workflow-inspector-field">
          <span class="workflow-inspector-label">{{ $t('workflows.editor.edgeType') }}</span>
          <span class="workflow-inspector-value">{{ edge.data?.edgeType }}</span>
        </div>
        <div class="workflow-inspector-field">
          <span class="workflow-inspector-label">{{ $t('workflows.editor.source') }}</span>
          <span class="workflow-inspector-value">{{ edge.source }} · {{ edge.sourceHandle }}</span>
        </div>
        <div class="workflow-inspector-field">
          <span class="workflow-inspector-label">{{ $t('workflows.editor.target') }}</span>
          <span class="workflow-inspector-value">{{ edge.target }} · {{ edge.targetHandle }}</span>
        </div>
        <button class="workflow-inspector-delete" type="button" @click="emit('removeEdge', edge.id)">
          <i class="bi bi-trash" aria-hidden="true" />
          {{ $t('workflows.editor.removeEdge') }}
        </button>
      </template>

      <template v-else>
        <div class="workflow-inspector-field">
          <span class="workflow-inspector-label">{{ $t('workflows.fields.name') }}</span>
          <span class="workflow-inspector-value">{{ workflowName }}</span>
        </div>
        <div class="workflow-inspector-field">
          <span class="workflow-inspector-label">{{ $t('workflows.editor.stateContract') }}</span>
          <span class="workflow-inspector-value">{{ stateContract }}</span>
        </div>
        <div class="workflow-inspector-field">
          <span class="workflow-inspector-label">{{ $t('workflows.editor.edgeType') }}</span>
          <span class="workflow-inspector-value">normal</span>
        </div>
      </template>
    </div>
  </aside>
</template>
