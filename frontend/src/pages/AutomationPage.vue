<script setup lang="ts">
import { LteAlert, LteButton } from '@adminlte/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import {
  managementApi,
  type AutomationScriptResource,
  type AutomationWorkflowPayload,
  type AutomationWorkflowType,
  type SavedAutomationWorkflow,
} from '@/api'
import AutomationNodeList from '@/components/AutomationNodeList.vue'
import FormField from '@/components/FormField.vue'
import PageShell from '@/components/PageShell.vue'
import RecordPicker from '@/components/RecordPicker.vue'
import SectionNav from '@/components/SectionNav.vue'
import type { SectionNavItem } from '@/components/sectionNav'
import ValidationChecklist from '@/components/ValidationChecklist.vue'
import { useConfirmation } from '@/composables/useConfirmation'
import { useConfigurationValidation } from '@/composables/useConfigurationValidation'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'
import { useUnsavedChanges } from '@/composables/useUnsavedChanges'
import {
  automationWorkflowFromApi,
  automationWorkflowPayload,
  blankAutomationWorkflow,
  type AutomationWorkflowDraft,
  type HookWorkflowDraft,
  type LifecycleWorkflowDraft,
} from '@/domain/automation'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { confirm } = useConfirmation()
const { notify } = useToasts()
const managementError = useManagementError()

const workflowType = computed<AutomationWorkflowType>(() => (
  route.params.type === 'lifecycle-workflow' ? 'lifecycle-workflow' : 'hook-workflow'
))
const records = ref<SavedAutomationWorkflow[]>([])
const scripts = ref<AutomationScriptResource[]>([])
const scriptErrors = ref<Record<string, unknown>>({})
const selectedId = ref('')
const draft = ref<AutomationWorkflowDraft>(blankAutomationWorkflow('hook-workflow'))
const loading = ref(true)
const saving = ref(false)
const pageError = ref('')

const navigationItems = computed<SectionNavItem[]>(() => [
  { id: 'hook-workflow', label: t('automation.hook.title') },
  { id: 'lifecycle-workflow', label: t('automation.lifecycle.title') },
])
const recordOptions = computed(() => records.value.map((record) => ({
  id: record.id,
  name: record.name,
})))
const compatibleScripts = computed(() => scripts.value.filter((script) => (
  script.triggers.includes(workflowType.value === 'hook-workflow' ? 'hook' : 'lifecycle')
)))
const dependencyFailureCount = computed(() => scripts.value.filter(
  (script) => script.dependency_status === 'failed',
).length)
const dependencyRestartCount = computed(() => scripts.value.filter(
  (script) => script.dependency_status === 'restart_required',
).length)
const hookDraft = computed(() => draft.value as HookWorkflowDraft)
const lifecycleDraft = computed(() => draft.value as LifecycleWorkflowDraft)

function currentPayload(): AutomationWorkflowPayload {
  return automationWorkflowPayload(workflowType.value, draft.value)
}

const { markClean, runAfterDiscard } = useUnsavedChanges(
  () => draft.value,
  () => ({
    title: t('unsavedChanges.title'),
    description: t('unsavedChanges.description'),
    confirmLabel: t('unsavedChanges.confirm'),
    cancelLabel: t('common.cancel'),
  }),
)

const { validation, validateNow } = useConfigurationValidation({
  source: draft,
  buildRequest: () => ({
    target: {
      kind: 'automation' as const,
      type: workflowType.value,
      id: draft.value.id,
    },
    payload: currentPayload(),
  }),
  validate: (request) => managementApi.validateDraft(request),
  errorMessage: (error) => managementError.describe(
    error,
    'errors.validationUnavailable',
  ).display,
})

function queryId(): string {
  return typeof route.query.id === 'string' ? route.query.id : ''
}

async function load(id = queryId()): Promise<void> {
  loading.value = true
  pageError.value = ''
  try {
    const [listed, catalog] = await Promise.all([
      managementApi.listAutomationWorkflows(workflowType.value),
      managementApi.listAutomationScripts(),
    ])
    records.value = listed
    scripts.value = catalog.catalog
    scriptErrors.value = catalog.errors
    selectedId.value = id
    draft.value = id
      ? automationWorkflowFromApi(
        workflowType.value,
        await managementApi.getAutomationWorkflow(workflowType.value, id),
      )
      : blankAutomationWorkflow(workflowType.value)
    markClean()
  } catch (error) {
    pageError.value = managementError.describe(error).display
  } finally {
    loading.value = false
  }
}

async function selectType(type: string): Promise<void> {
  await runAfterDiscard(() => router.push(`/automation/${type}`))
}

async function selectRecord(id: string): Promise<void> {
  await runAfterDiscard(async () => {
    await router.push({
      path: `/automation/${workflowType.value}`,
      ...(id ? { query: { id } } : {}),
    })
    await load(id)
  })
}

async function startNew(): Promise<void> {
  await selectRecord('')
}

