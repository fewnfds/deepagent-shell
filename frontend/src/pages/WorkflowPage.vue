<script setup lang="ts">
import { LteAlert, LteButton } from '@adminlte/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Connection } from '@vue-flow/core'

import {
  managementApi,
  type EntryScript,
  type EntryScriptDefinition,
  type MainAgent,
  type ValidationReport,
  type Workflow,
  type WorkflowDefinition,
  type WorkflowNode,
  type WorkflowNodeCatalogItem,
} from '@/api'
import PageShell from '@/components/PageShell.vue'
import GraphRunPanel from '@/components/workflow/GraphRunPanel.vue'
import WorkflowCanvas from '@/components/workflow/WorkflowCanvas.vue'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import { blankWorkflow, edgeId, nextNodeId, normalizeWorkflow, nodeCatalogItem } from '@/domain/workflows'

const { t } = useI18n()
const managementError = useManagementError()
const { notify } = useToasts()
const workflows = ref<Workflow[]>([])
const agents = ref<MainAgent[]>([])
const catalog = ref<WorkflowNodeCatalogItem[]>([])
const entries = ref<EntryScript[]>([])
const form = ref<WorkflowDefinition | Workflow>(blankWorkflow())
const selectedId = ref('')
const selectedNodeId = ref('')
const selectedEntryId = ref('')
const entryForm = ref<EntryScriptDefinition>({ name: '', graph_id: '', source: '', enabled: true })
const loading = ref(true)
const saving = ref(false)
const deleting = ref(false)
const entrySaving = ref(false)
const error = ref('')
const validation = ref<ValidationReport | null>(null)
const nodeConfigError = ref('')
const runStatuses = ref<Record<string, string>>({})

const { markClean, runAfterDiscard } = useUnsavedChanges(
  () => form.value,
  () => ({ title: t('unsavedChanges.title'), description: t('unsavedChanges.description'), confirmLabel: t('unsavedChanges.confirm'), cancelLabel: t('common.cancel') }),
)

const isEditing = computed(() => 'id' in form.value && Boolean(form.value.id))
const selectedNode = computed(() => form.value.nodes.find((node) => node.id === selectedNodeId.value))
const selectedDefinition = computed(() => selectedNode.value ? nodeCatalogItem(catalog.value, selectedNode.value.type) : undefined)
const currentGraphId = computed(() => ('id' in form.value ? form.value.id : ''))

function startNew(): void {
  selectedId.value = ''
  selectedNodeId.value = ''
  form.value = blankWorkflow()
  validation.value = null
  markClean()
}

async function loadWorkflow(id: string): Promise<void> {
  if (!id) return startNew()
  await runAfterDiscard(async () => {
    loading.value = true
    try {
      form.value = normalizeWorkflow(await managementApi.getWorkflow(id))
      selectedId.value = id
      selectedNodeId.value = form.value.nodes[0]?.id ?? ''
      validation.value = null
      markClean()
    } catch (cause) { error.value = managementError.describe(cause).display } finally { loading.value = false }
  })
}

function addNode(type: string): void {
  const definition = nodeCatalogItem(catalog.value, type)
  if (!definition) return
  const node: WorkflowNode = { id: nextNodeId(form.value.nodes, type), type, version: definition.version, config: {} }
  if (definition.execution_kind === 'agent') node.config.profile_id = agents.value[0]?.id ?? ''
  if (definition.execution_kind === 'workflow') node.config.graph_id = workflows.value[0]?.id ?? ''
  form.value.nodes.push(node)
  form.value.layout[node.id] = { x: 120 + form.value.nodes.length * 35, y: 120 + form.value.nodes.length * 35 }
  selectedNodeId.value = node.id
}

function removeNode(nodeId: string): void {
  form.value.nodes = form.value.nodes.filter((node) => node.id !== nodeId)
  form.value.entry_nodes = form.value.entry_nodes.filter((id) => id !== nodeId)
  if (!form.value.entry_nodes.length && form.value.nodes[0]) form.value.entry_nodes = [form.value.nodes[0].id]
  form.value.edges = form.value.edges.filter((edge) => edge.source.node !== nodeId && edge.target.node !== nodeId)
  if (selectedNodeId.value === nodeId) selectedNodeId.value = form.value.nodes[0]?.id ?? ''
}

