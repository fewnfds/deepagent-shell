<script setup lang="ts">
import { LteAlert, LteButton } from '@adminlte/vue'
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import type { SavedAutomationWorkflow } from '@/api'

import PageShell from '@/components/PageShell.vue'
import RecordPicker from '@/components/RecordPicker.vue'
import SubagentReferencesEditor from '@/components/SubagentReferencesEditor.vue'
import ValidationChecklist from '@/components/ValidationChecklist.vue'
import { useConfigurationValidation } from '@/composables/useConfigurationValidation'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import {
  agentAuthoringServiceKey,
  blankPrimaryAgent,
  managementAgentAuthoringService,
  normalizePrimaryAgent,
  primaryAgentPayload,
  referenceId,
  setReference,
  type AgentAuthoringService,
  type CapabilityManifest,
  type CapabilityType,
  type PrimaryAgentProfile,
  type StoredBlock,
  type SubagentProfile,
} from '@/domain/agents'

const props = defineProps<{
  service?: AgentAuthoringService
}>()

const { t } = useI18n()
const route = useRoute()
const managementError = useManagementError()
const { notify } = useToasts()
const providedService = inject(agentAuthoringServiceKey, managementAgentAuthoringService)
const service = computed(() => props.service ?? providedService)

const loading = ref(true)
const saving = ref(false)
const feedbackKey = ref('')
const feedbackDetail = ref('')
const manifests = ref<CapabilityManifest[]>([])
const blocks = ref<Record<string, StoredBlock[]>>({})
const profiles = ref<PrimaryAgentProfile[]>([])
const subagentProfiles = ref<SubagentProfile[]>([])
const hookWorkflows = ref<SavedAutomationWorkflow[]>([])
const lifecycleWorkflows = ref<SavedAutomationWorkflow[]>([])
const selectedProfileId = ref('')
const form = ref(blankPrimaryAgent())
let profileLoadSequence = 0

const obsoleteReferences = computed(() => {
  const supported = new Set<string>(manifests.value.map((manifest) => manifest.type))
  return form.value.capability_refs
    .map((reference, index) => ({ index, reference }))
    .filter(({ reference }) => !supported.has(reference.type))
})
const workspaceCapabilityTypes = new Set<CapabilityType>([
  'filesystem',
  'filesystem-permissions',
])
const generalManifests = computed(() => manifests.value.filter(
  (manifest) => !workspaceCapabilityTypes.has(manifest.type),
))

const { markClean, runAfterDiscard } = useUnsavedChanges(
  () => primaryAgentPayload(form.value),
  () => ({
    title: t('unsavedChanges.title'),
    description: t('unsavedChanges.description'),
    confirmLabel: t('unsavedChanges.confirm'),
    cancelLabel: t('common.cancel'),
  }),
)

const { validation, validateNow } = useConfigurationValidation({
  source: form,
  buildRequest: () => ({
    target: {
      kind: 'primary',
      id: form.value.id,
    },
    payload: primaryAgentPayload(form.value),
  }),
  validate: async (request) => {
    if (!service.value) throw new Error(t('agents.serviceUnavailable'))
    return service.value.validateDraft(request)
  },
  errorMessage: (error) => managementError.describe(
    error,
    'errors.validationUnavailable',
  ).display,
})

function capabilityBlocks(type: CapabilityType): StoredBlock[] {
  return blocks.value[type] ?? []
}

function updateReference(type: CapabilityType, value: string): void {
  setReference(form.value, type, value)
}

function removeObsoleteReference(index: number): void {
  form.value.capability_refs.splice(index, 1)
}

async function startNew(): Promise<void> {
  await runAfterDiscard(() => {
    profileLoadSequence += 1
    selectedProfileId.value = ''
    form.value = blankPrimaryAgent()
    feedbackKey.value = ''
    feedbackDetail.value = ''
    notify({ tone: 'info', title: t('agents.feedback.newDraft') })
    markClean()
  })
}

async function loadProfile(id: string): Promise<void> {
  const sequence = ++profileLoadSequence
  if (!id) {
    selectedProfileId.value = ''
    form.value = blankPrimaryAgent()
    feedbackKey.value = ''
    feedbackDetail.value = ''
    notify({ tone: 'info', title: t('agents.feedback.newDraft') })
    markClean()
    return
  }
  if (!service.value) return
  loading.value = true
  feedbackKey.value = ''
  feedbackDetail.value = ''
  try {
    const loaded = normalizePrimaryAgent(await service.value.getPrimaryAgent(id))
    if (sequence !== profileLoadSequence) return
    form.value = loaded
    selectedProfileId.value = loaded.id
    markClean()
  } catch (error) {
    if (sequence !== profileLoadSequence) return
    selectedProfileId.value = form.value.id
    feedbackKey.value = 'agents.feedback.loadFailed'
    feedbackDetail.value = managementError.describe(error).display
  } finally {
    if (sequence === profileLoadSequence) loading.value = false
  }
}