async function save(): Promise<void> {
  saving.value = true
  pageError.value = ''
  try {
    const state = await validateNow()
    if (state.status !== 'valid') return
    const payload = currentPayload()
    const saved = await managementApi.saveAutomationWorkflow(
      workflowType.value,
      draft.value.id ? { id: draft.value.id, ...payload } : payload,
    )
    const existing = records.value.findIndex((record) => record.id === saved.id)
    if (existing < 0) records.value.push(saved)
    else records.value[existing] = saved
    selectedId.value = saved.id
    draft.value = automationWorkflowFromApi(workflowType.value, saved)
    await router.replace({
      path: `/automation/${workflowType.value}`,
      query: { id: saved.id },
    })
    markClean()
    notify({ tone: 'success', title: t('automation.feedback.saved') })
  } catch (error) {
    pageError.value = managementError.describe(error).display
  } finally {
    saving.value = false
  }
}

async function remove(): Promise<void> {
  if (!draft.value.id) return
  const accepted = await confirm({
    title: t('automation.delete.title'),
    description: t('automation.delete.description', { name: draft.value.name }),
    confirmLabel: t('common.delete'),
    cancelLabel: t('common.cancel'),
    dangerous: true,
  })
  if (!accepted) return
  try {
    await managementApi.deleteAutomationWorkflow(workflowType.value, draft.value.id)
    notify({ tone: 'success', title: t('automation.feedback.deleted') })
    await selectRecord('')
  } catch (error) {
    pageError.value = managementError.describe(error).display
  }
}

onMounted(() => {
  void load()
})

watch(
  () => [route.params.type, route.query.id],
  ([newType, newId], [oldType, oldId]) => {
    if (newType === oldType && newId === oldId) return
    void load(typeof newId === 'string' ? newId : '')
  },
)
</script>

<template>
  <PageShell>
    <template #navigation>
      <SectionNav
        :active-id="workflowType"
        :aria-label="t('automation.title')"
        :items="navigationItems"
        @select="selectType"
      />
    </template>

    <template #actions>
      <LteButton theme="success" type="button" @click="startNew">
        {{ t('common.new') }}
      </LteButton>
      <LteButton :disabled="loading || saving" theme="primary" type="button" @click="save">
        <span v-if="saving" class="spinner-border spinner-border-sm" aria-hidden="true" />
        {{ t('common.save') }}
      </LteButton>
      <LteButton
        v-if="draft.id"
        :disabled="loading || saving"
        theme="danger"
        type="button"
        @click="remove"
      >
        {{ t('common.delete') }}
      </LteButton>
    </template>

    <template #status>
      <LteAlert v-if="pageError" theme="danger" :title="pageError" />
      <LteAlert
        v-else-if="Object.keys(scriptErrors).length"
        theme="warning"
        :title="t('automation.scripts.invalid', { count: Object.keys(scriptErrors).length })"
      />
      <LteAlert
        v-else-if="dependencyFailureCount"
        theme="danger"
        :title="t('automation.scripts.dependenciesFailed', { count: dependencyFailureCount })"
      />
      <LteAlert
        v-else-if="dependencyRestartCount"
        theme="warning"
        :title="t('automation.scripts.dependenciesRestartRequired', { count: dependencyRestartCount })"
      />
    </template>

    <div class="row g-3 align-items-start">
      <section class="col-lg-8">
        <div class="mb-3">
          <RecordPicker
            :disabled="loading"
            :model-value="selectedId"
            :name="draft.name"
            :records="recordOptions"
            @select="selectRecord"
            @update:name="draft.name = $event"
          />
        </div>

        <template v-if="workflowType === 'hook-workflow'">
          <AutomationNodeList
            v-model="hookDraft.hooks.request_prepare"
            field-prefix="hooks.request_prepare"
            :scripts="compatibleScripts"
            :title="t('automation.hook.requestPrepare')"
          />
          <AutomationNodeList
            v-model="hookDraft.hooks.subagent_before_invoke"
            field-prefix="hooks.subagent_before_invoke"
            :scripts="compatibleScripts"
            :title="t('automation.hook.subagentBeforeInvoke')"
          />
          <AutomationNodeList
            v-model="hookDraft.hooks.request_end"
            field-prefix="hooks.request_end"
            :scripts="compatibleScripts"
            :title="t('automation.hook.requestEnd')"
          />
        </template>

        <template v-else>
          <section class="card mb-3">
            <div class="card-body">
              <FormField field-path="interval_seconds" label-key="automation.lifecycle.interval">
                <input
                  v-model.number="lifecycleDraft.interval_seconds"
                  class="form-control"
                  max="86400"
                  min="0.1"
                  step="0.1"
                  type="number"
                >
              </FormField>
            </div>
          </section>
          <AutomationNodeList
            v-model="lifecycleDraft.nodes"
            field-prefix="nodes"
            :scripts="compatibleScripts"
            :title="t('automation.lifecycle.nodes')"
          />
        </template>
      </section>

      <aside class="col-lg-4 validation-sidebar">
        <ValidationChecklist
          :title="t('automation.validationTitle')"
          :validation="validation"
        />
      </aside>
    </div>
  </PageShell>
</template>
