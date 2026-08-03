<script setup lang="ts">
import { LteAlert, LteButton } from '@adminlte/vue'
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import type { SavedAutomationWorkflow, WorkflowOverride } from '@/api'

import PageShell from '@/components/PageShell.vue'
import RecordPicker from '@/components/RecordPicker.vue'
import FormField from '@/components/FormField.vue'
import SubagentReferencesEditor from '@/components/SubagentReferencesEditor.vue'
import ValidationChecklist from '@/components/ValidationChecklist.vue'
import { useDraftValidation } from '@/composables/useDraftValidation'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import {
  agentAuthoringServiceKey,
  blankSubagent,
  managementAgentAuthoringService,
  normalizeSubagent,
  overrideSelection,
  setOverrideSelection,
  subagentPayload,
  type AgentAuthoringService,
  type CapabilityManifest,
  type CapabilityType,
  type StoredBlock,
  type SubagentProfile,
} from '@/domain/agents'

const INHERIT_VALUE = '__inherit__'
const DISABLED_VALUE = '__disabled__'
const INVALID_VALUE = '__invalid__'

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
const profiles = ref<SubagentProfile[]>([])
const hookWorkflows = ref<SavedAutomationWorkflow[]>([])
const lifecycleWorkflows = ref<SavedAutomationWorkflow[]>([])
const selectedProfileId = ref('')
const form = ref(blankSubagent())
const recordOptions = computed(() => profiles.value.map((profile) => ({
  id: profile.id,
  name: profile.component_name,
})))
let profileLoadSequence = 0

const { markClean, runAfterDiscard } = useUnsavedChanges(
  () => subagentPayload(form.value),
  () => ({
    title: t('unsavedChanges.title'),
    description: t('unsavedChanges.description'),
    confirmLabel: t('unsavedChanges.confirm'),
    cancelLabel: t('common.cancel'),
  }),
)

const { validation, validateNow } = useDraftValidation(
  form,
  () => ({
    target: {
      kind: 'subagent',
      id: form.value.id,
    },
    payload: subagentPayload(form.value),
  }),
  async (request) => {
    if (!service.value) throw new Error(t('agents.serviceUnavailable'))
    return service.value.validateDraft(request)
  },
)

const displayedValidation = computed(() => validation.value.status === 'unavailable'
  ? {
    ...validation.value,
    error: managementError.describe(
      validation.value.error,
      'errors.validationUnavailable',
    ).display,
  }
  : validation.value)

function capabilityBlocks(type: CapabilityType): StoredBlock[] {
  return blocks.value[type] ?? []
}

function selectionValue(type: CapabilityType): string {
  const manifest = manifests.value.find((item) => item.type === type)
  if (!manifest?.subagent_overrideable) {
    return manifest?.subagent_policy === 'inherit' ? INHERIT_VALUE : INVALID_VALUE
  }
  const selection = overrideSelection(form.value, type)
  if (selection.mode === 'inherit') return INHERIT_VALUE
  if (selection.mode === 'disabled') return DISABLED_VALUE
  return selection.block_id
}

function updateSelection(capability: CapabilityManifest, value: string): void {
  if (!capability.subagent_overrideable) return
  if (value === INHERIT_VALUE) {
    setOverrideSelection(form.value, capability.type, 'inherit')
    return
  }
  if (value === DISABLED_VALUE) {
    setOverrideSelection(form.value, capability.type, 'disabled')
    return
  }
  setOverrideSelection(form.value, capability.type, 'replace', value)
}

function workflowSelection(type: 'hook_workflow' | 'lifecycle_workflow'): string {
  const selection = form.value.settings.automation[type]
  if (selection.mode === 'inherit') return INHERIT_VALUE
  if (selection.mode === 'disabled') return DISABLED_VALUE
  return selection.workflow_id
}

function updateWorkflow(
  type: 'hook_workflow' | 'lifecycle_workflow',
  value: string,
): void {
  let selection: WorkflowOverride
  if (value === INHERIT_VALUE) selection = { mode: 'inherit', workflow_id: '' }
  else if (value === DISABLED_VALUE) selection = { mode: 'disabled', workflow_id: '' }
  else selection = { mode: 'replace', workflow_id: value }
  form.value.settings.automation[type] = selection
}

