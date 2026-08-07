<script setup lang="ts">
import { VueFlow, type Connection, type Edge, type Node } from '@vue-flow/core'
import '@vue-flow/core/dist/style.css'
import { computed } from 'vue'

import type { WorkflowDefinition, WorkflowNodeCatalogItem } from '@/api'
import GraphNodeView from './GraphNodeView.vue'

const props = defineProps<{
  workflow: WorkflowDefinition
  catalog: WorkflowNodeCatalogItem[]
  statuses?: Record<string, string>
}>()

const emit = defineEmits<{
  connect: [connection: Connection]
  select: [nodeId: string]
  move: [nodeId: string, x: number, y: number]
}>()

const nodeTypes = { 'graph-node': GraphNodeView }
const canvasNodes = computed<Node[]>(() => props.workflow.nodes.map((node) => {
  const position = props.workflow.layout[node.id] ?? { x: 80, y: 80 }
  const definition = props.catalog.find((item) => item.type === node.type)
  return {
    id: node.id,
    type: 'graph-node',
    position,
    data: {
      label: node.id,
      type: definition?.title ?? node.type,
      status: props.statuses?.[node.id],
      input_ports: definition?.input_ports.map((port) => port.name) ?? [],
      output_ports: definition?.output_ports.map((port) => port.name) ?? [],
    },
  }
}))
const canvasEdges = computed<Edge[]>(() => props.workflow.edges.map((edge) => ({
  id: edge.id,
  source: edge.source.node,
  target: edge.target.node,
  sourceHandle: edge.source.port,
  targetHandle: edge.target.port,
  label: edge.kind,
  animated: edge.kind === 'control' && Boolean(props.statuses?.[edge.source.node]),
  data: edge,
})))

function onConnect(connection: Connection): void {
  emit('connect', connection)
}

function onNodeDragStop(event: { node: Node }): void {
  emit('move', event.node.id, event.node.position.x, event.node.position.y)
}
</script>

<template>
  <div class="graph-canvas">
    <VueFlow
      :nodes="canvasNodes"
      :edges="canvasEdges"
      :node-types="nodeTypes"
      fit-view-on-init
      class="graph-canvas__surface"
      @connect="onConnect"
      @node-click="({ node }) => emit('select', node.id)"
      @node-drag-stop="onNodeDragStop"
    >
    </VueFlow>
  </div>
</template>
