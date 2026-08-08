<script setup lang="ts">
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import {
  VueFlow,
  useVueFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type NodeDragEvent,
  type XYPosition,
} from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'
import { computed, markRaw, ref, watch } from 'vue'

import type { EntryScript, WorkflowDefinition, WorkflowNodeCatalogItem } from '@/api'
import { API_BOUNDARY_ID, ENTRY_BOUNDARY_ID, toFlowEdges, toFlowNodes, type GraphNodeData } from '@/domain/graphWorkspace'
import BoundaryNodeView from './BoundaryNodeView.vue'
import ControlEdgeView from './ControlEdgeView.vue'
import DataEdgeView from './DataEdgeView.vue'
import GraphNodeView from './GraphNodeView.vue'

const props = defineProps<{
  workflow: WorkflowDefinition
  catalog: WorkflowNodeCatalogItem[]
  statuses?: Record<string, string>
  entryScript?: EntryScript
  selectedNodeId?: string
  selectedEdgeId?: string
}>()

const emit = defineEmits<{
  addNode: [type: string, position: XYPosition]
  removeNode: [nodeId: string]
  removeEdge: [edgeId: string]
  connect: [connection: Connection]
  selectNode: [nodeId: string]
  selectEdge: [edgeId: string]
  moveNode: [nodeId: string, x: number, y: number]
}>()

const nodes = ref<Node<GraphNodeData>[]>([])
const edges = ref<Edge[]>([])
const nodeTypes = markRaw({ 'graph-node': GraphNodeView, 'boundary-node': BoundaryNodeView })
const edgeTypes = markRaw({ 'control-edge': ControlEdgeView, 'data-edge': DataEdgeView })
// The composable lives in this adapter (the parent of <VueFlow>), so bind it
// explicitly to the same store instead of creating a second, unmounted store.
// Without the stable id, screenToFlowCoordinate() has no viewport element and
// palette drops are converted to { x: 0, y: 0 }.
const flowId = 'workflow-canvas'
const { screenToFlowCoordinate } = useVueFlow(flowId)

// The graph definition is the persisted source of truth, while Vue Flow owns
// the in-progress pointer interaction.  Do not deep-watch the whole definition:
// a layout-only commit emitted at drag-stop must not rebuild the local nodes and
// make the node jump back under the pointer.
const definitionSignature = computed(() => JSON.stringify({
  nodes: props.workflow.nodes,
  edges: props.workflow.edges,
  entry_nodes: props.workflow.entry_nodes,
  catalog: props.catalog,
  entryScript: props.entryScript
    ? { id: props.entryScript.id, name: props.entryScript.name, enabled: props.entryScript.enabled }
    : null,
}))
const layoutSignature = computed(() => JSON.stringify(props.workflow.layout))
const statusSignature = computed(() => JSON.stringify(props.statuses ?? {}))
let skipNextLayoutRefresh = false

function refreshElements(): void {
  nodes.value = toFlowNodes(props.workflow, props.catalog, props.statuses ?? {}, props.entryScript)
  edges.value = toFlowEdges(props.workflow, props.catalog, props.statuses ?? {})
}

watch(definitionSignature, refreshElements, { immediate: true })

watch(layoutSignature, () => {
  if (skipNextLayoutRefresh) {
    skipNextLayoutRefresh = false
    return
  }
  refreshElements()
})

watch(statusSignature, () => {
  const statuses = props.statuses ?? {}
  nodes.value = nodes.value.map((node) => ({
    ...node,
    data: node.data.boundary ? node.data : { ...node.data, status: statuses[node.id] },
  }))
  edges.value = edges.value.map((edge) => ({
    ...edge,
    animated: edge.data?.system ? false : edge.type === 'control-edge' && Boolean(statuses[edge.source]),
  }))
})

function onNodesChange(changes: NodeChange[]): void {
  for (const change of changes) {
    if (change.type === 'remove' && !change.id.startsWith('boundary-')) emit('removeNode', change.id)
  }
}

function onEdgesChange(changes: EdgeChange[]): void {
  for (const change of changes) {
    if (change.type === 'remove' && !change.id.startsWith('boundary-')) emit('removeEdge', change.id)
  }
}

function onConnect(connection: Connection): void {
  if (!connection.source || !connection.target) return
  if (connection.source.startsWith('boundary-') || connection.target.startsWith('boundary-')) return
  emit('connect', connection)
}

function onNodeDragStop(event: NodeDragEvent): void {
  // The next layout change is the one just emitted by this pointer gesture.
  // Keep Vue Flow's final local position and let the parent persist it without
  // rebuilding the projection a second time.
  skipNextLayoutRefresh = true
  emit('moveNode', event.node.id, event.node.position.x, event.node.position.y)
}

function onDrop(event: DragEvent): void {
  event.preventDefault()
  event.stopPropagation()
  const type = event.dataTransfer?.getData('application/vueflow')
    || event.dataTransfer?.getData('application/x-agent-shell-node')
    || event.dataTransfer?.getData('text/plain')
  if (!type || event.clientX === undefined || event.clientY === undefined) return
  emit('addNode', type, screenToFlowCoordinate({ x: event.clientX, y: event.clientY }))
}

function onDragOver(event: DragEvent): void {
  event.preventDefault()
  event.stopPropagation()
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy'
}

function onPaneClick(): void {
  emit('selectNode', '')
  emit('selectEdge', '')
}

function onNodeClick(event: { node: Node }): void {
  if (!event.node.id.startsWith('boundary-')) emit('selectNode', event.node.id)
}

function onEdgeClick(event: { edge: Edge }): void {
  if (!event.edge.id.startsWith('boundary-')) emit('selectEdge', event.edge.id)
}

</script>

<template>
  <div class="graph-canvas graph-canvas--workspace" @drop="onDrop">
    <VueFlow
      :id="flowId"
      v-model:edges="edges"
      v-model:nodes="nodes"
      :node-types="nodeTypes"
      :edge-types="edgeTypes"
      :delete-key-code="['Backspace', 'Delete']"
      :nodes-draggable="true"
      :nodes-connectable="true"
      :elements-selectable="true"
      :selection-on-drag="true"
      :select-nodes-on-drag="true"
      :pan-on-drag="[2, 3]"
      fit-view-on-init
      :default-viewport="{ x: 0, y: 0, zoom: 1 }"
      class="graph-canvas__surface"
      @dragover="onDragOver"
      @drop="onDrop"
      @nodes-change="onNodesChange"
      @edges-change="onEdgesChange"
      @connect="onConnect"
      @node-click="onNodeClick"
      @edge-click="onEdgeClick"
      @node-drag-stop="onNodeDragStop"
      @pane-click="onPaneClick"
    >
      <Background pattern-color="var(--bs-border-color-translucent)" :gap="24" />
      <Controls position="bottom-left" />
      <MiniMap position="bottom-right" />
    </VueFlow>
  </div>
</template>
