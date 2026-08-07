<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import type { Connection, XYPosition } from '@vue-flow/core'

import {
  managementApi,
  type EntryScript,
  type MainAgent,
  type ValidationReport,
  type Workflow,
  type WorkflowDefinition,
  type WorkflowEdge,
  type WorkflowNode,
  type WorkflowNodeCatalogItem,
} from '@/api'
import CanvasWorkspaceShell from '@/components/workflow/CanvasWorkspaceShell.vue'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { blankWorkflow, edgeId, nextNodeId, nodeCatalogItem, normalizeWorkflow } from '@/domain/workflows'
import { cloneWorkflow } from '@/domain/graphWorkspace'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const managementError = useManagementError()
const { notify } = useToasts()
const workflow = ref<WorkflowDefinition | Workflow>(blankWorkflow())
const catalog = ref<WorkflowNodeCatalogItem[]>([])
const entries = ref<EntryScript[]>([])
const agents = ref<MainAgent[]>([])
const selectedNodeId = ref('')
const selectedEdgeId = ref('')
const selectedEntryId = ref('')
const statuses = ref<Record<string, string>>({})
const loading = ref(true)
const saving = ref(false)
const validating = ref(false)
const error = ref('')
const validation = ref<ValidationReport | null>(null)
const nodeConfigError = ref('')
const history = ref<Array<WorkflowDefinition | Workflow>>([])
const historyIndex = ref(-1)
const isNew = computed(() => !('id' in workflow.value) || !workflow.value.id)
const graphId = computed(() => ('id' in workflow.value ? workflow.value.id : ''))
const selectedNode = computed(() => workflow.value.nodes.find((node) => node.id === selectedNodeId.value))
const selectedDefinition = computed(() => selectedNode.value ? nodeCatalogItem(catalog.value, selectedNode.value.type) : undefined)
const selectedEdge = computed(() => workflow.value.edges.find((edge) => edge.id === selectedEdgeId.value))
const selectedEntry = computed(() => entries.value.find((entry) => entry.id === selectedEntryId.value))
const isNewRoute = computed(() => (
  route.path === '/workflows/new'
  || String(route.params.workflowId ?? '') === 'new'
))

const { isDirty, markClean, runAfterDiscard } = useUnsavedChanges(
  () => workflow.value,
  () => ({ title: t('unsavedChanges.title'), description: t('unsavedChanges.description'), confirmLabel: t('unsavedChanges.confirm'), cancelLabel: t('common.cancel') }),
)

function initializeHistory(value: WorkflowDefinition | Workflow): void {
  const snapshot = cloneWorkflow(value)
  workflow.value = snapshot
  history.value = [cloneWorkflow(snapshot)]
  historyIndex.value = 0
}

function commitWorkflow(value: WorkflowDefinition | Workflow): void {
  const snapshot = cloneWorkflow(value)
  history.value = history.value.slice(0, historyIndex.value + 1)
  history.value.push(cloneWorkflow(snapshot))
  historyIndex.value = history.value.length - 1
  workflow.value = snapshot
}

function undo(): void {
  if (historyIndex.value <= 0) return
  historyIndex.value -= 1
  workflow.value = cloneWorkflow(history.value[historyIndex.value] as WorkflowDefinition | Workflow)
}

function redo(): void {
  if (historyIndex.value >= history.value.length - 1) return
  historyIndex.value += 1
  workflow.value = cloneWorkflow(history.value[historyIndex.value] as WorkflowDefinition | Workflow)
}

function onUpdateWorkflow(field: 'name' | 'description' | 'enabled' | 'recursion_limit', value: string | number | boolean): void {
  commitWorkflow({ ...workflow.value, [field]: value })
}

function onToggleEntryNode(nodeId: string): void {
  const entryNodes = workflow.value.entry_nodes.includes(nodeId)
    ? workflow.value.entry_nodes.filter((id) => id !== nodeId)
    : [...workflow.value.entry_nodes, nodeId]
  commitWorkflow({ ...workflow.value, entry_nodes: entryNodes.length ? entryNodes : workflow.value.nodes.slice(0, 1).map((node) => node.id) })
}

