<script setup lang="ts">
import { LteAlert, LteButton } from '@adminlte/vue'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { managementApi, type AutoRoot, type AutoRootDefinition, type MainAgent, type Workflow } from '@/api'
import PageShell from '@/components/PageShell.vue'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'
import { blankAutoRoot, defaultAutoPublicId, normalizeAutoRoot } from '@/domain/autos'

const { t } = useI18n()
const managementError = useManagementError()
const { notify } = useToasts()
const roots = ref<AutoRoot[]>([])
const agents = ref<MainAgent[]>([])
const workflows = ref<Workflow[]>([])
const form = ref<AutoRootDefinition | AutoRoot>(blankAutoRoot())
const selectedId = ref('')
const publicIdEdited = ref(false)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const testMessages = ref('hello')
const routeResult = ref('')
const testing = ref(false)

function updateName(value: string): void {
  form.value.name = value
  if (!publicIdEdited.value) form.value.public_id = defaultAutoPublicId(value)
}

function updatePublicId(value: string): void {
  publicIdEdited.value = true
  form.value.public_id = value
}

function startNew(): void {
  selectedId.value = ''
  publicIdEdited.value = false
  form.value = blankAutoRoot()
  routeResult.value = ''
}

async function loadRoot(id: string): Promise<void> {
  if (!id) return startNew()
  try {
    form.value = normalizeAutoRoot(await managementApi.getAutoRoot(id))
    selectedId.value = id
    publicIdEdited.value = true
    routeResult.value = ''
  } catch (cause) {
    error.value = managementError.describe(cause).display
  }
}

async function save(): Promise<void> {
  saving.value = true
  error.value = ''
  try {
    const saved = await managementApi.saveAutoRoot(form.value)
    form.value = normalizeAutoRoot(saved)
    selectedId.value = saved.id
    roots.value = [...roots.value.filter((item) => item.id !== saved.id), saved].sort((a, b) => a.name.localeCompare(b.name))
    publicIdEdited.value = true
    notify({ tone: 'success', title: t('auto.saved') })
  } catch (cause) {
    error.value = managementError.describe(cause).display
  } finally {
    saving.value = false
  }
}

async function remove(): Promise<void> {
  if (!selectedId.value) return
  try {
    await managementApi.deleteAutoRoot(selectedId.value)
    roots.value = roots.value.filter((item) => item.id !== selectedId.value)
    startNew()
    notify({ tone: 'success', title: t('auto.deleted') })
  } catch (cause) {
    error.value = managementError.describe(cause).display
  }
}

async function testRoute(): Promise<void> {
  if (!selectedId.value) {
    routeResult.value = t('auto.saveBeforeTest')
    return
  }
  testing.value = true
  try {
    const messages = [{ role: 'user', content: testMessages.value }]
    const result = await managementApi.resolveAutoRoot(selectedId.value, messages)
    routeResult.value = JSON.stringify(result, null, 2)
  } catch (cause) {
    routeResult.value = managementError.describe(cause).display
  } finally {
    testing.value = false
  }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [autoRoots, mainAgents, workflowItems] = await Promise.all([
      managementApi.listAutoRoots(), managementApi.listMainAgents(), managementApi.listWorkflows(),
    ])
    roots.value = autoRoots
    agents.value = mainAgents
    workflows.value = workflowItems
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
    <template #actions><LteButton theme="success" type="button" @click="startNew">{{ t('common.new') }}</LteButton><LteButton :disabled="saving" theme="primary" type="button" @click="save">{{ t('common.save') }}</LteButton><LteButton v-if="selectedId" theme="danger" type="button" @click="remove">{{ t('common.delete') }}</LteButton></template>
    <template #status><LteAlert v-if="error" theme="danger" :title="error" /></template>
    <div class="row g-3 align-items-start">
      <section class="col-lg-3"><div class="card"><div class="card-header"><h2 class="card-title h5 mb-0">{{ t('auto.listTitle') }}</h2></div><div class="list-group list-group-flush"><button v-for="item in roots" :key="item.id" class="list-group-item text-start" type="button" @click="void loadRoot(item.id)"><span class="d-block fw-semibold">{{ item.name }}<span v-if="item.id === selectedId" class="visually-hidden"> ({{ t('common.selected') }})</span></span><span class="d-block small font-monospace text-body-secondary">{{ item.public_id }}</span></button><div v-if="!loading && !roots.length" class="list-group-item text-body-secondary">{{ t('auto.empty') }}</div></div></div></section>
      <section class="col-lg-9"><div class="card mb-3"><div class="card-header"><h2 class="card-title h5 mb-0">{{ t('auto.editorTitle') }}</h2></div><div class="card-body"><div class="row g-3"><div class="col-md-6"><label class="form-label">{{ t('fields.name') }}</label><input class="form-control" :value="form.name" @input="updateName(($event.target as HTMLInputElement).value)"></div><div class="col-md-6"><label class="form-label">{{ t('auto.publicId') }}</label><input class="form-control font-monospace" :value="form.public_id" @input="updatePublicId(($event.target as HTMLInputElement).value)"></div><div class="col-12"><label class="form-label">{{ t('auto.source') }}</label><textarea v-model="form.source" class="form-control font-monospace" rows="12" spellcheck="false" /></div><div class="col-12"><div class="form-check"><input id="auto-enabled" v-model="form.enabled" class="form-check-input" type="checkbox"><label class="form-check-label" for="auto-enabled">{{ t('common.enabled') }}</label></div></div></div></div></div><div class="card"><div class="card-header"><h2 class="card-title h5 mb-0">{{ t('auto.testTitle') }}</h2></div><div class="card-body"><p class="text-body-secondary">{{ t('auto.testHint') }}</p><textarea v-model="testMessages" class="form-control mb-2" rows="2" /><LteButton :disabled="testing || !selectedId" theme="primary" type="button" @click="testRoute">{{ t('auto.test') }}</LteButton><pre v-if="routeResult" class="border rounded overflow-auto p-3 mt-3 mb-0"><code>{{ routeResult }}</code></pre></div></div></section>
    </div>
  </PageShell>
</template>
