<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type {
  MainAgent,
  WorkflowConditionOperator,
  WorkflowNodeHandleSpec,
} from '@/api'
import FormField from '@/components/FormField.vue'
import type {
  WorkflowCanvasEdge,
  WorkflowCanvasEdgeType,
  WorkflowCanvasNode,
} from '@/domain/workflowGraph'

const props = defineProps<{
  collapsed: boolean
  edge: WorkflowCanvasEdge | null
  edgeSourceEndpoints: WorkflowNodeHandleSpec[]
  edgeTargetEndpoints: WorkflowNodeHandleSpec[]
  edgeTypeOptions: WorkflowCanvasEdgeType[]
  inputEndpoints: WorkflowNodeHandleSpec[]
  mainAgents: MainAgent[]
  node: WorkflowCanvasNode | null
  outputEndpoints: WorkflowNodeHandleSpec[]
  stateContract: string
  workflowName: string
}>()

const emit = defineEmits<{
  removeEdge: [edgeId: string]
  removeNode: [nodeId: string]
  selectEdgeSourceEndpoint: [edgeId: string, endpointId: string]
  selectEdgeTargetEndpoint: [edgeId: string, endpointId: string]
  selectEdgeType: [edgeId: string, edgeType: WorkflowCanvasEdgeType]
  toggle: []
  updateAgent: [nodeId: string, mainAgentId: string]
  updateConditionOperator: [nodeId: string, operator: WorkflowConditionOperator]
  updateConditionPath: [nodeId: string, path: string]
  updateConditionSource: [nodeId: string, source: 'state' | 'context']
  updateConditionValue: [nodeId: string, valueJson: string]
  updateDefer: [nodeId: string, defer: boolean]
}>()

const { t } = useI18n()

const contextTitle = computed(() => {
  if (props.node) return t(`workflows.editor.${props.node.data.nodeType}`)
  if (props.edge) return edgeTypeLabel(props.edge.data?.edgeType ?? '')
  return t('workflows.editor.workflowProperties')
})
const edgeSourceOptions = computed(() => props.edgeSourceEndpoints.filter((endpoint) => (
  endpoint.edge_type === props.edge?.data?.edgeType
)))
const edgeTargetOptions = computed(() => props.edgeTargetEndpoints.filter((endpoint) => (
  endpoint.edge_type === props.edge?.data?.edgeType
)))

function edgeTypeLabel(edgeType: string): string {
  if (edgeType === 'normal') return t('workflows.editor.normalEdge')
  if (edgeType === 'conditional') return t('workflows.editor.conditionalEdge')
  return edgeType
}

function endpointLabel(endpoint: WorkflowNodeHandleSpec): string {
  return `${edgeTypeLabel(endpoint.edge_type)} · ${endpoint.id}`
}

function updateAgent(event: Event): void {
  if (!props.node || props.node.data.nodeType !== 'agent') return
  emit('updateAgent', props.node.id, (event.target as HTMLSelectElement).value)
}

function updateDefer(event: Event): void {
  if (!props.node || props.node.data.nodeType !== 'agent') return
  emit('updateDefer', props.node.id, (event.target as HTMLInputElement).checked)
}

function updateConditionSource(event: Event): void {
  if (!props.node || props.node.data.nodeType !== 'condition') return
  const source = (event.target as HTMLSelectElement).value
  if (source !== 'state' && source !== 'context') return
  emit('updateConditionSource', props.node.id, source)
}

function updateConditionPath(event: Event): void {
  if (!props.node || props.node.data.nodeType !== 'condition') return
  emit('updateConditionPath', props.node.id, (event.target as HTMLInputElement).value)
}

function updateConditionOperator(event: Event): void {
  if (!props.node || props.node.data.nodeType !== 'condition') return
  const operator = (event.target as HTMLSelectElement).value as WorkflowConditionOperator
  if (!['equals', 'not_equals', 'exists', 'not_exists'].includes(operator)) return
  emit('updateConditionOperator', props.node.id, operator)
}

function updateConditionValue(event: Event): void {
  if (!props.node || props.node.data.nodeType !== 'condition') return
  emit('updateConditionValue', props.node.id, (event.target as HTMLTextAreaElement).value)
}

function conditionValueValid(value: string | undefined): boolean {
  try {
    JSON.parse(value ?? '')
    return true
  } catch {
    return false
  }
}

function selectEdgeType(event: Event): void {
  if (!props.edge) return
  const edgeType = (event.target as HTMLSelectElement).value as WorkflowCanvasEdgeType
  if (!props.edgeTypeOptions.includes(edgeType)) return
  emit('selectEdgeType', props.edge.id, edgeType)
}

function selectEdgeSourceEndpoint(event: Event): void {
  if (!props.edge) return
  emit('selectEdgeSourceEndpoint', props.edge.id, (event.target as HTMLSelectElement).value)
}

