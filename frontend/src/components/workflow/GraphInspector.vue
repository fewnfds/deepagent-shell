<script setup lang="ts">
import { computed, ref } from 'vue'
import type { EntryScript, Workflow, WorkflowDefinition, WorkflowEdge, WorkflowNode, WorkflowNodeCatalogItem } from '@/api'

const props = defineProps<{
  workflow: WorkflowDefinition | Workflow
  selectedNode?: WorkflowNode
  selectedDefinition?: WorkflowNodeCatalogItem
  selectedEdge?: WorkflowEdge
  entries: EntryScript[]
  selectedEntryId: string
  nodeConfigError?: string
}>()
const emit = defineEmits<{
  updateNode: [node: WorkflowNode]
  updateEdge: [edge: WorkflowEdge]
  deleteNode: []
  deleteEdge: []
  selectEntry: [id: string]
  toggleEntryNode: [nodeId: string]
  updateWorkflow: [field: 'name' | 'description' | 'enabled' | 'recursion_limit', value: string | number | boolean]
}>()

const showAdvanced = ref(false)
const advancedError = ref('')
const schemaProperties = computed(() => {
  const properties = props.selectedDefinition?.config_schema?.properties
  if (!properties || typeof properties !== 'object') return []
  return Object.entries(properties as Record<string, Record<string, unknown>>)
})

function updateConfig(key: string, value: unknown): void {
  if (!props.selectedNode) return
  emit('updateNode', { ...props.selectedNode, config: { ...props.selectedNode.config, [key]: value } })
}

function updateRawConfig(raw: string): void {
  if (!props.selectedNode) return
  try {
    const value = JSON.parse(raw)
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('object required')
    advancedError.value = ''
    emit('updateNode', { ...props.selectedNode, config: value as Record<string, unknown> })
  } catch {
    advancedError.value = '配置必须是有效的 JSON 对象。'
  }
}

function updateNodeSetting(field: 'timeout_seconds' | 'max_attempts', raw: string): void {
  if (!props.selectedNode) return
  const value = raw === '' ? null : Number(raw)
  emit('updateNode', { ...props.selectedNode, [field]: Number.isFinite(value) ? value : null })
}

function updateEdgeField(field: 'kind' | 'condition', value: string): void {
  if (!props.selectedEdge) return
  emit('updateEdge', { ...props.selectedEdge, [field]: field === 'condition' && value === '' ? null : value })
}

function fieldType(schema: Record<string, unknown>): string {
  return typeof schema.type === 'string' ? schema.type : 'string'
}
</script>

