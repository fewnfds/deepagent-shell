<script setup lang="ts">
import {
  ConnectionMode,
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
  type SavedBlock,
  type Workflow,
  type WorkflowNodeCatalogItem,
  type WorkflowNodeType,
} from '@/api'
import WorkflowInspector from '@/components/workflow/WorkflowInspector.vue'
import WorkflowNodeLibrary from '@/components/workflow/WorkflowNodeLibrary.vue'
import WorkflowNodeEndpoints from '@/components/workflow/WorkflowNodeEndpoints.vue'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'
import {
  newAgentCanvasNode,
  newConditionRouterCanvasNode,
  nextWorkflowCanvasEdgeId,
  WORKFLOW_NODE_DRAG_MIME,
  WORKFLOW_NORMAL_EDGE_MARKER,
  WORKFLOW_BRANCH_EDGE_MARKER,
  workflowCanvasEdgeTypesBetween,
  workflowCanvasNodeEndpoints,
  workflowCanvasToDocument,
  workflowConnectionEdgeType,
  workflowDocumentToCanvas,
  type WorkflowCanvasEdge,
  type WorkflowCanvasEdgeType,
  type WorkflowCanvasNode,
  type WorkflowEndpointDirection,
} from '@/domain/workflowGraph'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const managementError = useManagementError()
const { notify } = useToasts()
const workflow = ref<Workflow | null>(null)
const mainAgents = ref<MainAgent[]>([])
const conditionRouters = ref<SavedBlock[]>([])
const nodeCatalog = ref<WorkflowNodeCatalogItem[]>([])
const nodes = ref<WorkflowCanvasNode[]>([])
const edges = ref<WorkflowCanvasEdge[]>([])
const flow = ref<VueFlowStore | null>(null)
const stateContract = ref('agent-shell.workflow.agent-invocations.v1')
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
const conditionRouterCatalogItem = computed(() => (
  nodeCatalog.value.find((item) => item.type === 'condition-router') ?? null
))
const canAddConditionRouter = computed(() => (
  loaded.value
  && conditionRouters.value.length > 0
  && conditionRouterCatalogItem.value !== null
))
const canSave = computed(() => (
  loaded.value
  && !saving.value
  && !nodes.value.some((node) => node.data.nodeType === 'agent' && !node.data.mainAgentId)
  && !nodes.value.some((node) => node.data.nodeType === 'condition-router' && !node.data.conditionRouterId)
  && !edges.value.some((edge) => edge.data.edgeType === 'branch' && !edge.data.branchKey)
))
const selectedNode = computed(() => nodes.value.find((node) => node.selected) ?? null)
const selectedEdge = computed(() => (
  selectedNode.value ? null : edges.value.find((edge) => edge.selected) ?? null
))
const selectedNodeInputEndpoints = computed(() => nodeEndpoints(
  selectedNode.value?.data.nodeType,
  'input',
))
const selectedNodeOutputEndpoints = computed(() => nodeEndpoints(
  selectedNode.value?.data.nodeType,
  'output',
))
const selectedEdgeSourceNode = computed(() => (
  nodes.value.find((node) => node.id === selectedEdge.value?.source) ?? null
))
const selectedEdgeTargetNode = computed(() => (
  nodes.value.find((node) => node.id === selectedEdge.value?.target) ?? null
))
const selectedEdgeSourceEndpoints = computed(() => nodeEndpoints(
  selectedEdgeSourceNode.value?.data.nodeType,
  'output',
))
const selectedEdgeTargetEndpoints = computed(() => nodeEndpoints(
  selectedEdgeTargetNode.value?.data.nodeType,
  'input',
))
const selectedEdgeTypeOptions = computed(() => workflowCanvasEdgeTypesBetween(
  selectedEdgeSourceNode.value,
  selectedEdgeTargetNode.value,
  nodeCatalog.value,
))

