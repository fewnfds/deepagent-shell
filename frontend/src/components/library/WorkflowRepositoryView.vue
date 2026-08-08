<script setup lang="ts">
import { LteButton } from '@adminlte/vue'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { managementApi, type Workflow } from '@/api'
import DataTableWorkbench from '@/components/data-table/DataTableWorkbench.vue'
import type { DataTableConfig } from '@/components/data-table/types'

const { t } = useI18n()
const router = useRouter()
const workflows = ref<Workflow[]>([])
const table = ref<{ reload: () => Promise<void> } | null>(null)

function open(id: string): void { void router.push(`/workflows/${encodeURIComponent(id)}`) }
function create(): void { void router.push('/workflows/new') }

const config: DataTableConfig<Workflow> = {
  id: 'workflow-repository',
  ariaLabel: () => t('workflow.table.ariaLabel'),
  emptyMessage: () => t('workflow.empty'),
  loadErrorTitle: () => t('workflow.loadFailed'),
  rowKey: (item) => item.id,
  provider: {
    mode: 'local',
    load: async () => {
      workflows.value = await managementApi.listWorkflows()
      return workflows.value
    },
  },
  search: {
    label: () => t('workflow.table.search'),
    placeholder: () => t('workflow.table.searchPlaceholder'),
    values: (item) => [item.name, item.description, item.id],
  },
  columns: [
    { key: 'name', label: () => t('workflow.table.name'), value: (item) => item.name || t('workflow.unnamed') },
    { key: 'description', label: () => t('workflow.table.description'), value: (item) => item.description || '—' },
    { key: 'status', label: () => t('workflow.table.status'), value: (item) => t(item.enabled ? 'common.enabled' : 'common.disabled') },
  ],
  rowActions: [{ key: 'open-workflow', label: () => t('common.edit'), tone: 'primary', run: (item) => open(item.id) }],
  pageSize: 20,
  pageSizeOptions: [20, 50, 100],
}

async function reload(): Promise<void> { await table.value?.reload() }
defineExpose({ reload })
</script>

<template>
  <section class="card" data-testid="workflow-repository-view">
    <div class="card-header d-flex align-items-center justify-content-between gap-2">
      <div>
        <h2 class="card-title h5 mb-1">{{ t('workflow.listTitle') }}</h2>
        <p class="card-text small text-body-secondary mb-0">{{ t('library.workflowDescription') }}</p>
      </div>
      <LteButton theme="success" type="button" @click="create">
        <i class="bi bi-plus-lg" aria-hidden="true" /> {{ t('common.new') }}
      </LteButton>
    </div>
    <DataTableWorkbench ref="table" :config="config">
      <template #cell-name="{ value }"><span class="fw-semibold text-break">{{ value }}</span></template>
      <template #cell-description="{ value }"><span class="text-break">{{ value }}</span></template>
    </DataTableWorkbench>
  </section>
</template>