function onAddNode(type: string, position: XYPosition): void {
  const definition = nodeCatalogItem(catalog.value, type)
  if (!definition) return
  const id = nextNodeId(workflow.value.nodes, type)
  const config = Object.fromEntries(Object.entries((definition.config_schema as { properties?: Record<string, { default?: unknown }> }).properties ?? {}).filter(([, schema]) => Object.hasOwn(schema, 'default')).map(([key, schema]) => [key, schema.default]))
  const node: WorkflowNode = { id, type, version: definition.version, config }
  if (definition.execution_kind === 'agent') node.config.profile_id = agents.value[0]?.id ?? ''
  commitWorkflow({
    ...workflow.value,
    nodes: [...workflow.value.nodes, node],
    layout: { ...workflow.value.layout, [id]: position },
    entry_nodes: workflow.value.entry_nodes.length ? workflow.value.entry_nodes : [id],
  })
  selectedNodeId.value = id
  selectedEdgeId.value = ''
}

function onRemoveNode(nodeId: string): void {
  commitWorkflow({
    ...workflow.value,
    nodes: workflow.value.nodes.filter((node) => node.id !== nodeId),
    entry_nodes: workflow.value.entry_nodes.filter((id) => id !== nodeId),
    edges: workflow.value.edges.filter((edge) => edge.source.node !== nodeId && edge.target.node !== nodeId),
  })
  if (selectedNodeId.value === nodeId) selectedNodeId.value = workflow.value.nodes[0]?.id ?? ''
}

function onRemoveEdge(id: string): void {
  commitWorkflow({ ...workflow.value, edges: workflow.value.edges.filter((edge) => edge.id !== id) })
  if (selectedEdgeId.value === id) selectedEdgeId.value = ''
}

function onConnect(connection: Connection): void {
  if (!connection.source || !connection.target || connection.source === connection.target) return
  const sourceNode = workflow.value.nodes.find((node) => node.id === connection.source)
  const targetNode = workflow.value.nodes.find((node) => node.id === connection.target)
  const sourceDefinition = sourceNode && nodeCatalogItem(catalog.value, sourceNode.type)
  const targetDefinition = targetNode && nodeCatalogItem(catalog.value, targetNode.type)
  const sourcePort = connection.sourceHandle ?? sourceDefinition?.output_ports[0]?.name
  const targetPort = connection.targetHandle ?? targetDefinition?.input_ports[0]?.name
  if (!sourcePort || !targetPort) return
  const edge: WorkflowEdge = { id: edgeId(workflow.value.edges), kind: 'control', source: { node: connection.source, port: sourcePort }, target: { node: connection.target, port: targetPort }, condition: null }
  commitWorkflow({ ...workflow.value, edges: [...workflow.value.edges, edge] })
  selectedEdgeId.value = edge.id
  selectedNodeId.value = ''
}

function onMoveNode(id: string, x: number, y: number): void {
  commitWorkflow({ ...workflow.value, layout: { ...workflow.value.layout, [id]: { x, y } } })
}

function onUpdateNode(node: WorkflowNode): void {
  commitWorkflow({ ...workflow.value, nodes: workflow.value.nodes.map((item) => item.id === node.id ? node : item) })
  nodeConfigError.value = ''
}

function onUpdateEdge(edge: WorkflowEdge): void {
  commitWorkflow({ ...workflow.value, edges: workflow.value.edges.map((item) => item.id === edge.id ? edge : item) })
}

async function validate(): Promise<boolean> {
  error.value = ''
  validating.value = true
  try {
    validation.value = await managementApi.validateWorkflowDraft({ ...cloneWorkflow(workflow.value), ...(!isNew.value ? { id: graphId.value } : {}) } as WorkflowDefinition & { id?: string })
    return validation.value.valid
  } catch (cause) { error.value = managementError.describe(cause).display; return false } finally { validating.value = false }
}

