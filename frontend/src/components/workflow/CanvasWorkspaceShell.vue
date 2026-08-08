<script setup lang="ts">
import type { Connection, XYPosition } from '@vue-flow/core'
import { ref } from 'vue'
import type { EntryScript, Workflow, WorkflowDefinition, WorkflowEdge, WorkflowNode, WorkflowNodeCatalogItem } from '@/api'
import GraphInspector from './GraphInspector.vue'
import GraphRunDock from './GraphRunDock.vue'
import NodePalette from './NodePalette.vue'
import WorkflowCanvas from './WorkflowCanvas.vue'
import WorkspaceToolbar from './WorkspaceToolbar.vue'

const props = defineProps<{
  workflow: WorkflowDefinition | Workflow
  catalog: WorkflowNodeCatalogItem[]
  entries: EntryScript[]
  selectedNode?: WorkflowNode
  selectedDefinition?: WorkflowNodeCatalogItem
  selectedEdge?: WorkflowEdge
  selectedNodeId: string
  selectedEdgeId: string
  selectedEntryId: string
  statuses: Record<string, string>
  graphId: string
  isNew: boolean
  dirty: boolean
  saving: boolean
  validating: boolean
  valid: boolean | null
  nodeConfigError?: string
  canUndo: boolean
  canRedo: boolean
}>()
const emit = defineEmits<{
  back: []
  save: []
  validate: []
  run: []
  newWorkflow: []
  addNode: [type: string, position: XYPosition]
  removeNode: [id: string]
  removeEdge: [id: string]
  connect: [connection: Connection]
  selectNode: [id: string]
  selectEdge: [id: string]
  moveNode: [id: string, x: number, y: number]
  updateNode: [node: WorkflowNode]
  updateEdge: [edge: WorkflowEdge]
  deleteNode: []
  deleteEdge: []
  selectEntry: [id: string]
  toggleEntryNode: [id: string]
  updateWorkflow: [field: 'name' | 'description' | 'enabled' | 'recursion_limit', value: string | number | boolean]
  status: [nodeId: string, value: string]
  resetStatus: []
  undo: []
  redo: []
}>()
const runDockRef = ref<{ start: () => Promise<void> } | null>(null)
const runActive = ref(false)
function startRun(): void { void runDockRef.value?.start() }

function palettePosition(): XYPosition {
  const hasCanvasLayout = Object.hasOwn(props.workflow.layout, 'boundary-api')
    && Object.hasOwn(props.workflow.layout, 'boundary-entry')
  const fallback = props.workflow.nodes.reduce((max, _node, index) => Math.max(max, 620 + index * 260), 620)
  const maxX = props.workflow.nodes.reduce((max, node, index) => (
    Math.max(max, hasCanvasLayout ? (props.workflow.layout[node.id]?.x ?? 620 + index * 260) : 620 + index * 260)
  ), 300)
  return { x: Math.max(fallback, maxX + 320), y: 160 }
}
</script>

<template>
  <div class="canvas-workspace">
    <WorkspaceToolbar
      :dirty="dirty"
      :is-new="isNew"
      :name="workflow['name'] || '未命名 Workflow'"
      :run-active="runActive"
      :can-redo="canRedo"
      :can-undo="canUndo"
      :saving="saving"
      :valid="valid"
      :validating="validating"
      @back="emit('back')"
      @new-workflow="emit('newWorkflow')"
      @run="startRun"
      @redo="emit('redo')"
      @save="emit('save')"
      @validate="emit('validate')"
      @undo="emit('undo')"
    />
    <div class="canvas-workspace__body">
      <NodePalette :catalog="catalog" @add="(type) => emit('addNode', type, palettePosition())" />
      <main class="canvas-workspace__canvas" aria-label="Workflow graph canvas">
        <WorkflowCanvas
          :catalog="catalog"
          :entry-script="entries.find((entry) => entry.id === selectedEntryId)"
          :selected-edge-id="selectedEdgeId"
          :selected-node-id="selectedNodeId"
          :statuses="statuses"
          :workflow="workflow"
          @add-node="emit('addNode', $event[0], $event[1])"
          @connect="emit('connect', $event)"
          @move-node="emit('moveNode', $event[0], $event[1], $event[2])"
          @remove-edge="emit('removeEdge', $event)"
          @remove-node="emit('removeNode', $event)"
          @select-edge="emit('selectEdge', $event)"
          @select-node="emit('selectNode', $event)"
        />
      </main>
      <GraphInspector
        :entries="entries"
        :node-config-error="nodeConfigError"
        :selected-definition="selectedDefinition"
        :selected-edge="selectedEdge"
        :selected-entry-id="selectedEntryId"
        :selected-node="selectedNode"
        :workflow="workflow"
        @delete-edge="emit('deleteEdge')"
        @delete-node="emit('deleteNode')"
        @select-entry="emit('selectEntry', $event)"
        @toggle-entry-node="emit('toggleEntryNode', $event)"
        @update-edge="emit('updateEdge', $event)"
        @update-node="emit('updateNode', $event)"
        @update-workflow="emit('updateWorkflow', $event[0], $event[1])"
      />
    </div>
    <GraphRunDock
      ref="runDockRef"
      :entry-script-id="selectedEntryId || undefined"
      :graph-id="graphId"
      :dirty="dirty"
      :statuses="statuses"
      @reset="emit('resetStatus')"
      @status="emit('status', $event[0], $event[1])"
      @activity="runActive = $event"
    />
  </div>
</template>
