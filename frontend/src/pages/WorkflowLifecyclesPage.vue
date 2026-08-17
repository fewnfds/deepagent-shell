<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { managementApi, type WorkflowLifecycleSummary } from '@/api'
import DataTableWorkbench from '@/components/data-table/DataTableWorkbench.vue'
import type { DataTableConfig } from '@/components/data-table/types'
import PageShell from '@/components/PageShell.vue'

const { t } = useI18n()

function localTime(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

const tableConfig: DataTableConfig<WorkflowLifecycleSummary> = {
  id: 'workflow-lifecycles',
  ariaLabel: () => t('workflowLifecycles.tableAriaLabel'),
  emptyMessage: () => t('workflowLifecycles.empty'),
  filteredEmptyMessage: () => t('workflowLifecycles.filteredEmpty'),
  loadErrorTitle: () => t('workflowLifecycles.loadFailed'),
  rowKey: (row) => row.lifecycle_id,
  provider: {
    mode: 'numbered',
    load: async (request) => {
      const response = await managementApi.listWorkflowLifecycles({
        page: request.page,
        page_size: request.pageSize,
        query: request.query,
      })
      return { rows: response.items, total: response.total }
    },
  },
  search: {
    label: () => t('common.search'),
    placeholder: () => t('workflowLifecycles.searchPlaceholder'),
    values: (row) => [row.workflow_name, row.lifecycle_id, row.request_id],
  },
  columns: [
    {
      key: 'workflow',
      label: () => t('workflowLifecycles.columns.workflow'),
      value: (row) => row.workflow_name || row.workflow_id,
    },
    {
      key: 'created',
      label: () => t('workflowLifecycles.columns.created'),
      value: (row) => localTime(row.created_at),
    },
    {
      key: 'parentStatus',
      label: () => t('workflowLifecycles.columns.parentStatus'),
      value: (row) => row.lifecycle_status === 'deleting'
        ? t('workflowLifecycles.lifecycleStatuses.deleting')
        : t(`workflowLifecycles.parentStatuses.${row.parent_status}`),
    },
    {
      key: 'tasks',
      label: () => t('workflowLifecycles.columns.tasks'),
      value: (row) => `${row.active_task_count} / ${row.task_count}`,
    },
    {
      key: 'checkpoints',
      label: () => t('workflowLifecycles.columns.checkpoints'),
      value: (row) => row.checkpoint_count,
    },
    {
      key: 'store',
      label: () => t('workflowLifecycles.columns.storeItems'),
      value: (row) => row.store_item_count,
    },
    {
      key: 'directories',
      label: () => t('workflowLifecycles.columns.dynamicDirectories'),
      value: (row) => row.dynamic_directory_count,
    },
  ],
  rowActions: [
    {
      key: 'delete',
      label: () => t('common.delete'),
      tone: 'danger',
      confirm: (row) => ({
        title: t('workflowLifecycles.deleteTitle'),
        description: t('workflowLifecycles.deleteDescription', {
          name: row.workflow_name || row.lifecycle_id,
        }),
        confirmLabel: t('common.delete'),
        cancelLabel: t('common.cancel'),
        dangerous: true,
      }),
      run: (row) => managementApi.deleteWorkflowLifecycle(row.lifecycle_id),
      successTitle: () => t('workflowLifecycles.deleted'),
      failureTitle: () => t('workflowLifecycles.deleteFailed'),
      reloadAfter: 'current',
    },
  ],
  pageSize: 10,
  pageSizeOptions: [10],
}
</script>

<template>
  <PageShell>
    <DataTableWorkbench :config="tableConfig" />
  </PageShell>
</template>
