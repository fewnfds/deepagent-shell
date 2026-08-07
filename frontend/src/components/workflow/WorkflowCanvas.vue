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
  type XYPosition,
} from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'
import '@vue-flow/minimap/dist/style.css'
import { ref, watch } from 'vue'

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
const nodeTypes = { 'graph-node': GraphNodeView, 'boundary-node': BoundaryNodeView }
const edgeTypes = { 'control-edge': ControlEdgeView, 'data-edge': DataEdgeView }
// The composable lives in this adapter (the parent of <VueFlow>), so bind it
// explicitly to the same store instead of creating a second, unmounted store.
// Without the stable id, screenToFlowCoordinate() has no viewport element and
// palette drops are converted to { x: 0, y: 0 }.
const flowId = 'workflow-canvas'
const { screenToFlowCoordinate } = useVueFlow(flowId)

function refreshElements(): void {
  nodes.value = toFlowNodes(props.workflow, props.catalog, props.statuses ?? {}, props.entryScript)
  edges.value = toFlowEdges(props.workflow, props.statuses ?? {})
}

watch(() => [props.workflow, props.catalog, props.statuses, props.entryScript], refreshElements, { deep: true, immediate: true })

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

function onNodeDragStop(event: { node: Node }): void {
  if (event.node.id.startsWith('boundary-')) return
  emit('moveNode', event.node.id, event.node.position.x, event.node.position.y)
}

function onDrop(event: DragEvent): void {
  event.preventDefault()
  const type = event.dataTransfer?.getData('application/x-agent-shell-node')
    || event.dataTransfer?.getData('text/plain')
  if (!type || event.clientX === undefined || event.clientY === undefined) return
  emit('addNode', type, screenToFlowCoordinate({ x: event.clientX, y: event.clientY }))
}

function onDragOver(event: DragEvent): void {
  event.preventDefault()
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
  <div class="graph-canvas graph-canvas--workspace" @drop.capture="onDrop" @dragover.capture="onDragOver">
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
      :pan-on-drag="[1, 2]"
      :default-viewport="{ x: 0, y: 0, zoom: 1 }"
      class="graph-canvas__surface"
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