function updateNodeConfig(raw: string): void {
  const node = selectedNode.value
  if (!node) return
  try {
    const value = JSON.parse(raw)
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('object required')
    node.config = value as Record<string, unknown>
    nodeConfigError.value = ''
  } catch { nodeConfigError.value = t('workflow.configJsonInvalid') }
}

function onConnect(connection: Connection): void {
  if (!connection.source || !connection.target || connection.source === connection.target) return
  const sourceNode = form.value.nodes.find((node) => node.id === connection.source)
  const targetNode = form.value.nodes.find((node) => node.id === connection.target)
  const sourceDef = sourceNode && nodeCatalogItem(catalog.value, sourceNode.type)
  const targetDef = targetNode && nodeCatalogItem(catalog.value, targetNode.type)
  const sourcePort = connection.sourceHandle ?? sourceDef?.output_ports[0]?.name
  const targetPort = connection.targetHandle ?? targetDef?.input_ports[0]?.name
  if (!sourcePort || !targetPort) return
  form.value.edges.push({ id: edgeId(form.value.edges), kind: 'control', source: { node: connection.source, port: sourcePort }, target: { node: connection.target, port: targetPort }, condition: null })
}

function moveNode(nodeId: string, x: number, y: number): void { form.value.layout[nodeId] = { x, y } }

function ports(nodeId: string, direction: 'input_ports' | 'output_ports'): string[] {
  const node = form.value.nodes.find((item) => item.id === nodeId)
  return node ? (nodeCatalogItem(catalog.value, node.type)?.[direction] ?? []).map((port) => port.name) : []
}

async function validate(): Promise<boolean> {
  try {
    validation.value = await managementApi.validateWorkflowDraft({ ...form.value, ...('id' in form.value ? { id: form.value.id } : {}) })
    return validation.value.valid
  } catch (cause) { error.value = managementError.describe(cause).display; return false }
}

async function save(): Promise<void> {
  error.value = ''
  if (!(await validate())) return
  saving.value = true
  try {
    const saved = await managementApi.saveWorkflow(form.value)
    form.value = normalizeWorkflow(saved)
    selectedId.value = saved.id
    workflows.value = [...workflows.value.filter((item) => item.id !== saved.id), saved].sort((a, b) => a.name.localeCompare(b.name))
    markClean()
    notify({ tone: 'success', title: t('workflow.saved') })
  } catch (cause) { error.value = managementError.describe(cause).display } finally { saving.value = false }
}

async function deleteWorkflow(): Promise<void> {
  if (!isEditing.value) return
  deleting.value = true
  try {
    await managementApi.deleteWorkflow((form.value as Workflow).id)
    workflows.value = workflows.value.filter((item) => item.id !== (form.value as Workflow).id)
    startNew()
    notify({ tone: 'success', title: t('workflow.deleted') })
  } catch (cause) { error.value = managementError.describe(cause).display } finally { deleting.value = false }
}

function selectEntry(id: string): void {
  selectedEntryId.value = id
  const item = entries.value.find((entry) => entry.id === id)
  entryForm.value = item ? { name: item.name, graph_id: item.graph_id, source: item.source, enabled: item.enabled } : { name: '', graph_id: selectedId.value, source: '', enabled: true }
}

async function saveEntry(): Promise<void> {
  entrySaving.value = true
  try {
    const item = selectedEntryId.value ? await managementApi.saveEntryScript({ ...entryForm.value, id: selectedEntryId.value, revision: entries.value.find((entry) => entry.id === selectedEntryId.value)?.revision }) : await managementApi.saveEntryScript(entryForm.value)
    entries.value = [...entries.value.filter((entry) => entry.id !== item.id), item].sort((a, b) => a.name.localeCompare(b.name))
    selectEntry(item.id)
    notify({ tone: 'success', title: t('workflow.entrySaved') })
  } catch (cause) { error.value = managementError.describe(cause).display } finally { entrySaving.value = false }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [workflowItems, nodeCatalog, mainAgents, entryItems] = await Promise.all([managementApi.listWorkflows(), managementApi.getWorkflowNodeCatalog(), managementApi.listMainAgents(), managementApi.listEntryScripts()])
    workflows.value = workflowItems
    catalog.value = nodeCatalog.nodes
    agents.value = mainAgents
    entries.value = entryItems
    startNew()
  } catch (cause) { error.value = managementError.describe(cause).display } finally { loading.value = false }
}

