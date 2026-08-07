<script setup lang="ts">
import { LteAlert, LteButton } from '@adminlte/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { managementApi, type EntryScript, type EntryScriptDefinition, type Workflow } from '@/api'
import PageShell from '@/components/PageShell.vue'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'

const { t } = useI18n()
const managementError = useManagementError()
const { notify } = useToasts()
const scripts = ref<EntryScript[]>([])
const workflows = ref<Workflow[]>([])
const form = ref<EntryScriptDefinition>({ name: '', graph_id: '', source: '', enabled: true })
const selectedId = ref('')
const loading = ref(true)
const saving = ref(false)
const deleting = ref(false)
const error = ref('')
const isEditing = computed(() => Boolean(selectedId.value))

function newScript(): void {
  selectedId.value = ''
  form.value = { name: '', graph_id: workflows.value[0]?.id ?? '', source: '', enabled: true }
}

function select(id: string): void {
  selectedId.value = id
  const item = scripts.value.find((script) => script.id === id)
  form.value = item ? { name: item.name, graph_id: item.graph_id, source: item.source, enabled: item.enabled } : { name: '', graph_id: workflows.value[0]?.id ?? '', source: '', enabled: true }
}

async function save(): Promise<void> {
  error.value = ''
  saving.value = true
  try {
    const saved = selectedId.value
      ? await managementApi.saveEntryScript({ ...form.value, id: selectedId.value, revision: scripts.value.find((item) => item.id === selectedId.value)?.revision })
      : await managementApi.saveEntryScript(form.value)
    scripts.value = [...scripts.value.filter((item) => item.id !== saved.id), saved].sort((left, right) => left.name.localeCompare(right.name))
    select(saved.id)
    notify({ tone: 'success', title: t('workflow.entrySaved') })
  } catch (cause) { error.value = managementError.describe(cause).display } finally { saving.value = false }
}

async function remove(): Promise<void> {
  if (!selectedId.value) return
  deleting.value = true
  try {
    await managementApi.deleteEntryScript(selectedId.value)
    scripts.value = scripts.value.filter((item) => item.id !== selectedId.value)
    newScript()
    notify({ tone: 'success', title: t('common.delete') })
  } catch (cause) { error.value = managementError.describe(cause).display } finally { deleting.value = false }
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const [items, graphItems] = await Promise.all([managementApi.listEntryScripts(), managementApi.listWorkflows()])
    scripts.value = items
    workflows.value = graphItems
    select(items[0]?.id ?? '')
    if (!items.length) newScript()
  } catch (cause) { error.value = managementError.describe(cause).display } finally { loading.value = false }
}

onMounted(() => { void load() })
</script>

<template>
  <PageShell>
    <template #actions>
      <LteButton theme="success" type="button" @click="newScript">{{ t('common.new') }}</LteButton>
      <LteButton :disabled="saving || loading" theme="primary" type="button" @click="void save">{{ t('common.save') }}</LteButton>
      <LteButton v-if="isEditing" :disabled="deleting" theme="danger" type="button" @click="void remove">{{ t('common.delete') }}</LteButton>
    </template>
    <template #status><LteAlert v-if="error" theme="danger" :title="error" /></template>
    <div class="row g-3 align-items-start">
      <section class="col-lg-4"><div class="card"><div class="card-header"><h2 class="card-title h5 mb-0">{{ t('workflow.entryScripts') }}</h2></div><div class="list-group list-group-flush"><button v-for="item in scripts" :key="item.id" class="list-group-item list-group-item-action text-start" :data-active="item.id === selectedId || undefined" type="button" @click="select(item.id)"><strong class="d-block">{{ item.name }}</strong><small class="font-monospace text-body-secondary">{{ item.graph_id }}</small></button><div v-if="!scripts.length" class="list-group-item text-body-secondary">暂无入口脚本。</div></div></div></section>
      <section class="col-lg-8"><div class="card"><div class="card-header"><h2 class="card-title h5 mb-0">{{ isEditing ? form.name : '新建入口脚本' }}</h2></div><div class="card-body"><label class="form-label" for="entry-script-name">{{ t('workflow.entryName') }}</label><input id="entry-script-name" v-model="form.name" class="form-control font-monospace mb-1" placeholder="例如 research-entry"><small class="form-text d-block mb-3">只能使用字母（大小写均可）和横杠。</small><label class="form-label" for="entry-script-graph">{{ t('workflow.entryGraph') }}</label><select id="entry-script-graph" v-model="form.graph_id" class="form-select mb-3"><option v-for="item in workflows" :key="item.id" :value="item.id">{{ item.name }}</option></select><label class="form-label" for="entry-script-source">{{ t('workflow.entrySource') }}</label><textarea id="entry-script-source" v-model="form.source" class="form-control font-monospace" rows="16" placeholder="def prepare(messages):&#10;    return {'messages': messages, 'shared': {}}" /><div class="form-check mt-3"><input id="entry-script-enabled" v-model="form.enabled" class="form-check-input" type="checkbox"><label class="form-check-label" for="entry-script-enabled">{{ t('common.enabled') }}</label></div></div></div></section>
    </div>
  </PageShell>
</template>
