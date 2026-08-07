<script setup lang="ts">
import { LteAlert, LteButton } from '@adminlte/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  managementApi,
  type MainAgent,
  type ValidationReport,
  type Workflow,
  type WorkflowDefinition,
  type WorkflowNode,
  type WorkflowNodeCatalogItem,
} from '@/api'
import PageShell from '@/components/PageShell.vue'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import {
  blankWorkflow,
  defaultWorkflowPublicId,
  nextNodeId,
  normalizeWorkflow,
  nodeCatalogItem,
} from '@/domain/workflows'

const { t } = useI18n()
const managementError = useManagementError()
const { notify } = useToasts()
const workflows = ref<Workflow[]>([])
const agents = ref<MainAgent[]>([])
const catalog = ref<WorkflowNodeCatalogItem[]>([])
const form = ref<WorkflowDefinition | Workflow>(blankWorkflow())
const selectedId = ref('')
const publicIdEdited = ref(false)
const loading = ref(true)
const saving = ref(false)
const deleting = ref(false)
const error = ref('')
const validation = ref<ValidationReport | null>(null)
const runInput = ref('hello')
const runApiKey = ref('')
const runOutput = ref('')
const runBusy = ref(false)
const nodeConfigErrors = ref<Record<string, string>>({})

const { markClean, runAfterDiscard } = useUnsavedChanges(
  () => form.value,
  () => ({
    title: t('unsavedChanges.title'),
    description: t('unsavedChanges.description'),
    confirmLabel: t('unsavedChanges.confirm'),
    cancelLabel: t('common.cancel'),
  }),
)

const isEditing = computed(() => 'id' in form.value && Boolean(form.value.id))
const nodeTypes = computed(() => catalog.value)

function nodeDefinition(node: WorkflowNode): WorkflowNodeCatalogItem | undefined {
  return nodeCatalogItem(catalog.value, node.type)
}

function inputPorts(nodeId: string): string[] {
  const node = form.value.nodes.find((item) => item.id === nodeId)
  return node ? (nodeDefinition(node)?.input_ports ?? []).map((port) => port.name) : []
}

function outputPorts(nodeId: string): string[] {
  const node = form.value.nodes.find((item) => item.id === nodeId)
  return node ? (nodeDefinition(node)?.output_ports ?? []).map((port) => port.name) : []
}

function updateName(value: string): void {
  form.value.name = value
  if (!publicIdEdited.value) form.value.public_id = defaultWorkflowPublicId(value)
}

function updatePublicId(value: string): void {
  publicIdEdited.value = true
  form.value.public_id = value
}

function startNew(): void {
  selectedId.value = ''
  publicIdEdited.value = false
  form.value = blankWorkflow()
  validation.value = null
  runOutput.value = ''
  markClean()
}

async function loadWorkflow(id: string): Promise<void> {
  if (!id) {
    startNew()
    return
  }
  await runAfterDiscard(async () => {
    loading.value = true
    try {
      form.value = normalizeWorkflow(await managementApi.getWorkflow(id))
      selectedId.value = id
      publicIdEdited.value = true
      validation.value = null
      runOutput.value = ''
      markClean()
    } catch (cause) {
      error.value = managementError.describe(cause).display
    } finally {
      loading.value = false
    }
  })
}

function addNode(type: string): void {
  const definition = nodeCatalogItem(catalog.value, type)
  if (!definition) return
  const node: WorkflowNode = {
    id: nextNodeId(form.value.nodes, type),
    type,
    version: definition.version,
    config: {},
  }
  form.value.nodes.push(node)
  if (type === 'builtin.agent.call') node.config.agent_id = agents.value[0]?.id ?? ''
  if (type === 'builtin.workflow.call') node.config.workflow_id = workflows.value[0]?.id ?? ''
}

function removeNode(nodeId: string): void {
  if (nodeId === 'input' || nodeId === 'output') return
  form.value.nodes = form.value.nodes.filter((node) => node.id !== nodeId)
  form.value.edges = form.value.edges.filter((edge) => edge.source.node !== nodeId && edge.target.node !== nodeId)
}

function updateNodeConfig(node: WorkflowNode, raw: string): void {
  try {
    const value = JSON.parse(raw)
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('object required')
    node.config = value as Record<string, unknown>
    delete nodeConfigErrors.value[node.id]
  } catch {
    nodeConfigErrors.value[node.id] = t('workflow.configJsonInvalid')
  }
}

function addEdge(): void {
  const source = form.value.nodes.find((node) => outputPorts(node.id).length)
  const target = form.value.nodes.find((node) => inputPorts(node.id).length)
  if (!source || !target) return
  form.value.edges.push({
    id: `edge-${form.value.edges.length + 1}`,
    source: { node: source.id, port: outputPorts(source.id)[0] ?? 'messages' },
    target: { node: target.id, port: inputPorts(target.id)[0] ?? 'messages' },
  })
}