async function startNew(): Promise<void> {
  await runAfterDiscard(() => {
    profileLoadSequence += 1
    selectedProfileId.value = ''
    form.value = blankSubagent()
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
    form.value = blankSubagent()
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
    const loaded = normalizeSubagent(
      await service.value.getSubagent(id),
    )
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

function upsertProfile(saved: SubagentProfile): void {
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
    const payload = subagentPayload(form.value)
    const saved = form.value.id
      ? await service.value.updateSubagent(form.value.id, payload)
      : await service.value.createSubagent(payload)
    const normalized = normalizeSubagent(saved)
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
    const [catalog, profileItems, hooks, lifecycles] = await Promise.all([
      service.value.getCatalog(),
      service.value.listSubagents(),
      service.value.listAutomationWorkflows('hook-workflow'),
      service.value.listAutomationWorkflows('lifecycle-workflow'),
    ])
    manifests.value = [...catalog.block_types].sort((left, right) => left.order - right.order)
    profiles.value = profileItems.map(normalizeSubagent)
    hookWorkflows.value = hooks
    lifecycleWorkflows.value = lifecycles
    const entries = await Promise.all(manifests.value
      .filter((manifest) => manifest.subagent_overrideable)
      .map(async (manifest) => [
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
            :name="form.component_name"
            :records="recordOptions"
            :disabled="loading"
            @select="loadSelected"
            @update:name="form.component_name = $event"
          />
        </div>

        <section class="row g-3 mb-3" :aria-label="t('agents.subagent.identityTitle')">
          <div class="col-md-6">
            <FormField field-path="name">
              <input
                v-model="form.name"
                autocomplete="off"
                class="form-control"
              >
            </FormField>
          </div>
          <div class="col-md-6">
            <FormField field-path="description">
              <textarea v-model="form.description" class="form-control" rows="3" />
            </FormField>
          </div>
        </section>

        <section class="mb-3" :aria-label="t('agents.override.capabilitiesTitle')">
          <div class="row g-3">
            <div
              v-for="capability in manifests"
              :key="capability.type"
              class="col-md-6 col-xxl-4"
              :data-capability="capability.type"
            >
              <section class="card h-100">
                <header class="card-header d-flex flex-wrap align-items-center justify-content-between gap-2">
                <label
                  class="card-title mb-0"
                  :for="`subagent-capability-${capability.type}`"
                >
                  {{ t(`capabilities.${capability.type}.label`) }}
                </label>
                  <span v-if="capability.subagent_overrideable && capability.required" class="badge text-bg-primary ms-auto">
                    {{ t('agents.capability.required') }}
                  </span>
                  <span v-else-if="capability.subagent_overrideable" class="badge text-bg-info ms-auto">
                    {{ t('agents.capability.optional') }}
                  </span>
                </header>
                <div class="card-body">
                <select
                  :id="`subagent-capability-${capability.type}`"
                  class="form-select"
                  :data-testid="`subagent-capability-${capability.type}`"
                  :disabled="!capability.subagent_overrideable"
                  :value="selectionValue(capability.type)"
                  @change="updateSelection(capability, ($event.target as HTMLSelectElement).value)"
                >
                  <template v-if="!capability.subagent_overrideable">
                    <option v-if="capability.subagent_policy === 'inherit'" :value="INHERIT_VALUE">
                      {{ t('agents.override.mode.inherit') }}
                    </option>
                    <option v-else :value="INVALID_VALUE">
                      {{ t('agents.override.mode.invalid') }}
                    </option>
                  </template>
                  <template v-else>
                    <option :value="INHERIT_VALUE">{{ t('agents.override.mode.inherit') }}</option>
                    <option v-if="!capability.required" :value="DISABLED_VALUE">
                      {{ t('agents.override.mode.disabled') }}
                    </option>
                    <option v-for="block in capabilityBlocks(capability.type)" :key="block.id" :value="block.id">
                      {{ block.name }}
                    </option>
                  </template>
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
                  <label class="card-title mb-0" for="subagent-hook-workflow">
                    {{ t('automation.hook.title') }}
                  </label>
                </header>
                <div class="card-body">
                  <select
                    id="subagent-hook-workflow"
                    class="form-select"
                    :value="workflowSelection('hook_workflow')"
                    @change="updateWorkflow('hook_workflow', ($event.target as HTMLSelectElement).value)"
                  >
                    <option :value="INHERIT_VALUE">{{ t('agents.override.mode.inherit') }}</option>
                    <option :value="DISABLED_VALUE">{{ t('agents.override.mode.disabled') }}</option>
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
                  <label class="card-title mb-0" for="subagent-lifecycle-workflow">
                    {{ t('automation.lifecycle.title') }}
                  </label>
                </header>
                <div class="card-body">
                  <select
                    id="subagent-lifecycle-workflow"
                    class="form-select"
                    :value="workflowSelection('lifecycle_workflow')"
                    @change="updateWorkflow('lifecycle_workflow', ($event.target as HTMLSelectElement).value)"
                  >
                    <option :value="INHERIT_VALUE">{{ t('agents.override.mode.inherit') }}</option>
                    <option :value="DISABLED_VALUE">{{ t('agents.override.mode.disabled') }}</option>
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
          v-model:references="form.settings.subagents"
          :profiles="profiles"
          path-prefix="settings.subagents"
        />
      </section>

      <aside class="col-lg-4 validation-sidebar">
        <ValidationChecklist
          :title="t('agents.override.validationTitle')"
          :validation="displayedValidation"
        />
      </aside>
    </div>
  </PageShell>
</template>
