<script setup lang="ts">
import { LteAlert, LteButton, LteInput, LteTextarea } from '@adminlte/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import {
  managementApi,
  type SavedBlock,
  type Workflow,
  type WorkflowPayload,
  type WorkflowRole,
} from '@/api'
import DataTableWorkbench from '@/components/data-table/DataTableWorkbench.vue'
import type { DataTableConfig } from '@/components/data-table/types'
import FormField from '@/components/FormField.vue'
import ModalHost from '@/components/ModalHost.vue'
import PageShell from '@/components/PageShell.vue'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'

const { t } = useI18n()
const router = useRouter()
const props = defineProps<{ workflowRole: WorkflowRole }>()
const managementError = useManagementError()
const { notify } = useToasts()

const table = ref<{ reload: () => Promise<void> } | null>(null)
const editingId = ref('')
const formOpen = ref(false)
const saving = ref(false)
const formError = ref('')
const workflowEventOutputs = ref<SavedBlock[]>([])
const form = ref<WorkflowPayload>(blankWorkflow())

function blankWorkflow(): WorkflowPayload {
  return {
    name: '',
    workflow_role: props.workflowRole,
    description: '',
    workflow_event_output_id: null,
    recursion_limit: 100,
    execution_timeout_seconds: 600,
    max_concurrency: 16,
  }
}

function openNew(): void {
  editingId.value = ''
  form.value = blankWorkflow()
  formError.value = ''
  formOpen.value = true
}

function openEdit(workflow: Workflow): void {
  editingId.value = workflow.id
  form.value = {
    name: workflow.name,
    workflow_role: workflow.workflow_role,
    description: workflow.description,
    workflow_event_output_id: workflow.workflow_event_output_id,
    recursion_limit: workflow.recursion_limit,
    execution_timeout_seconds: workflow.execution_timeout_seconds,
    max_concurrency: workflow.max_concurrency,
  }
  formError.value = ''
  formOpen.value = true
}

function closeForm(): void {
  if (saving.value) return
  formOpen.value = false
}

async function save(): Promise<void> {
  if (saving.value) return
  saving.value = true
  formError.value = ''
  try {
    const payload: WorkflowPayload = {
      name: form.value.name.trim(),
      workflow_role: props.workflowRole,
      description: form.value.description.trim(),
      workflow_event_output_id: form.value.workflow_event_output_id || null,
      recursion_limit: Number(form.value.recursion_limit),
      execution_timeout_seconds: Number(form.value.execution_timeout_seconds),
      max_concurrency: Number(form.value.max_concurrency),
    }
    if (editingId.value) await managementApi.updateWorkflow(editingId.value, payload)
    else await managementApi.createWorkflow(payload)
    formOpen.value = false
    notify({ tone: 'success', title: t('workflows.saved') })
    await table.value?.reload()
  } catch (error) {
    formError.value = managementError.describe(error).display
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  const [blocksResult] = await Promise.allSettled([
    Promise.all([
      managementApi.listBlocks('workflow-event-output'),
    ]),
  ])
  if (blocksResult.status === 'fulfilled') {
    ;[workflowEventOutputs.value] = blocksResult.value
  } else {
    notify({
      tone: 'danger',
      title: t('workflows.componentLoadFailed'),
      message: managementError.describe(blocksResult.reason).display,
    })
  }
})

