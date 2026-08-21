<script setup lang="ts">
import { LteAlert, LteButton } from '@adminlte/vue'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { managementApi, type ModelConnection, type ModelProviderCatalog } from '@/api'
import PageShell from '@/components/PageShell.vue'
import ModelEditor from '@/editors/ModelEditor.vue'
import { modelAdapter, type ModelDraft } from '@/domain/blocks/model'
import { useConfirmation } from '@/composables/useConfirmation'
import { useManagementError } from '@/composables/useManagementError'

const { t } = useI18n()
const { confirm } = useConfirmation()
const managementError = useManagementError()
const records = ref<ModelConnection[]>([])
const providers = ref<ModelProviderCatalog | null>(null)
const draft = ref<ModelDraft>(modelAdapter.blank())
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const models = ref<string[]>([])
const loadingModels = ref(false)

function select(record: ModelConnection): void { draft.value = modelAdapter.fromApi(record) }
function startNew(): void { draft.value = modelAdapter.blank() }
async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    records.value = await managementApi.listModelConnections()
    providers.value = await managementApi.listModelProviders()
    if (!draft.value.id && records.value[0]) select(records.value[0])
  } catch (cause) { error.value = managementError.describe(cause).display }
  finally { loading.value = false }
}
async function save(): Promise<void> {
  saving.value = true
  try {
    const saved = await managementApi.saveModelConnection({
      ...modelAdapter.toPayload(draft.value),
      ...(draft.value.id ? { id: draft.value.id } : {}),
    })
    records.value = await managementApi.listModelConnections()
    select(saved)
  } catch (cause) { error.value = managementError.describe(cause).display }
  finally { saving.value = false }
}
async function copy(): Promise<void> {
  if (!draft.value.id) return
  try { select(await managementApi.copyModelConnection(draft.value.id, `${draft.value.name} (copy)`)); await load() }
  catch (cause) { error.value = managementError.describe(cause).display }
}
async function remove(): Promise<void> {
  if (!draft.value.id) return
  const accepted = await confirm({ title: t('models.connections.deleteTitle'), description: t('models.connections.deleteDescription', { name: draft.value.name }), confirmLabel: t('common.delete'), cancelLabel: t('common.cancel') })
  if (!accepted) return
  try { await managementApi.deleteModelConnection(draft.value.id); startNew(); await load() }
  catch (cause) { error.value = managementError.describe(cause).display }
}
async function fetchModels(request: { provider: string; baseUrl: string; credential: string; blockId: string }): Promise<void> {
  loadingModels.value = true
  try { models.value = await managementApi.fetchModels(request.provider, request.baseUrl, request.credential || null, request.blockId) }
  catch (cause) { error.value = managementError.describe(cause).display; models.value = [] }
  finally { loadingModels.value = false }
}
onMounted(() => { void load() })
</script>

<template>
  <PageShell>
    <template #actions>
      <LteButton theme="success" type="button" @click="startNew"><i class="bi bi-plus-lg" aria-hidden="true" /> {{ t('common.new') }}</LteButton>
      <LteButton :disabled="!draft.id" theme="secondary" type="button" @click="copy"><i class="bi bi-copy" aria-hidden="true" /> {{ t('common.copy') }}</LteButton>
      <LteButton :disabled="!draft.id" theme="danger" type="button" @click="remove"><i class="bi bi-trash" aria-hidden="true" /> {{ t('common.delete') }}</LteButton>
      <LteButton :disabled="saving || loading" theme="primary" type="button" @click="save"><i class="bi bi-check-lg" aria-hidden="true" /> {{ t('common.save') }}</LteButton>
    </template>
    <template #status><LteAlert v-if="error" theme="danger" :title="t('models.connections.loadFailed')">{{ error }}</LteAlert></template>
    <div class="row g-3 align-items-start">
      <section class="col-lg-4"><div class="card"><header class="card-header"><h2 class="card-title">{{ t('navigation.sections.modelConnections') }}</h2></header><div class="list-group list-group-flush"><button v-for="record in records" :key="record.id" class="list-group-item text-start" type="button" @click="select(record)">{{ record.name }}<small class="d-block text-body-secondary">{{ record.provider }} · {{ record.model }}</small></button><p v-if="!records.length && !loading" class="card-body text-body-secondary mb-0">{{ t('models.connections.empty') }}</p></div></div></section>
      <section class="col-lg-8"><ModelEditor v-model="draft" :models="models" :loading-models="loadingModels" :providers="providers?.providers ?? []" :loading-providers="loading" @fetch-models="fetchModels" /></section>
    </div>
  </PageShell>
</template>