async function loadSelected(value?: string): Promise<void> {
  const id = value ?? selectedProfileId.value
  await runAfterDiscard(() => loadProfile(id))
}

function upsertProfile(saved: PrimaryAgentProfile): void {
  const index = profiles.value.findIndex((profile) => profile.id === saved.id)
  if (index === -1) profiles.value.push(saved)
  else profiles.value[index] = saved
}

async function save(): Promise<void> {
  if (!service.value) {
    feedbackKey.value = 'agents.serviceUnavailable'
    feedbackDetail.value = ''
    return
  }
  saving.value = true
  feedbackKey.value = ''
  feedbackDetail.value = ''
  try {
    await validateNow()
    const payload = primaryAgentPayload(form.value)
    const saved = form.value.id
      ? await service.value.updatePrimaryAgent(form.value.id, payload)
      : await service.value.createPrimaryAgent(payload)
    const normalized = normalizePrimaryAgent(saved)
    form.value = normalized
    selectedProfileId.value = normalized.id
    upsertProfile(normalized)
    markClean()
    notify({ tone: 'success', title: t('agents.feedback.saved') })
  } catch (error) {
    feedbackKey.value = 'agents.feedback.saveFailed'
    feedbackDetail.value = managementError.describe(error).display
  } finally {
    saving.value = false
  }
}

async function loadWorkspace(): Promise<void> {
  if (!service.value) {
    feedbackKey.value = 'agents.serviceUnavailable'
    loading.value = false
    return
  }
  loading.value = true
  try {
    const [catalog, primaryItems, subagentItems, hooks, lifecycles] = await Promise.all([
      service.value.getCatalog(),
      service.value.listPrimaryAgents(),
      service.value.listSubagents(),
      service.value.listAutomationWorkflows('hook-workflow'),
      service.value.listAutomationWorkflows('lifecycle-workflow'),
    ])
    manifests.value = [...catalog.block_types].sort((left, right) => left.order - right.order)
    profiles.value = primaryItems.map(normalizePrimaryAgent)
    subagentProfiles.value = subagentItems
    hookWorkflows.value = hooks
    lifecycleWorkflows.value = lifecycles
    const entries = await Promise.all(manifests.value.map(async (manifest) => [
      manifest.type,
      await service.value?.listBlocks(manifest.type) ?? [],
    ] as const))
    blocks.value = Object.fromEntries(entries)
    const requestedId = typeof route.query.id === 'string' ? route.query.id : ''
    if (requestedId) await loadProfile(requestedId)
    else markClean()
  } catch (error) {
    feedbackKey.value = 'agents.feedback.loadFailed'
    feedbackDetail.value = managementError.describe(error).display
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadWorkspace()
})

watch(
  () => route.query.id,
  (value) => {
    const id = typeof value === 'string' ? value : ''
    if (id === selectedProfileId.value) return
    void loadProfile(id)
  },
)
</script>