onMounted(() => { void load() })
</script>

<template>
  <PageShell>
    <template #actions>
      <LteButton theme="success" type="button" @click="startNew">{{ t('common.new') }}</LteButton>
      <LteButton :disabled="saving || loading" theme="primary" type="button" @click="void save">{{ t('common.save') }}</LteButton>
      <LteButton v-if="isEditing" :disabled="deleting" theme="danger" type="button" @click="void deleteWorkflow">{{ t('common.delete') }}</LteButton>
    </template>
    <template #status>
      <LteAlert v-if="error" theme="danger" :title="error" />
      <LteAlert v-if="validation && !validation.valid" theme="warning" :title="t('workflow.validationFailed')" />
    </template>

    <div class="row g-3 align-items-start">
      <section class="col-lg-3">
        <div class="card mb-3">
          <div class="card-header"><h2 class="card-title h5 mb-0">{{ t('workflow.listTitle') }}</h2></div>
          <div class="list-group list-group-flush">
            <button v-for="item in workflows" :key="item.id" class="list-group-item text-start" type="button" @click="void loadWorkflow(item.id)"><span class="d-block fw-semibold">{{ item.name }}</span><span class="d-block small font-monospace text-body-secondary">{{ item.id }}</span></button>
            <div v-if="!loading && !workflows.length" class="list-group-item text-body-secondary">{{ t('workflow.empty') }}</div>
          </div>
        </div>
        <div class="card">
          <div class="card-header"><h2 class="card-title h5 mb-0">{{ t('workflow.entryScripts') }}</h2></div>
          <div class="list-group list-group-flush"><button v-for="entry in entries" :key="entry.id" class="list-group-item text-start" type="button" @click="selectEntry(entry.id)">{{ entry.name }}</button><button class="list-group-item text-start" type="button" @click="selectEntry('')">{{ t('workflow.newEntry') }}</button></div>
          <div class="card-body">
            <label class="form-label">{{ t('workflow.entryName') }}</label><input v-model="entryForm.name" class="form-control font-monospace mb-2">
            <label class="form-label">{{ t('workflow.entryGraph') }}</label><select v-model="entryForm.graph_id" class="form-select mb-2"><option v-for="item in workflows" :key="item.id" :value="item.id">{{ item.name }}</option></select>
            <label class="form-label">{{ t('workflow.entrySource') }}</label><textarea v-model="entryForm.source" class="form-control font-monospace mb-2" rows="6" placeholder="def prepare(messages):\n    return {'messages': messages, 'shared': {}}" />
            <LteButton :disabled="entrySaving" theme="secondary" size="sm" type="button" @click="void saveEntry">{{ t('common.save') }}</LteButton>
          </div>
        </div>
        <div class="card mt-3">
          <div class="card-header"><h2 class="card-title h5 mb-0">{{ t('workflow.nodePalette') }}</h2></div>
          <div class="list-group list-group-flush">
            <button v-for="item in catalog" :key="item.type" class="list-group-item list-group-item-action text-start" type="button" @click="addNode(item.type)">
              <span class="d-block fw-semibold">{{ item.title }}</span>
              <span class="d-block small font-monospace text-body-secondary">{{ item.type }}</span>
            </button>
          </div>
        </div>
      </section>

      <section class="col-lg-9">
        <div class="card mb-3">
          <div class="card-header"><h2 class="card-title h5 mb-0">{{ t('workflow.editorTitle') }}</h2></div>
          <div class="card-body"><div class="row g-3"><div class="col-md-5"><label class="form-label">{{ t('fields.name') }}</label><input v-model="form.name" class="form-control"></div><div class="col-md-3"><label class="form-label">{{ t('workflow.recursionLimit') }}</label><input v-model.number="form.recursion_limit" class="form-control" type="number" min="1" max="10000"></div><div class="col-md-4 d-flex align-items-end"><div class="form-check"><input id="workflow-enabled" v-model="form.enabled" class="form-check-input" type="checkbox"><label class="form-check-label" for="workflow-enabled">{{ t('common.enabled') }}</label></div></div><div class="col-12"><label class="form-label">{{ t('fields.description') }}</label><textarea v-model="form.description" class="form-control" rows="2" /></div></div></div>
        </div>

        <WorkflowCanvas :workflow="form" :catalog="catalog" :statuses="runStatuses" @select="selectedNodeId = $event" @connect="onConnect" @move="moveNode" />

        <div class="row g-3 mt-1">
          <section class="col-lg-5"><div class="card"><div class="card-header"><h2 class="card-title h5 mb-0">{{ t('workflow.inspectorTitle') }}</h2></div><div class="card-body"><template v-if="selectedNode && selectedDefinition"><p class="font-monospace mb-2">{{ selectedNode.id }}</p><p class="small text-body-secondary">{{ selectedDefinition.description }}</p><div class="form-check mb-2"><input :id="`entry-${selectedNode.id}`" v-model="form.entry_nodes" class="form-check-input" type="checkbox" :value="selectedNode.id"><label class="form-check-label" :for="`entry-${selectedNode.id}`">{{ t('workflow.entryNode') }}</label></div><label class="form-label">{{ t('workflow.configJson') }}</label><textarea class="form-control font-monospace" rows="12" :value="JSON.stringify(selectedNode.config, null, 2)" @input="updateNodeConfig(($event.target as HTMLTextAreaElement).value)" /><p v-if="nodeConfigError" class="text-danger small mt-1">{{ nodeConfigError }}</p><label class="form-label mt-2">{{ t('workflow.timeout') }}</label><input v-model.number="selectedNode.timeout_seconds" class="form-control" type="number" min="0.1"><label class="form-label mt-2">{{ t('workflow.maxAttempts') }}</label><input v-model.number="selectedNode.max_attempts" class="form-control" type="number" min="1"><LteButton theme="danger" size="sm" type="button" class="mt-2" @click="removeNode(selectedNode.id)">{{ t('common.delete') }}</LteButton></template><p v-else class="text-body-secondary mb-0">{{ t('workflow.selectNode') }}</p></div></div></section>
          <section class="col-lg-7"><div class="card"><div class="card-header"><h2 class="card-title h5 mb-0">{{ t('workflow.edgesTitle') }}</h2></div><div class="list-group list-group-flush"><div v-for="(edge, index) in form.edges" :key="edge.id" class="list-group-item"><div class="row g-2 align-items-center"><div class="col-md-3 font-monospace small">{{ edge.source.node }}.{{ edge.source.port }} → {{ edge.target.node }}.{{ edge.target.port }}</div><div class="col-md-2"><select v-model="edge.kind" class="form-select form-select-sm"><option value="control">control</option><option value="data">data</option></select></div><div class="col-md-4"><input v-if="edge.kind === 'control'" v-model="edge.condition" class="form-control form-control-sm" placeholder="success / retry / failed"><span v-else class="small text-body-secondary">{{ t('workflow.dataEdgeNoCondition') }}</span></div><div class="col-md-3 text-end"><LteButton theme="danger" size="sm" type="button" @click="form.edges.splice(index, 1)">{{ t('common.delete') }}</LteButton></div></div></div><div v-if="!form.edges.length" class="list-group-item text-body-secondary">{{ t('workflow.noEdges') }}</div></div></div></section>
        </div>
        <GraphRunPanel v-if="isEditing" :graph-id="currentGraphId" :entry-script-id="selectedEntryId ? selectedEntryId : undefined" :statuses="runStatuses" @reset="runStatuses = {}" @status="(nodeId, status) => runStatuses[nodeId] = status" />
      </section>
    </div>
  </PageShell>
</template>