function removeEdge(index: number): void {
  form.value.edges.splice(index, 1)
}

async function validate(): Promise<boolean> {
  try {
    validation.value = await managementApi.validateWorkflowDraft({
      ...form.value,
      ...('id' in form.value ? { id: form.value.id } : {}),
    })
    return validation.value.valid
  } catch (cause) {
    error.value = managementError.describe(cause).display
    return false
  }
}

async function save(): Promise<void> {
  error.value = ''
  if (!(await validate())) return
  saving.value = true
  try {
    const saved = await managementApi.saveWorkflow(form.value)
    form.value = normalizeWorkflow(saved)
    selectedId.value = saved.id
    publicIdEdited.value = true
    workflows.value = [
      ...workflows.value.filter((item) => item.id !== saved.id),
      saved,
    ].sort((left, right) => left.name.localeCompare(right.name))
    markClean()
    notify({ tone: 'success', title: t('workflow.saved') })
  } catch (cause) {
    error.value = managementError.describe(cause).display
  } finally {
    saving.value = false
  }
}

async function deleteWorkflow(): Promise<void> {
  if (!isEditing.value) return
  deleting.value = true
  try {
    await managementApi.deleteWorkflow((form.value as Workflow).id)
    workflows.value = workflows.value.filter((item) => item.id !== (form.value as Workflow).id)
    startNew()
    notify({ tone: 'success', title: t('workflow.deleted') })
  } catch (cause) {
    error.value = managementError.describe(cause).display
  } finally {
    deleting.value = false
  }
}

async function runWorkflow(): Promise<void> {
  if (!form.value.public_id || !(await validate())) return
  runBusy.value = true
  runOutput.value = ''
  try {
    const response = await fetch('/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(runApiKey.value ? { Authorization: `Bearer ${runApiKey.value}` } : {}),
      },
      body: JSON.stringify({
        model: form.value.public_id,
        messages: [{ role: 'user', content: runInput.value }],
      }),
    })
    const payload = await response.json() as Record<string, any>
    if (!response.ok) throw new Error(payload.error?.message || t('workflow.runFailed'))
    runOutput.value = JSON.stringify(payload, null, 2)
  } catch (cause) {
    runOutput.value = managementError.describe(cause).display
  } finally {
    runBusy.value = false
  }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [workflowItems, nodeCatalog, mainAgents] = await Promise.all([
      managementApi.listWorkflows(),
      managementApi.getWorkflowNodeCatalog(),
      managementApi.listMainAgents(),
    ])
    workflows.value = workflowItems
    catalog.value = nodeCatalog.nodes
    agents.value = mainAgents
    startNew()
  } catch (cause) {
    error.value = managementError.describe(cause).display
  } finally {
    loading.value = false
  }
}

onMounted(() => { void load() })
</script>