function selectEdgeTargetEndpoint(event: Event): void {
  if (!props.edge) return
  emit('selectEdgeTargetEndpoint', props.edge.id, (event.target as HTMLSelectElement).value)
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
        <div
          v-for="endpoint in inputEndpoints"
          :key="`input-${endpoint.id}`"
          class="workflow-inspector-field"
        >
          <span class="workflow-inspector-label">{{ $t('workflows.editor.inputEndpoint') }}</span>
          <span class="workflow-inspector-value">{{ endpointLabel(endpoint) }}</span>
        </div>
        <div
          v-for="endpoint in outputEndpoints"
          :key="`output-${endpoint.id}`"
          class="workflow-inspector-field"
        >
          <span class="workflow-inspector-label">{{ $t('workflows.editor.outputEndpoint') }}</span>
          <span class="workflow-inspector-value">{{ endpointLabel(endpoint) }}</span>
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
          <FormField
            field-path="definition.nodes[].config.defer"
            label-key="workflows.editor.defer"
          >
            <div class="form-check form-switch">
              <input
                id="workflow-node-defer"
                class="form-check-input"
                type="checkbox"
                :checked="node.data.defer"
                @change="updateDefer"
              >
              <label class="form-check-label" for="workflow-node-defer">
                {{ $t('workflows.editor.deferEnabled') }}
              </label>
            </div>
          </FormField>
          <button class="workflow-inspector-delete" type="button" @click="emit('removeNode', node.id)">
            <i class="bi bi-trash" aria-hidden="true" />
            {{ $t('workflows.editor.removeAgent') }}
          </button>
        </template>

        <template v-else-if="node.data.nodeType === 'condition'">
          <FormField
            field-path="definition.nodes[].config.source"
            label-key="workflows.editor.conditionSource"
          >
            <select
              id="workflow-condition-source"
              class="form-select workflow-inspector-select"
              :value="node.data.conditionSource"
              @change="updateConditionSource"
            >
              <option value="state">state</option>
              <option value="context">context</option>
            </select>
          </FormField>
          <FormField
            field-path="definition.nodes[].config.path"
            label-key="workflows.editor.conditionPath"
          >
            <input
              id="workflow-condition-path"
              class="form-control"
              type="text"
              :value="node.data.conditionPath"
              @input="updateConditionPath"
            >
            <div class="form-text">{{ $t('workflows.editor.jsonPointer') }}</div>
          </FormField>
          <FormField
            field-path="definition.nodes[].config.operator"
            label-key="workflows.editor.conditionOperator"
          >
            <select
              id="workflow-condition-operator"
              class="form-select workflow-inspector-select"
              :value="node.data.conditionOperator"
              @change="updateConditionOperator"
            >
              <option value="equals">equals</option>
              <option value="not_equals">not_equals</option>
              <option value="exists">exists</option>
              <option value="not_exists">not_exists</option>
            </select>
          </FormField>
          <FormField
            v-if="node.data.conditionOperator === 'equals' || node.data.conditionOperator === 'not_equals'"
            field-path="definition.nodes[].config.value"
            label-key="workflows.editor.conditionValue"
          >
            <textarea
              v-if="conditionValueValid(node.data.conditionValueJson)"
              id="workflow-condition-value"
              class="form-control"
              rows="3"
              :value="node.data.conditionValueJson"
              @input="updateConditionValue"
            />
            <textarea
              v-else
              id="workflow-condition-value"
              class="form-control is-invalid"
              rows="3"
              :value="node.data.conditionValueJson"
              @input="updateConditionValue"
            />
            <div v-if="!conditionValueValid(node.data.conditionValueJson)" class="invalid-feedback">
              {{ $t('workflows.editor.invalidJsonValue') }}
            </div>
          </FormField>
          <button class="workflow-inspector-delete" type="button" @click="emit('removeNode', node.id)">
            <i class="bi bi-trash" aria-hidden="true" />
            {{ $t('workflows.editor.removeCondition') }}
          </button>
        </template>

        <p v-else class="workflow-inspector-note">{{ $t('workflows.editor.fixedNode') }}</p>
      </template>

      <template v-else-if="edge">
        <div class="workflow-inspector-field">
          <label class="workflow-inspector-label" for="workflow-edge-type">
            {{ $t('workflows.editor.edgeType') }}
          </label>
          <select
            id="workflow-edge-type"
            class="form-select workflow-inspector-select"
            name="edge-type"
            :value="edge.data?.edgeType"
            @change="selectEdgeType"
          >
            <option v-for="edgeType in edgeTypeOptions" :key="edgeType" :value="edgeType">
              {{ edgeTypeLabel(edgeType) }}
            </option>
          </select>
        </div>
        <div class="workflow-inspector-field">
          <label class="workflow-inspector-label" for="workflow-edge-source-endpoint">
            {{ $t('workflows.editor.source') }}
          </label>
          <select
            id="workflow-edge-source-endpoint"
            class="form-select workflow-inspector-select"
            name="source-endpoint"
            :value="edge.sourceHandle"
            @change="selectEdgeSourceEndpoint"
          >
            <option v-for="endpoint in edgeSourceOptions" :key="endpoint.id" :value="endpoint.id">
              {{ edge.source }} · {{ endpointLabel(endpoint) }}
            </option>
          </select>
        </div>
        <div class="workflow-inspector-field">
          <label class="workflow-inspector-label" for="workflow-edge-target-endpoint">
            {{ $t('workflows.editor.target') }}
          </label>
          <select
            id="workflow-edge-target-endpoint"
            class="form-select workflow-inspector-select"
            name="target-endpoint"
            :value="edge.targetHandle"
            @change="selectEdgeTargetEndpoint"
          >
            <option v-for="endpoint in edgeTargetOptions" :key="endpoint.id" :value="endpoint.id">
              {{ edge.target }} · {{ endpointLabel(endpoint) }}
            </option>
          </select>
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
          <span class="workflow-inspector-value">normal, conditional</span>
        </div>
      </template>
    </div>
  </aside>
</template>
