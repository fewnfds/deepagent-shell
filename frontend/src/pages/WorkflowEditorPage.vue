<script setup lang="ts">
import {
  ConnectionMode,
  Handle,
  Position,
  VueFlow,
  type Connection,
  type VueFlowStore,
  type ViewportTransform,
  type XYPosition,
} from '@vue-flow/core'
import { computed, nextTick, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import {
  managementApi,
  type MainAgent,
  type Workflow,
  type WorkflowNodeCatalogItem,
  type WorkflowNodeType,
} from '@/api'
import WorkflowInspector from '@/components/workflow/WorkflowInspector.vue'
import WorkflowNodeLibrary from '@/components/workflow/WorkflowNodeLibrary.vue'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'
import {
  newAgentCanvasNode,
  WORKFLOW_NODE_DRAG_MIME,
  WORKFLOW_NORMAL_EDGE_MARKER,
  workflowCanvasToDocument,
  workflowConnectionEdgeType,
  workflowDocumentToCanvas,
  type WorkflowCanvasEdge,
  type WorkflowCanvasNode,
} from '@/domain/workflowGraph'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const managementError = useManagementError()
const { notify } = useToasts()
const workflow = ref<Workflow | null>(null)
const mainAgents = ref<MainAgent[]>([])
const nodeCatalog = ref<WorkflowNodeCatalogItem[]>([])
const nodes = ref<WorkflowCanvasNode[]>([])
const edges = ref<WorkflowCanvasEdge[]>([])
const flow = ref<VueFlowStore | null>(null)
const stateContract = ref('agent-shell.workflow.messages.v1')
const savedViewport = ref<ViewportTransform>({ x: 0, y: 0, zoom: 1 })
const leftCollapsed = ref(false)
const rightCollapsed = ref(false)
const loaded = ref(false)
const saving = ref(false)
const loadError = ref('')
const workflowId = computed(() => String(route.params.id ?? ''))
const agentCatalogItem = computed(() => (
  nodeCatalog.value.find((item) => item.type === 'agent') ?? null
))
const canAddAgent = computed(() => (
  loaded.value
  && mainAgents.value.length > 0
  && agentCatalogItem.value !== null
))
const canSave = computed(() => (
  loaded.value
  && !saving.value
  && !nodes.value.some((node) => node.data.nodeType === 'agent' && !node.data.mainAgentId)
))
const selectedNode = computed(() => nodes.value.find((node) => node.selected) ?? null)
const selectedEdge = computed(() => (
  selectedNode.value ? null : edges.value.find((edge) => edge.selected) ?? null
))

function normalHandleId(nodeType: WorkflowNodeType, output: boolean): string {
  const catalog = nodeCatalog.value.find((item) => item.type === nodeType)
  if (!catalog) return ''
  const handles = output ? catalog.output_handles : catalog.input_handles
  return handles.find((handle) => handle.edge_type === 'normal')?.id ?? ''
}

function isValidConnection(connection: Connection): boolean {
  return workflowConnectionEdgeType(
    connection,
    nodes.value,
    edges.value,
    nodeCatalog.value,
  ) !== null
}

function connect(connection: Connection): void {
  const edgeType = workflowConnectionEdgeType(
    connection,
    nodes.value,
    edges.value,
    nodeCatalog.value,
  )
  if (!edgeType) return
  nodes.value = nodes.value.map((node) => ({ ...node, selected: false }))
  edges.value = [
    ...edges.value.map((edge) => ({ ...edge, selected: false })),
    {
      id: `edge-${connection.source}-${connection.sourceHandle}-${connection.target}-${connection.targetHandle}`,
      source: connection.source,
      sourceHandle: connection.sourceHandle,
      target: connection.target,
      targetHandle: connection.targetHandle,
      type: 'smoothstep',
      markerEnd: WORKFLOW_NORMAL_EDGE_MARKER,
      selected: true,
      data: { edgeType },
    },
  ]
  rightCollapsed.value = false
}

function addAgent(position?: XYPosition): void {
  const firstAgent = mainAgents.value[0]
  if (!canAddAgent.value || !firstAgent) return
  const nodeId = nextAgentNodeId()
  const node = newAgentCanvasNode(nodeId, firstAgent.id, position ?? nextAgentPosition())
  node.selected = true
  nodes.value = [
    ...nodes.value.map((item) => ({ ...item, selected: false })),
    node,
  ]
  edges.value = edges.value.map((edge) => ({ ...edge, selected: false }))
  rightCollapsed.value = false
}

function nextAgentPosition(): XYPosition {
  const count = nodes.value.filter((node) => node.data.nodeType === 'agent').length
  return {
    x: 360 + (count % 4) * 260,
    y: 180 + Math.floor(count / 4) * 140,
  }
}

function nextAgentNodeId(): string {
  let index = 1
  while (nodes.value.some((node) => node.id === `agent-${index}`)) index += 1
  return `agent-${index}`
}

function dragOver(event: DragEvent): void {
  if (!canAddAgent.value || !event.dataTransfer?.types.includes(WORKFLOW_NODE_DRAG_MIME)) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'copy'
}

function dropNode(event: DragEvent): void {
  if (
    !canAddAgent.value
    || !flow.value
    || event.dataTransfer?.getData(WORKFLOW_NODE_DRAG_MIME) !== 'agent'
  ) return
  event.preventDefault()
  addAgent(flow.value.screenToFlowCoordinate({ x: event.clientX, y: event.clientY }))
}

function removeAgent(nodeId: string): void {
  nodes.value = nodes.value.filter((node) => node.id !== nodeId)
  edges.value = edges.value.filter((edge) => edge.source !== nodeId && edge.target !== nodeId)
}

function removeEdge(edgeId: string): void {
  edges.value = edges.value.filter((edge) => edge.id !== edgeId)
}

function selectAgent(nodeId: string, mainAgentId: string): void {
  nodes.value = nodes.value.map((node) => (
    node.id === nodeId
      ? { ...node, data: { ...node.data, mainAgentId } }
      : node
  ))
}

function clearSelection(): void {
  nodes.value = nodes.value.map((node) => ({ ...node, selected: false }))
  edges.value = edges.value.map((edge) => ({ ...edge, selected: false }))
}

function showInspector(): void {
  rightCollapsed.value = false
}

function mainAgentName(mainAgentId: string): string {
  return mainAgents.value.find((agent) => agent.id === mainAgentId)?.name
    ?? t('workflows.editor.noMainAgentSelected')
}

async function initializeFlow(instance: VueFlowStore): Promise<void> {
  flow.value = instance
  if (loaded.value) {
    await nextTick()
    await instance.setViewport(savedViewport.value)
  }
}

async function save(): Promise<void> {
  if (!canSave.value || !flow.value) return
  saving.value = true
  try {
    const document = workflowCanvasToDocument(
      nodes.value,
      edges.value,
      flow.value.getViewport(),
    )
    await managementApi.updateWorkflowGraph(workflowId.value, document)
    notify({ tone: 'success', title: t('workflows.editor.saved') })
  } catch (error) {
    notify({
      tone: 'danger',
      title: t('workflows.editor.saveFailed'),
      message: managementError.describe(error).display,
    })
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    const [metadata, graph, agents, catalog] = await Promise.all([
      managementApi.getWorkflow(workflowId.value),
      managementApi.getWorkflowGraph(workflowId.value),
      managementApi.listMainAgents(),
      managementApi.listWorkflowNodeCatalog(),
    ])
    workflow.value = metadata
    mainAgents.value = agents
    nodeCatalog.value = catalog
    stateContract.value = graph.definition.state_contract
    const canvas = workflowDocumentToCanvas(graph, nodeCatalog.value)
    nodes.value = canvas.nodes
    edges.value = canvas.edges
    savedViewport.value = canvas.viewport
    loaded.value = true
    await nextTick()
    await flow.value?.setViewport(canvas.viewport)
  } catch (error) {
    loadError.value = managementError.describe(error).display
  }
})
</script>