<template>
  <PageShell>
    <template #actions>
      <LteButton theme="success" type="button" @click="startNew">{{ t('common.new') }}</LteButton>
      <LteButton :disabled="saving || loading" theme="primary" type="button" @click="save">{{ t('common.save') }}</LteButton>
      <LteButton v-if="isEditing" :disabled="deleting" theme="danger" type="button" @click="deleteWorkflow">{{ t('common.delete') }}</LteButton>
    </template>
    <template #status>
      <LteAlert v-if="error" theme="danger" :title="error" />
      <LteAlert v-if="validation && !validation.valid" theme="warning" :title="t('workflow.validationFailed')" />
      <pre v-if="validation && !validation.valid" class="border rounded overflow-auto p-3 mb-0"><code>{{ JSON.stringify(validation, null, 2) }}</code></pre>
    </template>

    <div class="row g-3 align-items-start">
      <section class="col-lg-3">
        <div class="card">
          <div class="card-header"><h2 class="card-title h5 mb-0">{{ t('workflow.listTitle') }}</h2></div>
          <div class="list-group list-group-flush">
            <button v-for="item in workflows" :key="item.id" class="list-group-item text-start" type="button" @click="void loadWorkflow(item.id)">
              <span class="d-block fw-semibold">{{ item.name }}<span v-if="item.id === selectedId" class="visually-hidden"> ({{ t('common.selected') }})</span></span>
              <span class="d-block small font-monospace text-body-secondary">{{ item.public_id }}</span>
            </button>
            <div v-if="!loading && !workflows.length" class="list-group-item text-body-secondary">{{ t('workflow.empty') }}</div>
          </div>
        </div>
      </section>

      <section class="col-lg-9">
        <div class="card mb-3">
          <div class="card-header"><h2 class="card-title h5 mb-0">{{ t('workflow.editorTitle') }}</h2></div>
          <div class="card-body">
            <div class="row g-3">
              <div class="col-md-6"><label class="form-label">{{ t('fields.name') }}</label><input class="form-control" :value="form.name" @input="updateName(($event.target as HTMLInputElement).value)"></div>
              <div class="col-md-6"><label class="form-label">{{ t('workflow.publicId') }}</label><input class="form-control font-monospace" :value="form.public_id" @input="updatePublicId(($event.target as HTMLInputElement).value)"></div>
              <div class="col-12"><label class="form-label">{{ t('fields.description') }}</label><textarea v-model="form.description" class="form-control" rows="2" /></div>
              <div class="col-md-6"><label class="form-label">{{ t('workflow.agentBase') }}</label><select v-model="form.agent_base" class="form-select"><option :value="null">{{ t('common.none') }}</option><option v-for="agent in agents" :key="agent.id" :value="{ source: { kind: 'main-agent-profile', id: agent.id }, inherit: [] }">{{ agent.name }}</option></select></div>
              <div class="col-md-6 d-flex align-items-end"><div class="form-check"><input id="workflow-enabled" v-model="form.enabled" class="form-check-input" type="checkbox"><label class="form-check-label" for="workflow-enabled">{{ t('common.enabled') }}</label></div></div>
            </div>
          </div>
        </div>

        <div class="card mb-3">
          <div class="card-header d-flex justify-content-between align-items-center"><h2 class="card-title h5 mb-0">{{ t('workflow.nodesTitle') }}</h2><select class="form-select" @change="addNode(($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''"><option value="">{{ t('workflow.addNode') }}</option><option v-for="item in nodeTypes" :key="item.type" :value="item.type">{{ item.title }}</option></select></div>
          <div class="list-group list-group-flush">
            <div v-for="node in form.nodes" :key="node.id" class="list-group-item">
              <div class="d-flex justify-content-between gap-2 mb-2"><strong class="font-monospace">{{ node.id }}</strong><LteButton v-if="node.id !== 'input' && node.id !== 'output'" theme="danger" size="sm" type="button" @click="removeNode(node.id)">{{ t('common.delete') }}</LteButton></div>
              <div class="row g-3"><div class="col-md-6"><select v-model="node.type" class="form-select"><option v-for="item in nodeTypes" :key="item.type" :value="item.type">{{ item.title }}</option></select></div><div class="col-md-6"><textarea class="form-control font-monospace" rows="2" :value="JSON.stringify(node.config, null, 2)" @input="updateNodeConfig(node, ($event.target as HTMLTextAreaElement).value)" /><small v-if="nodeConfigErrors[node.id]" class="text-danger">{{ nodeConfigErrors[node.id] }}</small></div></div>
            </div>
          </div>
        </div>

        <div class="card mb-3">
          <div class="card-header d-flex justify-content-between align-items-center"><h2 class="card-title h5 mb-0">{{ t('workflow.edgesTitle') }}</h2><LteButton theme="secondary" size="sm" type="button" @click="addEdge">{{ t('workflow.addEdge') }}</LteButton></div>
          <div class="list-group list-group-flush"><div v-for="(edge, index) in form.edges" :key="edge.id" class="list-group-item"><div class="row g-3 align-items-center"><div class="col-md-6"><select v-model="edge.source.node" class="form-select"><option v-for="node in form.nodes" :key="node.id" :value="node.id">{{ node.id }}</option></select><select v-model="edge.source.port" class="form-select mb-1"><option v-for="port in outputPorts(edge.source.node)" :key="port">{{ port }}</option></select></div><div class="col-md-6"><select v-model="edge.target.node" class="form-select"><option v-for="node in form.nodes" :key="node.id" :value="node.id">{{ node.id }}</option></select><select v-model="edge.target.port" class="form-select mb-1"><option v-for="port in inputPorts(edge.target.node)" :key="port">{{ port }}</option></select></div><div class="col-md-6"><LteButton theme="danger" size="sm" type="button" @click="removeEdge(index)">{{ t('common.delete') }}</LteButton></div></div></div><div v-if="!form.edges.length" class="list-group-item text-body-secondary">{{ t('workflow.noEdges') }}</div></div>
        </div>

        <div class="card">
          <div class="card-header"><h2 class="card-title h5 mb-0">{{ t('workflow.runTitle') }}</h2></div>
          <div class="card-body"><label class="form-label">{{ t('workflow.runInput') }}</label><textarea v-model="runInput" class="form-control mb-2" rows="2" /><label class="form-label">{{ t('workflow.runApiKey') }}</label><input v-model="runApiKey" class="form-control mb-1" type="password" autocomplete="off"><p class="form-text">{{ t('workflow.runApiKeyHint') }}</p><LteButton :disabled="runBusy" theme="primary" type="button" @click="runWorkflow">{{ t('workflow.run') }}</LteButton><pre v-if="runOutput" class="border rounded overflow-auto p-3 mt-3 mb-0"><code>{{ runOutput }}</code></pre></div>
        </div>
      </section>
    </div>
  </PageShell>
</template>