function nodeEndpoints(
  nodeType: WorkflowNodeType | undefined,
  direction: WorkflowEndpointDirection,
) {
  return nodeType
    ? workflowCanvasNodeEndpoints(nodeCatalog.value, nodeType, direction)
    : []
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
      id: nextWorkflowCanvasEdgeId(edges.value),
      source: connection.source,
      sourceHandle: connection.sourceHandle,
      target: connection.target,
      targetHandle: connection.targetHandle,
      type: 'smoothstep',
      markerEnd: edgeType === 'branch' ? WORKFLOW_BRANCH_EDGE_MARKER : WORKFLOW_NORMAL_EDGE_MARKER,
      animated: edgeType === 'branch',
      class: edgeType === 'branch' ? 'workflow-edge--branch' : undefined,
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

function addConditionRouter(position?: XYPosition): void {
  const firstRouter = conditionRouters.value[0]
  if (!canAddConditionRouter.value || !firstRouter) return
  const nodeId = nextConditionRouterNodeId()
  const node = newConditionRouterCanvasNode(
    nodeId,
    firstRouter.id,
    position ?? nextConditionRouterPosition(),
  )
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

function nextConditionRouterPosition(): XYPosition {
  const count = nodes.value.filter((node) => node.data.nodeType === 'condition-router').length
  return { x: 620 + (count % 3) * 280, y: 180 + Math.floor(count / 3) * 160 }
}

function nextConditionRouterNodeId(): string {
  let index = 1
  while (nodes.value.some((node) => node.id === `condition-router-${index}`)) index += 1
  return `condition-router-${index}`
}

function dragOver(event: DragEvent): void {
  if ((!canAddAgent.value && !canAddConditionRouter.value) || !event.dataTransfer?.types.includes(WORKFLOW_NODE_DRAG_MIME)) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'copy'
}

function dropNode(event: DragEvent): void {
  if (
    (!canAddAgent.value && !canAddConditionRouter.value)
    || !flow.value
    || !['agent', 'condition-router'].includes(event.dataTransfer?.getData(WORKFLOW_NODE_DRAG_MIME) ?? '')
  ) return
  event.preventDefault()
  const position = flow.value.screenToFlowCoordinate({ x: event.clientX, y: event.clientY })
  if (event.dataTransfer?.getData(WORKFLOW_NODE_DRAG_MIME) === 'agent') addAgent(position)
  else addConditionRouter(position)
}

function removeNode(nodeId: string): void {
  nodes.value = nodes.value.filter((node) => node.id !== nodeId)
  edges.value = edges.value.filter((edge) => edge.source !== nodeId && edge.target !== nodeId)
}

function removeEdge(edgeId: string): void {
  edges.value = edges.value.filter((edge) => edge.id !== edgeId)
}

function replaceEdgeEndpoints(
  edgeId: string,
  sourceHandle: string,
  targetHandle: string,
): void {
  const edge = edges.value.find((item) => item.id === edgeId)
  if (!edge) return
  const edgeType = workflowConnectionEdgeType(
    {
      source: edge.source,
      sourceHandle,
      target: edge.target,
      targetHandle,
    },
    nodes.value,
    edges.value.filter((item) => item.id !== edgeId),
    nodeCatalog.value,
  )
  if (!edgeType) return
  edges.value = edges.value.map((item) => (
    item.id === edgeId
      ? {
          ...item,
          sourceHandle,
          targetHandle,
          data: { ...item.data, edgeType },
          markerEnd: edgeType === 'branch' ? WORKFLOW_BRANCH_EDGE_MARKER : WORKFLOW_NORMAL_EDGE_MARKER,
          animated: edgeType === 'branch',
          class: edgeType === 'branch' ? 'workflow-edge--branch' : undefined,
        }
      : item
  ))
}

function selectEdgeType(edgeId: string, edgeType: WorkflowCanvasEdgeType): void {
  const edge = edges.value.find((item) => item.id === edgeId)
  if (!edge) return
  const source = nodes.value.find((node) => node.id === edge.source)
  const target = nodes.value.find((node) => node.id === edge.target)
  if (!source || !target) return
  const sourceEndpoint = nodeEndpoints(source.data.nodeType, 'output')
    .find((endpoint) => endpoint.edge_type === edgeType)
  const targetEndpoint = nodeEndpoints(target.data.nodeType, 'input')
    .find((endpoint) => (endpoint.accepted_edge_types ?? [endpoint.edge_type]).includes(edgeType))
  if (!sourceEndpoint || !targetEndpoint) return
  replaceEdgeEndpoints(edgeId, sourceEndpoint.id, targetEndpoint.id)
}

function selectEdgeSourceEndpoint(edgeId: string, sourceHandle: string): void {
  const edge = edges.value.find((item) => item.id === edgeId)
  if (!edge || !edge.targetHandle) return
  replaceEdgeEndpoints(edgeId, sourceHandle, edge.targetHandle)
}

function selectEdgeTargetEndpoint(edgeId: string, targetHandle: string): void {
  const edge = edges.value.find((item) => item.id === edgeId)
  if (!edge || !edge.sourceHandle) return
  replaceEdgeEndpoints(edgeId, edge.sourceHandle, targetHandle)
}

function selectAgent(nodeId: string, mainAgentId: string): void {
  nodes.value = nodes.value.map((node) => (
    node.id === nodeId
      ? { ...node, data: { ...node.data, mainAgentId } }
      : node
  ))
}

function selectConditionRouter(nodeId: string, conditionRouterId: string): void {
  nodes.value = nodes.value.map((node) => (
    node.id === nodeId
      ? { ...node, data: { ...node.data, conditionRouterId } }
      : node
  ))
}

function updateBranchKey(edgeId: string, branchKey: string): void {
  edges.value = edges.value.map((edge) => (
    edge.id === edgeId && edge.data.edgeType === 'branch'
      ? { ...edge, label: branchKey, data: { ...edge.data, branchKey, branchLabel: branchKey } }
      : edge
  ))
}

function selectDefer(nodeId: string, defer: boolean): void {
  nodes.value = nodes.value.map((node) => (
    node.id === nodeId
      ? { ...node, data: { ...node.data, defer } }
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

function conditionRouterName(conditionRouterId: string): string {
  return conditionRouters.value.find((router) => router.id === conditionRouterId)?.name
    ?? t('workflows.editor.noConditionRouterSelected')
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
    const [metadata, graph, agents, conditionRouterRecords, catalog] = await Promise.all([
      managementApi.getWorkflow(workflowId.value),
      managementApi.getWorkflowGraph(workflowId.value),
      managementApi.listMainAgents(),
      managementApi.listBlocks('condition-router'),
      managementApi.listWorkflowNodeCatalog(),
    ])
    workflow.value = metadata
    mainAgents.value = agents
    conditionRouters.value = conditionRouterRecords
    nodeCatalog.value = catalog
    stateContract.value = graph.definition.state_contract
    const canvas = workflowDocumentToCanvas(graph, nodeCatalog.value, conditionRouters.value)
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
        :condition-router="conditionRouterCatalogItem"
        :collapsed="leftCollapsed"
        :agent-disabled="!canAddAgent"
        :condition-router-disabled="!canAddConditionRouter"
        @add-agent="addAgent()"
        @add-condition-router="addConditionRouter()"
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
              <WorkflowNodeEndpoints
                direction="output"
                :endpoints="nodeEndpoints('start', 'output')"
              />
            </div>
          </template>

          <template #node-agent="{ data }">
            <div class="workflow-node workflow-node--agent">
              <WorkflowNodeEndpoints
                direction="input"
                :endpoints="nodeEndpoints('agent', 'input')"
              />
              <div class="workflow-node-header">
                <span class="workflow-node-icon" aria-hidden="true"><i class="bi bi-robot" /></span>
                <span class="workflow-node-title">{{ t('workflows.editor.agent') }}</span>
              </div>
              <span class="workflow-node-summary">{{ mainAgentName(data.mainAgentId) }}</span>
              <WorkflowNodeEndpoints
                direction="output"
                :endpoints="nodeEndpoints('agent', 'output')"
              />
            </div>
          </template>

          <template #node-condition-router="{ data }">
            <div class="workflow-node workflow-node--condition-router">
              <WorkflowNodeEndpoints direction="input" :endpoints="nodeEndpoints('condition-router', 'input')" />
              <div class="workflow-node-header">
                <span class="workflow-node-icon" aria-hidden="true"><i class="bi bi-circle-half" /></span>
                <span class="workflow-node-title">{{ t('workflows.editor.conditionRouter') }}</span>
              </div>
              <span class="workflow-node-summary">{{ conditionRouterName(data.conditionRouterId ?? '') }}</span>
              <WorkflowNodeEndpoints direction="output" :endpoints="nodeEndpoints('condition-router', 'output')" />
            </div>
          </template>

          <template #node-end>
            <div class="workflow-node workflow-node--terminal">
              <WorkflowNodeEndpoints
                direction="input"
                :endpoints="nodeEndpoints('end', 'input')"
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
        :edge-source-endpoints="selectedEdgeSourceEndpoints"
        :edge-target-endpoints="selectedEdgeTargetEndpoints"
        :edge-type-options="selectedEdgeTypeOptions"
        :input-endpoints="selectedNodeInputEndpoints"
        :main-agents="mainAgents"
        :condition-routers="conditionRouters"
        :node="selectedNode"
        :output-endpoints="selectedNodeOutputEndpoints"
        :state-contract="stateContract"
        :workflow-name="workflow?.name ?? ''"
        @remove-edge="removeEdge"
        @remove-node="removeNode"
        @select-edge-source-endpoint="selectEdgeSourceEndpoint"
        @select-edge-target-endpoint="selectEdgeTargetEndpoint"
        @select-edge-type="selectEdgeType"
        @toggle="rightCollapsed = !rightCollapsed"
        @update-agent="selectAgent"
        @update-condition-router="selectConditionRouter"
        @update-branch-key="updateBranchKey"
        @update-defer="selectDefer"
      />
    </div>
  </div>
</template>