<template>
  <div class="workflow-editor-shell">
    <header class="workflow-editor-toolbar">
      <button :aria-label="t('workflows.editor.back')" :title="t('workflows.editor.back')" type="button" @click="router.push('/workflows')">
        <i class="bi bi-chevron-left" aria-hidden="true" />
      </button>
      <h1>{{ workflow?.name ?? t('workflows.editor.title') }}</h1>
      <button :aria-label="t('common.save')" :disabled="!canSave" :title="t('common.save')" type="button" @click="save">
        <i class="bi bi-floppy" aria-hidden="true" />
      </button>
    </header>

    <div
      class="workflow-editor-workspace"
      :data-left-collapsed="leftCollapsed"
      :data-right-collapsed="rightCollapsed"
    >
      <WorkflowNodeLibrary
        :agent="agentCatalogItem"
        :collapsed="leftCollapsed"
        :disabled="!canAddAgent"
        @add-agent="addAgent()"
        @toggle="leftCollapsed = !leftCollapsed"
      />

      <main
        class="workflow-editor-canvas"
        :aria-label="t('workflows.editor.canvas')"
        @dragover="dragOver"
        @drop="dropNode"
      >
        <p v-if="loadError" class="workflow-editor-error" role="alert">{{ loadError }}</p>
        <VueFlow
          v-else
          v-model:nodes="nodes"
          v-model:edges="edges"
          class="workflow-editor-flow"
          :connection-mode="ConnectionMode.Strict"
          default-marker-color="var(--bs-primary)"
          :delete-key-code="['Backspace', 'Delete']"
          :is-valid-connection="isValidConnection"
          :max-zoom="2"
          :min-zoom="0.25"
          @connect="connect"
          @edge-click="showInspector"
          @init="initializeFlow"
          @node-click="showInspector"
          @pane-click="clearSelection"
        >
          <template #node-start>
            <div class="workflow-node workflow-node--terminal">
              <span class="workflow-node-icon" aria-hidden="true"><i class="bi bi-play-fill" /></span>
              <span class="workflow-node-title">{{ t('workflows.editor.start') }}</span>
              <Handle
                :id="normalHandleId('start', true)"
                class="workflow-port workflow-port--normal"
                type="source"
                :aria-label="t('workflows.editor.normalOutput')"
                :connectable="true"
                :position="Position.Right"
              />
            </div>
          </template>

          <template #node-agent="{ data }">
            <div class="workflow-node workflow-node--agent">
              <Handle
                :id="normalHandleId('agent', false)"
                class="workflow-port workflow-port--normal"
                type="target"
                :aria-label="t('workflows.editor.normalInput')"
                :connectable="true"
                :position="Position.Left"
              />
              <div class="workflow-node-header">
                <span class="workflow-node-icon" aria-hidden="true"><i class="bi bi-robot" /></span>
                <span class="workflow-node-title">{{ t('workflows.editor.agent') }}</span>
              </div>
              <span class="workflow-node-summary">{{ mainAgentName(data.mainAgentId) }}</span>
              <Handle
                :id="normalHandleId('agent', true)"
                class="workflow-port workflow-port--normal"
                type="source"
                :aria-label="t('workflows.editor.normalOutput')"
                :connectable="true"
                :position="Position.Right"
              />
            </div>
          </template>

          <template #node-end>
            <div class="workflow-node workflow-node--terminal">
              <Handle
                :id="normalHandleId('end', false)"
                class="workflow-port workflow-port--normal"
                type="target"
                :aria-label="t('workflows.editor.normalInput')"
                :connectable="true"
                :position="Position.Left"
              />
              <span class="workflow-node-icon" aria-hidden="true"><i class="bi bi-stop-fill" /></span>
              <span class="workflow-node-title">{{ t('workflows.editor.end') }}</span>
            </div>
          </template>
        </VueFlow>
      </main>

      <WorkflowInspector
        :collapsed="rightCollapsed"
        :edge="selectedEdge"
        :main-agents="mainAgents"
        :node="selectedNode"
        :state-contract="stateContract"
        :workflow-name="workflow?.name ?? ''"
        @remove-edge="removeEdge"
        @remove-node="removeAgent"
        @toggle="rightCollapsed = !rightCollapsed"
        @update-agent="selectAgent"
      />
    </div>
  </div>
</template>
