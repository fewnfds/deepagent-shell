<script setup lang="ts">
import { LteAlert, LteButton, LteInput, LteTextarea } from '@adminlte/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  managementApi,
  type MainAgent,
  type Workflow,
  type WorkflowPayload,
} from '@/api'
import DataTableWorkbench from '@/components/data-table/DataTableWorkbench.vue'
import type { DataTableConfig } from '@/components/data-table/types'
import FormField from '@/components/FormField.vue'
import ModalHost from '@/components/ModalHost.vue'
import PageShell from '@/components/PageShell.vue'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'

const { t } = useI18n()
const managementError = useManagementError()
const { notify } = useToasts()

const table = ref<{ reload: () => Promise<void> } | null>(null)
const mainAgents = ref<MainAgent[]>([])
const editingId = ref('')
const formOpen = ref(false)
const saving = ref(false)
const formError = ref('')
const form = ref<WorkflowPayload>(blankWorkflow())

function blankWorkflow(): WorkflowPayload {
  return { name: '', description: '', main_agent_id: '', enabled: true }
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
    description: workflow.description,
    main_agent_id: workflow.main_agent_id,
    enabled: workflow.enabled,
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
      description: form.value.description.trim(),
      main_agent_id: form.value.main_agent_id,
      enabled: form.value.enabled,
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

const tableConfig = computed<DataTableConfig<Workflow>>(() => ({
  id: 'workflows',
  ariaLabel: () => t('workflows.tableAriaLabel'),
  emptyMessage: () => t('workflows.empty'),
  filteredEmptyMessage: () => t('workflows.filteredEmpty'),
  loadErrorTitle: () => t('workflows.loadFailed'),
  rowKey: (row) => row.id,
  provider: { mode: 'local', load: () => managementApi.listWorkflows() },
  search: {
    label: () => t('common.search'),
    placeholder: () => t('workflows.searchPlaceholder'),
    values: (row) => [row.name, row.description, row.main_agent_name],
  },
  columns: [
    { key: 'name', label: () => t('workflows.fields.name'), value: (row) => row.name },
    {
      key: 'mainAgent',
      label: () => t('workflows.fields.mainAgent'),
      value: (row) => row.main_agent_name,
    },
    {
      key: 'enabled',
      label: () => t('workflows.fields.enabled'),
      value: (row) => row.enabled ? t('common.enabled') : t('common.disabled'),
    },
  ],
  rowActions: [
    {
      key: 'edit',
      label: () => t('common.edit'),
      tone: 'primary',
      run: (row) => openEdit(row),
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

onMounted(async () => {
  try {
    mainAgents.value = await managementApi.listMainAgents()
  } catch (error) {
    notify({
      tone: 'danger',
      title: t('workflows.mainAgentsLoadFailed'),
      message: managementError.describe(error).display,
    })
  }
})
</script>

<template>
  <PageShell>
    <DataTableWorkbench ref="table" :config="tableConfig" />
    <template #actions>
      <LteButton theme="success" type="button" @click="openNew">
        <i class="bi bi-plus-lg" aria-hidden="true" />
        {{ t('common.new') }}
      </LteButton>
    </template>
  </PageShell>

  <ModalHost
    :open="formOpen"
    :title="editingId ? t('workflows.editTitle') : t('workflows.createTitle')"
    @close="closeForm"
  >
    <form id="workflow-form" @submit.prevent="save">
      <FormField field-path="name" label-key="workflows.fields.name">
        <LteInput v-model="form.name" maxlength="120" required />
      </FormField>
      <FormField field-path="description" label-key="workflows.fields.description">
        <LteTextarea v-model="form.description" :rows="4" maxlength="2000" />
      </FormField>
      <FormField field-path="main_agent_id" label-key="workflows.fields.mainAgent">
        <select v-model="form.main_agent_id" class="form-select" required>
          <option value="">{{ t('workflows.selectMainAgent') }}</option>
          <option v-for="agent in mainAgents" :key="agent.id" :value="agent.id">
            {{ agent.name }}
          </option>
        </select>
      </FormField>
      <div class="form-check form-switch">
        <input id="workflow-enabled" v-model="form.enabled" class="form-check-input" type="checkbox">
        <label class="form-check-label" for="workflow-enabled">{{ t('workflows.fields.enabled') }}</label>
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