<template>
  <aside class="workspace-panel workspace-panel--inspector" aria-label="Graph inspector">
    <div class="workspace-panel__header">
      <div>
        <div class="workspace-panel__eyebrow">INSPECTOR</div>
        <h2 class="workspace-panel__title">检查器</h2>
      </div>
      <i class="bi bi-sliders" aria-hidden="true" />
    </div>
    <div class="workspace-panel__body workspace-panel__body--scroll">
      <template v-if="selectedNode && selectedDefinition">
        <div class="workspace-inspector__identity">
          <strong>{{ selectedNode.id }}</strong>
          <span class="font-monospace">{{ selectedDefinition.type }}</span>
          <small>{{ selectedDefinition.description }}</small>
        </div>
        <div class="form-check mb-3">
          <input :id="`entry-node-${selectedNode.id}`" class="form-check-input" type="checkbox" :checked="workflow.entry_nodes.includes(selectedNode.id)" @change="emit('toggleEntryNode', selectedNode.id)">
          <label class="form-check-label" :for="`entry-node-${selectedNode.id}`">Graph 入口节点</label>
        </div>
        <div v-for="[key, schema] in schemaProperties" :key="key" class="mb-3">
          <label class="form-label" :for="`node-config-${selectedNode.id}-${key}`">{{ schema.title || key }}</label>
          <select
            v-if="Array.isArray(schema.enum)"
            :id="`node-config-${selectedNode.id}-${key}`"
            class="form-select form-select-sm"
            :value="String(selectedNode.config[key] ?? '')"
            @change="updateConfig(key, ($event.target as HTMLSelectElement).value)"
          >
            <option value="">未设置</option>
            <option v-for="option in schema.enum" :key="String(option)" :value="String(option)">{{ option }}</option>
          </select>
          <input
            v-else-if="fieldType(schema) === 'boolean'"
            :id="`node-config-${selectedNode.id}-${key}`"
            class="form-check-input"
            type="checkbox"
            :checked="Boolean(selectedNode.config[key])"
            @change="updateConfig(key, ($event.target as HTMLInputElement).checked)"
          >
          <input
            v-else
            :id="`node-config-${selectedNode.id}-${key}`"
            class="form-control form-control-sm"
            :type="fieldType(schema) === 'number' || fieldType(schema) === 'integer' ? 'number' : 'text'"
            :value="String(selectedNode.config[key] ?? '')"
            @input="updateConfig(key, ($event.target as HTMLInputElement).value)"
          >
          <small v-if="schema.description" class="form-text">{{ schema.description }}</small>
        </div>
        <div class="row g-2 mb-3">
          <div class="col-6"><label class="form-label" :for="`timeout-${selectedNode.id}`">超时（秒）</label><input :id="`timeout-${selectedNode.id}`" class="form-control form-control-sm" type="number" min="0.1" :value="selectedNode.timeout_seconds ?? ''" @input="updateNodeSetting('timeout_seconds', ($event.target as HTMLInputElement).value)"></div>
          <div class="col-6"><label class="form-label" :for="`attempts-${selectedNode.id}`">最大尝试</label><input :id="`attempts-${selectedNode.id}`" class="form-control form-control-sm" type="number" min="1" :value="selectedNode.max_attempts ?? ''" @input="updateNodeSetting('max_attempts', ($event.target as HTMLInputElement).value)"></div>
        </div>
        <button class="btn btn-sm btn-outline-secondary mb-3" type="button" @click="showAdvanced = !showAdvanced">{{ showAdvanced ? '隐藏高级 JSON' : '高级 JSON' }}</button>
        <div v-if="showAdvanced">
          <textarea class="form-control form-control-sm font-monospace" rows="8" :value="JSON.stringify(selectedNode.config, null, 2)" @input="updateRawConfig(($event.target as HTMLTextAreaElement).value)" />
          <p v-if="advancedError || nodeConfigError" class="text-danger small mt-1 mb-0">{{ advancedError || nodeConfigError }}</p>
        </div>
        <button class="btn btn-sm btn-outline-danger mt-3" type="button" @click="emit('deleteNode')"><i class="bi bi-trash" aria-hidden="true" /> 删除节点</button>
      </template>

      <template v-else-if="selectedEdge">
        <div class="workspace-inspector__identity">
          <strong>{{ selectedEdge.id }}</strong>
          <span class="font-monospace">{{ selectedEdge.source.node }}.{{ selectedEdge.source.port }} → {{ selectedEdge.target.node }}.{{ selectedEdge.target.port }}</span>
        </div>
        <label class="form-label" :for="`edge-kind-${selectedEdge.id}`">连线类型</label>
        <select :id="`edge-kind-${selectedEdge.id}`" class="form-select form-select-sm mb-3" :value="selectedEdge.kind" @change="updateEdgeField('kind', ($event.target as HTMLSelectElement).value)">
          <option value="control">control · 控制</option>
          <option value="data">data · 数据</option>
        </select>
        <label class="form-label" :for="`edge-condition-${selectedEdge.id}`">条件（可选）</label>
        <input :id="`edge-condition-${selectedEdge.id}`" class="form-control form-control-sm" type="text" :value="selectedEdge.condition ?? ''" placeholder="success / retry / failed" @input="updateEdgeField('condition', ($event.target as HTMLInputElement).value)">
        <button class="btn btn-sm btn-outline-danger mt-3" type="button" @click="emit('deleteEdge')"><i class="bi bi-trash" aria-hidden="true" /> 删除连线</button>
      </template>

      <template v-else>
        <div class="workspace-inspector__identity">
          <strong>Workflow 设置</strong>
          <small>画布只负责图的编排；组件配置仍在配置仓库管理。</small>
        </div>
        <label class="form-label" for="workflow-name">名称</label>
        <input id="workflow-name" class="form-control form-control-sm mb-3" type="text" :value="workflow['name']" @input="emit('updateWorkflow', 'name', ($event.target as HTMLInputElement).value)">
        <label class="form-label" for="workflow-description">说明</label>
        <textarea id="workflow-description" class="form-control form-control-sm mb-3" rows="3" :value="workflow['description']" @input="emit('updateWorkflow', 'description', ($event.target as HTMLTextAreaElement).value)" />
        <div class="form-check mb-3"><input id="workflow-enabled" class="form-check-input" type="checkbox" :checked="workflow['enabled']" @change="emit('updateWorkflow', 'enabled', ($event.target as HTMLInputElement).checked)"><label class="form-check-label" for="workflow-enabled">启用 Workflow</label></div>
        <label class="form-label" for="workflow-recursion-limit">步骤上限</label>
        <input id="workflow-recursion-limit" class="form-control form-control-sm mb-3" type="number" min="1" max="10000" :value="workflow['recursion_limit']" @input="emit('updateWorkflow', 'recursion_limit', Number(($event.target as HTMLInputElement).value))">
        <label class="form-label" for="workflow-entry-script">入口脚本</label>
        <select id="workflow-entry-script" class="form-select form-select-sm" :value="selectedEntryId" @change="emit('selectEntry', ($event.target as HTMLSelectElement).value)">
          <option value="">不使用入口脚本</option>
          <option v-for="entry in entries" :key="entry.id" :value="entry.id">{{ entry.name }}</option>
        </select>
        <small class="form-text">入口脚本是图的边界资源，不是普通 Graph 节点。</small>
        <div class="workspace-inspector__api mt-3"><span class="badge text-bg-success">API</span><span class="font-monospace">/v1/chat/completions</span></div>
      </template>
    </div>
  </aside>
</template>