const tableConfig = computed<DataTableConfig<Workflow>>(() => ({
  id: `workflows-${props.workflowRole}`,
  ariaLabel: () => t(`workflows.${props.workflowRole}TableAriaLabel`),
  emptyMessage: () => t(`workflows.${props.workflowRole}Empty`),
  filteredEmptyMessage: () => t('workflows.filteredEmpty'),
  loadErrorTitle: () => t('workflows.loadFailed'),
  rowKey: (row) => row.id,
  provider: { mode: 'local', load: () => managementApi.listWorkflows(props.workflowRole) },
  search: {
    label: () => t('common.search'),
    placeholder: () => t('workflows.searchPlaceholder'),
    values: (row) => [row.name, row.description],
  },
  columns: [
    { key: 'name', label: () => t('workflows.fields.name'), value: (row) => row.name },
    {
      key: 'status',
      label: () => t('workflows.fields.status'),
      value: (row) => row.enabled
        ? t('workflows.status.published')
        : t('workflows.status.draft'),
    },
  ],
  rowActions: [
    {
      key: 'configure',
      label: () => t('workflows.actions.configure'),
      tone: 'primary',
      run: (row) => openEdit(row),
    },
    {
      key: 'edit-flow',
      label: () => t('workflows.actions.editFlow'),
      tone: 'info',
      run: (row) => router.push(`/workflows/${encodeURIComponent(row.id)}/editor`),
    },
    {
      key: 'delete',
      label: () => t('common.delete'),
      tone: 'danger',
      confirm: (row) => ({
        title: t('workflows.deleteTitle'),
        description: t('workflows.deleteDescription', { name: row.name }),
        confirmLabel: t('common.delete'),
        cancelLabel: t('common.cancel'),
        dangerous: true,
      }),
      run: (row) => managementApi.deleteWorkflow(row.id),
      successTitle: () => t('workflows.deleted'),
      failureTitle: () => t('workflows.deleteFailed'),
      reloadAfter: 'current',
    },
  ],
}))
</script>

<template>
  <PageShell>
    <DataTableWorkbench :key="props.workflowRole" ref="table" :config="tableConfig" />
    <template #actions>
      <LteButton theme="success" type="button" @click="openNew">
        <i class="bi bi-plus-lg" aria-hidden="true" />
        {{ t('common.new') }}
      </LteButton>
    </template>
  </PageShell>

  <ModalHost
    :open="formOpen"
    :title="editingId ? t('workflows.editTitle') : t(`workflows.${props.workflowRole}CreateTitle`)"
    @close="closeForm"
  >
    <form id="workflow-form" @submit.prevent="save">
      <FormField field-path="name" label-key="workflows.fields.name">
        <LteInput v-model="form.name" maxlength="120" required />
      </FormField>
      <FormField field-path="workflow_event_output_id" label-key="workflows.fields.eventOutput">
        <select v-model="form.workflow_event_output_id" class="form-select">
          <option :value="null">{{ t('common.none') }}</option>
          <option v-for="output in workflowEventOutputs" :key="output.id" :value="output.id">
            {{ output.name }}
          </option>
        </select>
      </FormField>
      <FormField field-path="description" label-key="workflows.fields.description">
        <LteTextarea v-model="form.description" :rows="4" maxlength="2000" />
      </FormField>
      <div class="row g-3" data-ui-control-row>
        <div class="col-lg-4">
          <FormField field-path="recursion_limit" label-key="workflows.fields.recursionLimit">
            <input v-model.number="form.recursion_limit" class="form-control" min="1" max="100000" step="1" type="number" required>
          </FormField>
        </div>
        <div class="col-lg-4">
          <FormField field-path="execution_timeout_seconds" label-key="workflows.fields.executionTimeoutSeconds">
            <div class="input-group">
              <input v-model.number="form.execution_timeout_seconds" class="form-control" min="1" max="86400" step="1" type="number" required>
              <span class="input-group-text">{{ t('workflows.seconds') }}</span>
            </div>
          </FormField>
        </div>
        <div class="col-lg-4">
          <FormField field-path="max_concurrency" label-key="workflows.fields.maxConcurrency">
            <input v-model.number="form.max_concurrency" class="form-control" min="1" max="256" step="1" type="number" required>
          </FormField>
        </div>
      </div>
      <LteAlert v-if="formError" class="mt-3" theme="danger">{{ formError }}</LteAlert>
    </form>
    <template #footer>
      <LteButton :disabled="saving" theme="warning" type="button" @click="closeForm">
        {{ t('common.cancel') }}
      </LteButton>
      <LteButton :disabled="saving" form="workflow-form" theme="primary" type="submit">
        <span v-if="saving" class="spinner-border spinner-border-sm" aria-hidden="true" />
        {{ t('common.save') }}
      </LteButton>
    </template>
  </ModalHost>
</template>