async function save(): Promise<void> {
  const wasNew = isNew.value
  if (!await validate()) return
  saving.value = true
  try {
    const saved = await managementApi.saveWorkflow(workflow.value)
    initializeHistory(normalizeWorkflow(saved))
    markClean()
    notify({ tone: 'success', title: t('workflow.saved') })
    if (wasNew) await router.replace(`/workflows/${encodeURIComponent(saved.id)}`)
  } catch (cause) { error.value = managementError.describe(cause).display } finally { saving.value = false }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [nodeCatalog, mainAgents, entryItems, current] = await Promise.all([
      managementApi.getWorkflowNodeCatalog(),
      managementApi.listMainAgents(),
      managementApi.listEntryScripts(),
      isNewRoute.value ? Promise.resolve(null) : managementApi.getWorkflow(String(route.params.workflowId)),
    ])
    catalog.value = nodeCatalog.nodes
    agents.value = mainAgents
    entries.value = entryItems
    initializeHistory(current ? normalizeWorkflow(current) : blankWorkflow())
    selectedEntryId.value = entryItems.find((entry) => entry.graph_id === graphId.value && entry.enabled)?.id ?? ''
    selectedNodeId.value = workflow.value.nodes[0]?.id ?? ''
    selectedEdgeId.value = ''
    validation.value = null
    markClean()
  } catch (cause) { error.value = managementError.describe(cause).display } finally { loading.value = false }
}

function goBack(): void { void runAfterDiscard(() => router.push('/workflows')) }
function newWorkflow(): void {
  void runAfterDiscard(async () => {
    if (isNewRoute.value) {
      initializeHistory(blankWorkflow())
      selectedNodeId.value = 'agent-1'
      selectedEdgeId.value = ''
      selectedEntryId.value = ''
      validation.value = null
      error.value = ''
      markClean()
      return
    }
    await router.push('/workflows/new')
  })
}

onMounted(() => { void load() })
</script>

<template>
  <div v-if="!loading" class="canvas-workspace-host">
    <p v-if="error" class="workspace-error text-danger">{{ error }}</p>
    <CanvasWorkspaceShell
      :catalog="catalog"
      :can-redo="historyIndex < history.length - 1"
      :can-undo="historyIndex > 0"
      :dirty="isDirty"
      :entries="entries"
      :graph-id="graphId"
      :is-new="isNew"
      :node-config-error="nodeConfigError"
      :saving="saving"
      :selected-definition="selectedDefinition"
      :selected-edge="selectedEdge"
      :selected-edge-id="selectedEdgeId"
      :selected-entry-id="selectedEntryId"
      :selected-node="selectedNode"
      :selected-node-id="selectedNodeId"
      :statuses="statuses"
      :valid="validation?.valid ?? null"
      :validating="validating"
      :workflow="workflow"
      @add-node="onAddNode"
      @back="goBack"
      @connect="onConnect"
      @delete-edge="selectedEdgeId ? onRemoveEdge(selectedEdgeId) : undefined"
      @delete-node="selectedNodeId ? onRemoveNode(selectedNodeId) : undefined"
      @move-node="onMoveNode"
      @new-workflow="newWorkflow"
      @remove-edge="onRemoveEdge"
      @remove-node="onRemoveNode"
      @reset-status="statuses = {}"
      @save="void save()"
      @select-edge="selectedEdgeId = $event; selectedNodeId = ''"
      @select-entry="selectedEntryId = $event"
      @select-node="selectedNodeId = $event; selectedEdgeId = ''"
      @status="(id, status) => statuses[id] = status"
      @toggle-entry-node="onToggleEntryNode"
      @update-edge="onUpdateEdge"
      @update-node="onUpdateNode"
      @update-workflow="onUpdateWorkflow"
      @validate="void validate()"
      @redo="redo"
      @undo="undo"
    />
  </div>
  <div v-else class="canvas-workspace-loading">正在加载 Graph Workspace…</div>
</template>