<template>
  <PageShell>
    <template #actions>
      <LteButton theme="success" type="button" @click="startNew">
        {{ t('common.new') }}
      </LteButton>
      <LteButton
        :disabled="loading || saving"
        theme="primary"
        type="button"
        @click="save"
      >
        <span v-if="saving" class="spinner-border spinner-border-sm" aria-hidden="true" />
        {{ t('common.save') }}
      </LteButton>
    </template>

    <template #status>
      <LteAlert v-if="feedbackKey" data-testid="page-feedback" theme="danger">
        {{ t(feedbackKey) }}<span v-if="feedbackDetail">{{ t('common.detailSeparator') }}{{ feedbackDetail }}</span>
      </LteAlert>
    </template>

    <div class="row g-3 align-items-start">
      <section class="col-lg-8">
        <div class="mb-3">
          <RecordPicker
            :model-value="selectedProfileId"
            :name="form.name"
            :records="profiles"
            :disabled="loading"
            @select="loadSelected"
            @update:name="form.name = $event"
          />
        </div>

        <section
          v-if="obsoleteReferences.length"
          class="card card-danger card-outline mb-3"
          data-testid="obsolete-capability-references"
        >
          <header class="card-header">
            <h2 class="card-title h5 mb-0 fw-semibold">
              {{ t('agents.obsoleteReferences.title') }}
            </h2>
          </header>
          <ul class="list-group list-group-flush">
            <li
              v-for="item in obsoleteReferences"
              :key="`${item.reference.type}:${item.reference.block_id}:${item.index}`"
              class="list-group-item d-flex align-items-center justify-content-between gap-2"
            >
              <div class="text-break">
                <strong>{{ item.reference.type }}</strong>
                <small class="d-block font-monospace text-body-secondary">
                  {{ item.reference.block_id }}
                </small>
              </div>
              <LteButton
                :aria-label="t('agents.obsoleteReferences.remove')"
                :title="t('agents.obsoleteReferences.remove')"
                class="ms-auto"
                data-action="remove-obsolete-capability-reference"
                size="sm"
                theme="danger"
                type="button"
                @click="removeObsoleteReference(item.index)"
              >
                <i class="bi bi-trash" aria-hidden="true" />
              </LteButton>
            </li>
          </ul>
        </section>

        <section class="card mb-3" :aria-label="t('agents.workspace.title')" data-testid="primary-workspace-card">
          <header class="card-header">
            <h2 class="card-title h5 mb-0 fw-semibold">{{ t('agents.workspace.title') }}</h2>
          </header>
          <div class="card-body">
            <div class="row g-3">
              <div v-for="type in ['filesystem', 'filesystem-permissions'] as CapabilityType[]" :key="type" class="col-md-6">
                <label class="form-label" :for="`primary-capability-${type}`">{{ t(`capabilities.${type}.label`) }}</label>
                <select
                  :id="`primary-capability-${type}`"
                  class="form-select"
                  :data-testid="`primary-capability-${type}`"
                  :value="referenceId(form, type)"
                  @change="updateReference(type, ($event.target as HTMLSelectElement).value)"
                >
                  <option value="">{{ t('agents.capability.notAttached') }}</option>
                  <option v-for="block in capabilityBlocks(type)" :key="block.id" :value="block.id">{{ block.name }}</option>
                </select>
              </div>
            </div>
          </div>
        </section>

        <section class="mb-3" :aria-label="t('agents.primary.capabilitiesTitle')">
          <div class="row g-3">
            <div
              v-for="capability in generalManifests"
              :key="capability.type"
              class="col-md-6 col-xxl-4"
              :data-capability="capability.type"
            >
              <section class="card h-100">
                <header class="card-header d-flex flex-wrap align-items-center justify-content-between gap-2">
                <label
                  class="card-title mb-0"
                  :for="`primary-capability-${capability.type}`"
                >
                  {{ t(`capabilities.${capability.type}.label`) }}
                </label>
                  <span v-if="capability.required" class="badge text-bg-primary ms-auto">
                    {{ t('agents.capability.required') }}
                  </span>
                  <span v-else class="badge text-bg-info ms-auto">{{ t('agents.capability.optional') }}</span>
                </header>
                <div class="card-body">
                <select
                  :id="`primary-capability-${capability.type}`"
                  class="form-select"
                  :value="referenceId(form, capability.type)"
                  @change="updateReference(capability.type, ($event.target as HTMLSelectElement).value)"
                >
                  <option v-if="capability.required" disabled value="">{{ t('common.chooseConfiguration') }}</option>
                  <option v-else value="">{{ t('agents.capability.notAttached') }}</option>
                  <option v-for="block in capabilityBlocks(capability.type)" :key="block.id" :value="block.id">
                    {{ block.name }}
                  </option>
                </select>
                </div>
              </section>
            </div>
          </div>
        </section>

        <section class="mb-3" :aria-label="t('agents.automation.title')">
          <div class="row g-3">
            <div class="col-md-6">
              <section class="card h-100">
                <header class="card-header">
                  <label class="card-title mb-0" for="primary-hook-workflow">
                    {{ t('automation.hook.title') }}
                  </label>
                </header>
                <div class="card-body">
                  <select id="primary-hook-workflow" v-model="form.automation.hook_workflow_id" class="form-select">
                    <option value="">{{ t('agents.capability.notAttached') }}</option>
                    <option v-for="workflow in hookWorkflows" :key="workflow.id" :value="workflow.id">
                      {{ workflow.name }}
                    </option>
                  </select>
                </div>
              </section>
            </div>
            <div class="col-md-6">
              <section class="card h-100">
                <header class="card-header">
                  <label class="card-title mb-0" for="primary-lifecycle-workflow">
                    {{ t('automation.lifecycle.title') }}
                  </label>
                </header>
                <div class="card-body">
                  <select id="primary-lifecycle-workflow" v-model="form.automation.lifecycle_workflow_id" class="form-select">
                    <option value="">{{ t('agents.capability.notAttached') }}</option>
                    <option v-for="workflow in lifecycleWorkflows" :key="workflow.id" :value="workflow.id">
                      {{ workflow.name }}
                    </option>
                  </select>
                </div>
              </section>
            </div>
          </div>
        </section>

        <SubagentReferencesEditor
          v-model:references="form.subagents"
          :profiles="subagentProfiles"
        />

      </section>

      <aside class="col-lg-4 validation-sidebar">
        <ValidationChecklist
          :title="t('agents.primary.validationTitle')"
          :validation="validation"
        />
      </aside>
    </div>
  </PageShell>
</template>
