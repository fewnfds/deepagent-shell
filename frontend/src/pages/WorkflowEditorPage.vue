<script setup lang="ts">
import {
  Handle,
  Position,
  VueFlow,
  type Connection,
  type VueFlowStore,
  type ViewportTransform,
} from '@vue-flow/core'
import { computed, nextTick, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { managementApi, type MainAgent, type Workflow } from '@/api'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'
import {
  newAgentCanvasNode,
  workflowCanvasToDocument,
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
const nodes = ref<WorkflowCanvasNode[]>([])
const edges = ref<WorkflowCanvasEdge[]>([])
const flow = ref<VueFlowStore | null>(null)
const savedViewport = ref<ViewportTransform>({ x: 0, y: 0, zoom: 1 })
const loaded = ref(false)
const saving = ref(false)
const loadError = ref('')
const workflowId = computed(() => String(route.params.id ?? ''))
const hasAgent = computed(() => nodes.value.some((node) => node.data.nodeType === 'agent'))
const canAddAgent = computed(() => loaded.value && !hasAgent.value && mainAgents.value.length > 0)
const canSave = computed(() => (
  loaded.value
  && !saving.value
  && !nodes.value.some((node) => node.data.nodeType === 'agent' && !node.data.mainAgentId)
))

function isValidConnection(connection: Connection): boolean {
  const source = nodes.value.find((node) => node.id === connection.source)
  const target = nodes.value.find((node) => node.id === connection.target)
  if (!source || !target) return false
  const pair = `${source.data.nodeType}:${connection.sourceHandle}->${target.data.nodeType}:${connection.targetHandle}`
  if (pair !== 'start:next->agent:in' && pair !== 'agent:next->end:in') return false
  return !edges.value.some((edge) => (
    edge.source === connection.source
    || edge.target === connection.target
  ))
}

function connect(connection: Connection): void {
  if (!isValidConnection(connection)) return
  edges.value.push({
    id: `edge-${connection.source}-${connection.target}`,
    source: connection.source,
    sourceHandle: connection.sourceHandle,
    target: connection.target,
    targetHandle: connection.targetHandle,
  })
}

function addAgent(): void {
  const firstAgent = mainAgents.value[0]
  if (!canAddAgent.value || !firstAgent) return
  nodes.value.push(newAgentCanvasNode(firstAgent.id))
}

function removeAgent(nodeId: string): void {
  nodes.value = nodes.value.filter((node) => node.id !== nodeId)
  edges.value = edges.value.filter((edge) => edge.source !== nodeId && edge.target !== nodeId)
}

function selectAgent(nodeId: string, event: Event): void {
  const mainAgentId = (event.target as HTMLSelectElement).value
  nodes.value = nodes.value.map((node) => (
    node.id === nodeId
      ? { ...node, data: { ...node.data, mainAgentId } }
      : node
  ))
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
    const [metadata, graph, agents] = await Promise.all([
      managementApi.getWorkflow(workflowId.value),
      managementApi.getWorkflowGraph(workflowId.value),
      managementApi.listMainAgents(),
    ])
    workflow.value = metadata
    mainAgents.value = agents
    const canvas = workflowDocumentToCanvas(graph)
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
      <button
        :aria-label="t('workflows.editor.addAgent')"
        :disabled="!canAddAgent"
        :title="t('workflows.editor.addAgent')"
        type="button"
        @click="addAgent"
      >
        <i class="bi bi-plus-lg" aria-hidden="true" />
      </button>
      <button :aria-label="t('common.save')" :disabled="!canSave" :title="t('common.save')" type="button" @click="save">
        <i class="bi bi-floppy" aria-hidden="true" />
      </button>
    </header>
    <main class="workflow-editor-canvas" :aria-label="t('workflows.editor.canvas')">
      <p v-if="loadError" class="workflow-editor-error" role="alert">{{ loadError }}</p>
      <VueFlow
        v-else
        v-model:nodes="nodes"
        v-model:edges="edges"
        class="workflow-editor-flow"
        :delete-key-code="['Backspace', 'Delete']"
        :is-valid-connection="isValidConnection"
        :max-zoom="2"
        :min-zoom="0.25"
        @connect="connect"
        @init="initializeFlow"
      >
        <template #node-start>
          <div class="workflow-node workflow-node--terminal">
            <span class="workflow-node-title">{{ t('workflows.editor.start') }}</span>
            <Handle id="next" type="source" :position="Position.Right" />
          </div>
        </template>
        <template #node-agent="{ id, data }">
          <div class="workflow-node workflow-node--agent">
            <Handle id="in" type="target" :position="Position.Left" />
            <div class="workflow-node-header">
              <span class="workflow-node-title">{{ t('workflows.editor.agent') }}</span>
              <button
                class="nodrag workflow-node-remove"
                :aria-label="t('workflows.editor.removeAgent')"
                :title="t('workflows.editor.removeAgent')"
                type="button"
                @click="removeAgent(id)"
              >
                <i class="bi bi-trash" aria-hidden="true" />
              </button>
            </div>
            <select
              class="nodrag workflow-node-select"
              :aria-label="t('workflows.editor.selectAgent')"
              :value="data.mainAgentId"
              @change="selectAgent(id, $event)"
            >
              <option v-for="agent in mainAgents" :key="agent.id" :value="agent.id">
                {{ agent.name }}
              </option>
            </select>
            <Handle id="next" type="source" :position="Position.Right" />
          </div>
        </template>
        <template #node-end>
          <div class="workflow-node workflow-node--terminal">
            <Handle id="in" type="target" :position="Position.Left" />
            <span class="workflow-node-title">{{ t('workflows.editor.end') }}</span>
          </div>
        </template>
      </VueFlow>
    </main>
  </div>
</template>
