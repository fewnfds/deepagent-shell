<script setup lang="ts">
import { LteButton } from '@adminlte/vue'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { managementApi, type Workflow } from '@/api'
import DataTableWorkbench from '@/components/data-table/DataTableWorkbench.vue'
import type { DataTableConfig } from '@/components/data-table/types'
import PageShell from '@/components/PageShell.vue'

const { t } = useI18n()
const router = useRouter()
const workflows = ref<Workflow[]>([])

function open(id: string): void { void router.push(`/workflows/${encodeURIComponent(id)}`) }
function create(): void { void router.push('/workflows/new') }

const workflowTableConfig: DataTableConfig<Workflow> = {
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
  rowActions: [{
    key: 'open-workflow',
    label: () => t('common.edit'),
    tone: 'primary',
    run: (item) => open(item.id),
  }],
  pageSize: 20,
  pageSizeOptions: [20, 50, 100],
}
</script>

<template>
  <PageShell>
    <template #actions>
      <LteButton theme="secondary" type="button" @click="void router.push('/library/entry-scripts')">{{ t('workflow.entryScripts') }}</LteButton>
      <LteButton theme="success" type="button" @click="create">{{ t('common.new') }}</LteButton>
    </template>
    <DataTableWorkbench :config="workflowTableConfig">
      <template #cell-name="{ value }"><span class="fw-semibold text-break">{{ value }}</span></template>
      <template #cell-description="{ value }"><span class="text-break">{{ value }}</span></template>
    </DataTableWorkbench>
  </PageShell>
</template>
