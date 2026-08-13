<script setup lang="ts">
import { LteAlert, LteButton } from '@adminlte/vue'
import { computed, onMounted, ref, watch, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import {
  managementApi,
  ManagementApiError,
  type BlockPayload,
  type ManagedComponentType,
  type WorkflowComponentManifest,
  type CapabilityManifest,
  type LocalizedMessagePayload,
  type ModelProviderCatalog,
  type SavedBlock,
  type ValidationReport,
} from '@/api'
import PageShell from '@/components/PageShell.vue'
import RecordPicker from '@/components/RecordPicker.vue'
import SectionNav from '@/components/SectionNav.vue'
import type { SectionNavItem } from '@/components/sectionNav'
import ValidationChecklist from '@/components/ValidationChecklist.vue'
import { useConfirmation } from '@/composables/useConfirmation'
import {
  useConfigurationValidation,
  type ConfigurationValidationState,
} from '@/composables/useConfigurationValidation'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import {
  blockAdapters,
  type BlockDraftBase,
  type CustomMiddlewareCatalogItem,
  type CustomToolCatalogItem,
  type FilesystemImportSource,
  type SkillCatalogItem,
  type ModelDraft,
} from '@/domain/blocks'
import {
  CustomMiddlewareEditor,
  CustomToolEditor,
  ExceptionRetryEditor,
  FilesystemEditor,
  FilesystemPermissionsEditor,
  ModelEditor,
  OutputModeEditor,
  PromptCachingEditor,
  SkillEditor,
  SubagentCapabilityEditor,
  SummarizationEditor,
  SystemPromptEditor,
  TodoListEditor,
  WorkflowInputContextEditor,
  WorkflowPrepareEditor,
} from '@/editors'

interface PageBlockAdapter {
  blank(defaults?: unknown): BlockDraftBase
  fromApi(value: SavedBlock, defaults?: unknown): BlockDraftBase
  toPayload(value: BlockDraftBase, defaults?: unknown): BlockPayload
}

const editorComponents: Record<ManagedComponentType, Component> = {
  model: ModelEditor,
  'system-prompt': SystemPromptEditor,
  filesystem: FilesystemEditor,
  'filesystem-permissions': FilesystemPermissionsEditor,
  'todo-list': TodoListEditor,
  'custom-tool': CustomToolEditor,
  skill: SkillEditor,
  'custom-middleware': CustomMiddlewareEditor,
  'output-mode': OutputModeEditor,
  'exception-retry': ExceptionRetryEditor,
  subagent: SubagentCapabilityEditor,
  summarization: SummarizationEditor,
  'prompt-caching': PromptCachingEditor,
  'workflow-input-context': WorkflowInputContextEditor,
  'workflow-prepare': WorkflowPrepareEditor,
}

const { t } = useI18n()
const managementError = useManagementError()
const route = useRoute()
const router = useRouter()
const { confirm } = useConfirmation()
const { notify } = useToasts()

type ManagedManifest = CapabilityManifest | WorkflowComponentManifest
const manifests = ref<ManagedManifest[]>([])
const editorDefaults = ref<Record<string, unknown>>({})
const activeType = ref<ManagedComponentType | null>(null)
const records = ref<SavedBlock[]>([])
const selectedId = ref('')
const draft = ref<BlockDraftBase | null>(null)
const loading = ref(true)
const saving = ref(false)
const pageError = ref('')
const saveValidation = ref<ValidationReport | null>(null)
const storedRecordInvalid = ref(false)

const { markClean, runAfterDiscard } = useUnsavedChanges(
  () => activeType.value && draft.value
    ? payloadFromDraft(activeType.value, draft.value)
    : draft.value,
  () => ({
    title: t('unsavedChanges.title'),
    description: t('unsavedChanges.description'),
    confirmLabel: t('unsavedChanges.confirm'),
    cancelLabel: t('common.cancel'),
  }),
)

const models = ref<string[]>([])
const loadingModels = ref(false)
const providerCatalog = ref<ModelProviderCatalog | null>(null)
const loadingProviders = ref(false)
const customTools = ref<CustomToolCatalogItem[]>([])
const customToolErrors = ref<Record<string, LocalizedMessagePayload>>({})
const customMiddlewares = ref<CustomMiddlewareCatalogItem[]>([])
const customMiddlewareErrors = ref<Record<string, LocalizedMessagePayload>>({})
const skills = ref<SkillCatalogItem[]>([])
const filesystems = ref<FilesystemImportSource[]>([])
const skillErrors = ref<Record<string, LocalizedMessagePayload>>({})
const loadingResource = ref(false)

let routeSequence = 0
let modelRequestSequence = 0

function invalidateModelCatalog(): void {
  modelRequestSequence += 1
  models.value = []
  loadingModels.value = false
}

function defaultsForType(type: ManagedComponentType | null): unknown {
  const editorKey = manifests.value.find((item) => item.type === type)?.editor_key
  return editorKey ? editorDefaults.value[editorKey] : undefined
}

const activeDefaults = computed(() => defaultsForType(activeType.value))
const currentEditor = computed(() => activeType.value ? editorComponents[activeType.value] : null)
const navigationItems = computed<SectionNavItem[]>(() => manifests.value.map((manifest) => ({
  id: manifest.type,
  label: t(`capabilities.${manifest.type}.label`),
})))

const editorProps = computed<Record<string, unknown>>(() => {
  switch (activeType.value) {
    case 'model':
      return {
        models: models.value,
        loadingModels: loadingModels.value,
        providers: providerCatalog.value?.providers ?? [],
        loadingProviders: loadingProviders.value,
      }
    case 'custom-tool':
      return {
        catalog: customTools.value,
        errors: customToolErrors.value,
        loading: loadingResource.value,
      }
    case 'custom-middleware':
      return {
        catalog: customMiddlewares.value,
        errors: customMiddlewareErrors.value,
        loading: loadingResource.value,
      }
    case 'skill':
      return {
        defaults: activeDefaults.value,
        catalog: skills.value,
        errors: skillErrors.value,
        loading: loadingResource.value,
      }
    case 'filesystem':
    case 'filesystem-permissions':
    case 'todo-list':
    case 'output-mode':
    case 'exception-retry':
    case 'subagent':
    case 'summarization':
    case 'prompt-caching':
    case 'workflow-input-context':
    case 'workflow-prepare':
      return {
        defaults: activeDefaults.value,
        ...(activeType.value === 'filesystem-permissions'
          ? { filesystems: filesystems.value }
          : {}),
      }
    default:
      return {}
  }
})

function adapter(type: ManagedComponentType): PageBlockAdapter {
  return blockAdapters[type] as unknown as PageBlockAdapter
}

function blankDraft(type: ManagedComponentType): BlockDraftBase {
  return adapter(type).blank(defaultsForType(type))
}

function draftFromApi(type: ManagedComponentType, value: SavedBlock): BlockDraftBase {
  return adapter(type).fromApi(value, defaultsForType(type))
}

function payloadFromDraft(type: ManagedComponentType, value: BlockDraftBase): BlockPayload {
  return adapter(type).toPayload(value, defaultsForType(type))
}

function routeId(): string {
  return typeof route.query.id === 'string' ? route.query.id : ''
}

function notifyFailure(titleKey: string, error: unknown): void {
  notify({
    tone: 'danger',
    title: t(titleKey),
    message: managementError.describe(error).display,
  })
}

async function isStoredRecordInvalid(id: string): Promise<boolean> {
  try {
    const report = await managementApi.validateRepository()
    return report.issues.some((issue) => issue.scope === 'block' && issue.owner_id === id)
  } catch {
    return false
  }
}

const { validation } = useConfigurationValidation({
  source: draft,
  buildRequest: () => {
    if (!activeType.value || !draft.value) return null
    return {
      target: {
        kind: 'block',
        type: activeType.value,
        id: draft.value.id,
      },
      payload: payloadFromDraft(activeType.value, draft.value),
    }
  },
  validate: (request) => managementApi.validateDraft(request),
  errorMessage: (error) => managementError.describe(
    error,
    'errors.validationUnavailable',
  ).display,
})

const displayedValidation = computed<ConfigurationValidationState>(() => {
  if (saveValidation.value) return { status: 'invalid', report: saveValidation.value, error: '' }
  return validation.value
})

watch(draft, () => {
  saveValidation.value = null
}, { deep: true })

watch(
  () => {
    if (activeType.value !== 'model' || !draft.value) return null
    const model = draft.value as ModelDraft
    return [model.id, model.provider, model.base_url, model.credential_secret] as const
  },
  (current, previous) => {
    if (!previous) return
    if (
      !current
      || current[0] !== previous[0]
      || current[1] !== previous[1]
      || current[2] !== previous[2]
      || current[3] !== previous[3]
    ) invalidateModelCatalog()
  },
)

async function loadRoute(): Promise<void> {
  if (manifests.value.length === 0) return
  const requestedType = typeof route.params.type === 'string' ? route.params.type : ''
  const manifest = manifests.value.find((item) => item.type === requestedType)
  if (!manifest) {
    const fallback = manifests.value[0]
    if (fallback) await router.replace({ path: `/components/${fallback.type}` })
    return
  }

  invalidateModelCatalog()
  routeSequence += 1
  const sequence = routeSequence
  loading.value = true
  pageError.value = ''
  saveValidation.value = null
  try {
    const [listed, filesystemItems] = await Promise.all([
      managementApi.listBlocks(manifest.type),
      manifest.type === 'filesystem-permissions'
        ? managementApi.listBlocks('filesystem')
        : Promise.resolve([]),
    ])
    if (sequence !== routeSequence) return
    const id = routeId()
    let loadedDraft: BlockDraftBase
    if (id) {
      const [loaded, invalid] = await Promise.all([
        managementApi.getBlock(manifest.type, id),
        isStoredRecordInvalid(id),
      ])
      if (sequence !== routeSequence) return
      loadedDraft = draftFromApi(manifest.type, loaded)
      storedRecordInvalid.value = invalid
    } else {
      loadedDraft = blankDraft(manifest.type)
      storedRecordInvalid.value = false
    }
    activeType.value = manifest.type
    records.value = listed
    filesystems.value = filesystemItems as FilesystemImportSource[]
    draft.value = loadedDraft
    selectedId.value = loadedDraft.id
    markClean()
    if (manifest.type === 'model') await loadProviderCatalog(sequence)
  } catch (error) {
    if (sequence !== routeSequence) return
    pageError.value = managementError.describe(error).display
  } finally {
    if (sequence === routeSequence) loading.value = false
  }
}

async function loadProviderCatalog(sequence = routeSequence): Promise<void> {
  loadingProviders.value = true
  try {
    const loaded = await managementApi.listModelProviders()
    if (sequence !== routeSequence) return
    providerCatalog.value = loaded
  } catch (error) {
    if (sequence !== routeSequence) return
    providerCatalog.value = null
    notifyFailure('components.feedback.providerCatalogFailed', error)
  } finally {
    if (sequence === routeSequence) loadingProviders.value = false
  }
}

async function loadCatalog(): Promise<void> {
  loading.value = true
  pageError.value = ''
  try {
    const catalog = await managementApi.getCatalog()
    manifests.value = [
      ...catalog.block_types,
      ...catalog.workflow_component_types,
    ].sort((left, right) => left.order - right.order)
    editorDefaults.value = catalog.editor_defaults
    await loadRoute()
  } catch (error) {
    pageError.value = managementError.describe(error).display
    loading.value = false
  }
}

async function selectType(type: string): Promise<void> {
  await runAfterDiscard(async () => {
    await router.push({ path: `/components/${type}` })
  })
}

async function selectRecord(id: string): Promise<void> {
  if (!activeType.value) return
  await runAfterDiscard(async () => {
    await router.push({
      path: `/components/${activeType.value}`,
      ...(id ? { query: { id } } : {}),
    })
  })
}

async function startNew(): Promise<void> {
  if (!activeType.value) return
  await runAfterDiscard(async () => {
    await router.push({ path: `/components/${activeType.value}` })
    if (!routeId()) {
      selectedId.value = ''
      draft.value = blankDraft(activeType.value!)
      storedRecordInvalid.value = false
      markClean()
    }
  })
}

async function reset(): Promise<void> {
  if (!activeType.value) return
  await runAfterDiscard(async () => {
    saveValidation.value = null
    try {
      if (draft.value?.id) {
        const id = draft.value.id
        const [loaded, invalid] = await Promise.all([
          managementApi.getBlock(activeType.value!, id),
          isStoredRecordInvalid(id),
        ])
        draft.value = draftFromApi(activeType.value!, loaded)
        storedRecordInvalid.value = invalid
      } else {
        draft.value = blankDraft(activeType.value!)
        storedRecordInvalid.value = false
      }
      markClean()
      notify({ tone: 'info', title: t('components.feedback.reset') })
    } catch (error) {
      notifyFailure('components.feedback.resetFailed', error)
    }
  })
}

function upsertRecord(saved: SavedBlock): void {
  const index = records.value.findIndex((item) => item.id === saved.id)
  if (index === -1) records.value.push(saved)
  else records.value[index] = saved
}

async function save(): Promise<void> {
  if (!activeType.value || !draft.value) return
  const payload = payloadFromDraft(activeType.value, draft.value)
  const existing = records.value.find((record) => record.name === payload.name)
  let targetId = draft.value.id
  if (existing) {
    const accepted = await confirm({
      title: t('components.overwrite.title'),
      description: t('components.overwrite.description', { name: existing.name }),
      confirmLabel: t('components.overwrite.confirm'),
      cancelLabel: t('common.cancel'),
      dangerous: true,
    })
    if (!accepted) return
    targetId = existing.id
  }

  saving.value = true
  saveValidation.value = null
  try {
    const request = targetId ? { id: targetId, ...payload } : payload
    const saved = await managementApi.saveBlock(activeType.value, request)
    draft.value = draftFromApi(activeType.value, saved)
    storedRecordInvalid.value = false
    selectedId.value = saved.id
    upsertRecord(saved)
    markClean()
    await router.replace({
      path: `/components/${activeType.value}`,
      query: { id: saved.id },
    })
    notify({ tone: 'success', title: t('components.feedback.saved') })
  } catch (error) {
    if (error instanceof ManagementApiError && error.validation) {
      saveValidation.value = error.validation
    } else {
      notifyFailure('components.feedback.saveFailed', error)
    }
  } finally {
    saving.value = false
  }
}

function updateDraft(value: BlockDraftBase): void {
  draft.value = value
}

async function refreshResource(): Promise<void> {
  loadingResource.value = true
  try {
    if (activeType.value === 'custom-tool') {
      const result = await managementApi.listCustomTools()
      customTools.value = result.catalog
      customToolErrors.value = result.errors
    } else if (activeType.value === 'custom-middleware') {
      const result = await managementApi.listCustomMiddlewares()
      customMiddlewares.value = result.catalog
      customMiddlewareErrors.value = result.errors
    } else if (activeType.value === 'skill') {
      const result = await managementApi.listSkills()
      skills.value = result.catalog
      skillErrors.value = result.errors
    }
  } catch (error) {
    notifyFailure('components.feedback.resourceFailed', error)
  } finally {
    loadingResource.value = false
  }
}

async function fetchModels(request: {
  provider: string
  baseUrl: string
  credential: string
  blockId: string
}): Promise<void> {
  if (activeType.value !== 'model') return
  const sequence = ++modelRequestSequence
  models.value = []
  loadingModels.value = true
  try {
    const loaded = await managementApi.fetchModels(
      request.provider,
      request.baseUrl,
      request.credential || null,
      request.blockId,
    )
    if (sequence !== modelRequestSequence) return
    const current = draft.value as ModelDraft | null
    if (
      !current
      || current.id !== request.blockId
      || current.provider !== request.provider
      || current.base_url !== request.baseUrl
      || current.credential_secret !== request.credential
    ) return
    models.value = loaded
  } catch (error) {
    if (sequence !== modelRequestSequence) return
    models.value = []
    notifyFailure('components.feedback.modelsFailed', error)
  } finally {
    if (sequence === modelRequestSequence) loadingModels.value = false
  }
}

watch(
  () => [route.params.type, route.query.id],
  () => {
    if (manifests.value.length === 0) return
    const requestedType = typeof route.params.type === 'string' ? route.params.type : ''
    if (requestedType === activeType.value && routeId() === (draft.value?.id ?? '')) return
    void loadRoute()
  },
)

onMounted(() => {
  void loadCatalog()
})
</script>

<template>
  <PageShell>
    <template #actions>
      <LteButton
        :disabled="!draft || loading"
        theme="success"
        type="button"
        @click="startNew"
      >
        {{ t('common.new') }}
      </LteButton>
      <LteButton
        :disabled="!draft || loading"
        theme="warning"
        type="button"
        @click="reset"
      >
        {{ t('common.reset') }}
      </LteButton>
      <LteButton
        :disabled="!draft || loading || saving"
        theme="primary"
        type="button"
        @click="save"
      >
        <span v-if="saving" class="spinner-border spinner-border-sm" aria-hidden="true" />
        {{ t('common.save') }}
      </LteButton>
    </template>

    <template #status>
      <LteAlert
        v-if="pageError"
        data-testid="page-error"
        :title="t('components.feedback.requestFailed')"
        theme="danger"
      >
        {{ pageError }}
      </LteAlert>
    </template>

    <SectionNav
      v-if="navigationItems.length"
      :active-id="activeType ?? ''"
      :aria-label="t('components.navigationLabel')"
      class="mb-3"
      :items="navigationItems"
      layout="inline"
      @select="selectType"
    />

    <div
      v-if="activeType && draft"
      class="row g-3 align-items-start configuration-loading-surface"
      data-testid="component-layout"
      :aria-busy="loading"
      :data-loading="loading"
      :inert="loading || undefined"
    >
      <section class="col-lg-9 component-editor-region" data-testid="editor-region">
        <LteAlert
          v-if="storedRecordInvalid"
          class="mb-3"
          data-testid="stored-invalid-warning"
          :title="t('components.storedInvalidWarning')"
          theme="warning"
        />
        <div class="mb-3">
          <RecordPicker
            :model-value="selectedId"
            :name="draft.name"
            :records="records"
            :disabled="loading"
            @select="selectRecord"
            @update:name="draft.name = $event"
          />
        </div>

        <component
          :is="currentEditor"
          v-bind="editorProps"
          :model-value="draft"
          @fetch-models="fetchModels"
          @refresh="refreshResource"
          @update:model-value="updateDraft"
        />
      </section>

      <aside class="col-lg-3 validation-sidebar" data-testid="inspector-region">
        <ValidationChecklist
          :title="t('components.validationTitle')"
          :validation="displayedValidation"
        />
      </aside>
    </div>
  </PageShell>
</template>
