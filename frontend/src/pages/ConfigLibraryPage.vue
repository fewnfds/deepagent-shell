<script setup lang="ts">
import { LteAlert, LteButton } from '@adminlte/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { managementApi, type CapabilityManifest, type ValidationIssue } from '@/api'
import ConfigDetail from '@/components/ConfigDetail.vue'
import DataTableWorkbench from '@/components/data-table/DataTableWorkbench.vue'
import type { DataTableConfig } from '@/components/data-table/types'
import FormField from '@/components/FormField.vue'
import ModalHost from '@/components/ModalHost.vue'
import PageShell from '@/components/PageShell.vue'
import SectionNav from '@/components/SectionNav.vue'
import type { SectionNavItem } from '@/components/sectionNav'
import ValidationChecklist from '@/components/ValidationChecklist.vue'
import { useConfirmation } from '@/composables/useConfirmation'
import type { DraftValidationState } from '@/composables/useDraftValidation'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'
import {
  agentLibraryCategories,
  editLocation,
  routeCategory,
  type ConfigLibraryApi,
  type LibraryCategoryId,
  type LibraryItem,
} from '@/pages/configLibrary'

const props = defineProps<{
  api?: ConfigLibraryApi
}>()

const { t } = useI18n()
const managementError = useManagementError()
const route = useRoute()
const router = useRouter()
const { notify } = useToasts()
const confirmation = useConfirmation()
const api = computed<ConfigLibraryApi>(() => props.api ?? managementApi)

const manifests = ref<CapabilityManifest[]>([])
const catalogReady = ref(false)
const refreshing = ref(false)
const catalogError = ref('')
const libraryTable = ref<{ reload: () => Promise<void> } | null>(null)
const detailItem = ref<LibraryItem | null>(null)
const detailMode = ref<'card' | 'json'>('card')
const copyItem = ref<LibraryItem | null>(null)
const copyName = ref('')
const copyError = ref('')
const copying = ref(false)
const deletingUnsupportedBlockId = ref('')
const repositoryValidation = ref<DraftValidationState>({
  status: 'validating',
  report: null,
  error: '',
})

const activeCategoryId = computed(() => routeCategory(route.params.type))

const componentCategoryItems = computed<SectionNavItem[]>(() => (
  manifests.value.map((manifest) => ({
    id: manifest.type,
    label: t(`capabilities.${manifest.type}.label`),
  }))
))

const agentCategoryItems = computed<SectionNavItem[]>(() => (
  agentLibraryCategories.map((id) => ({
    id,
    label: t(`capabilities.${id}.label`),
  }))
))

const categoryItems = computed<SectionNavItem[]>(() => [
  ...componentCategoryItems.value,
  ...agentCategoryItems.value,
])

const currentCategory = computed<LibraryCategoryId | null>(() => (
  categoryItems.value.some((item) => item.id === activeCategoryId.value)
    ? activeCategoryId.value as LibraryCategoryId
    : null
))

const currentCategoryLabel = computed(() => currentCategory.value
  ? t(`capabilities.${currentCategory.value}.label`)
  : t('library.unknownCategory', { type: activeCategoryId.value }))

const detailValue = computed<Record<string, unknown>>(() => (
  detailItem.value ? { ...detailItem.value } : {}
))

async function loadCatalog(): Promise<void> {
  catalogError.value = ''
  try {
    const catalog = await api.value.getCatalog()
    manifests.value = [...catalog.block_types].sort((left, right) => left.order - right.order)
  } catch (error) {
    catalogError.value = managementError.describe(error).display
  } finally {
    catalogReady.value = true
  }
}

async function refreshRepositoryValidation(): Promise<void> {
  repositoryValidation.value = { status: 'validating', report: null, error: '' }
  try {
    const report = await api.value.validateRepository()
    repositoryValidation.value = {
      status: report.valid ? 'valid' : 'invalid',
      report,
      error: '',
    }
  } catch (error) {
    repositoryValidation.value = {
      status: 'unavailable',
      report: null,
      error: managementError.describe(error, 'errors.validationUnavailable').display,
    }
  }
}

async function listCategory(category: LibraryCategoryId): Promise<LibraryItem[]> {
  if (category === 'primary-agent') return api.value.listPrimaryAgents()
  if (category === 'subagent-override') return api.value.listSubagentOverrides()
  if (category === 'worker-profile') return api.value.listWorkerProfiles()
  return api.value.listBlocks(category)
}

async function refresh(): Promise<void> {
  refreshing.value = true
  await Promise.all([libraryTable.value?.reload(), refreshRepositoryValidation()])
  refreshing.value = false
}

function selectCategory(id: string): void {
  if (id === activeCategoryId.value) return
  void router.push(`/library/${encodeURIComponent(id)}`)
}

function showDetail(item: LibraryItem): void {
  detailMode.value = 'card'
  detailItem.value = item
}

function closeDetail(): void {
  detailItem.value = null
}

function editItem(item: LibraryItem): void {
  const category = currentCategory.value
  if (!category) return
  closeDetail()
  void router.push(editLocation(category, item.id))
}

function openCopy(item: LibraryItem): void {
  copyItem.value = item
  copyName.value = ''
  copyError.value = ''
}

function closeCopy(): void {
  if (copying.value) return
  copyItem.value = null
  copyName.value = ''
  copyError.value = ''
}

async function copyCurrentItem(): Promise<void> {
  const source = copyItem.value
  const category = currentCategory.value
  if (!source || !category) return
  if (!copyName.value.trim()) {
    copyError.value = t('library.copy.nameRequired')
    return
  }
  copying.value = true
  copyError.value = ''
  try {
    if (category === 'primary-agent') {
      await api.value.copyPrimaryAgent(source.id, copyName.value)
    } else if (category === 'subagent-override') {
      await api.value.copySubagentOverride(source.id, copyName.value)
    } else if (category === 'worker-profile') {
      await api.value.copyWorkerProfile(source.id, copyName.value)
    } else {
      await api.value.copyBlock(category, source.id, copyName.value)
    }
    copying.value = false
    closeCopy()
    notify({ tone: 'success', title: t('library.copy.succeeded') })
    await Promise.all([libraryTable.value?.reload(), refreshRepositoryValidation()])
  } catch (error) {
    copyError.value = managementError.describe(error).display
  } finally {
    copying.value = false
  }
}

async function deleteUnsupportedBlock(issue: ValidationIssue): Promise<void> {
  if (
    issue.code !== 'storage.unknown_block_type'
    || !issue.owner_id
    || !issue.owner_type
  ) return
  const accepted = await confirmation.confirm({
    title: t('library.unsupportedBlock.title'),
    description: t('library.unsupportedBlock.description', {
      name: issue.owner_name,
      type: issue.owner_type,
    }),
    confirmLabel: t('common.delete'),
    cancelLabel: t('common.cancel'),
    dangerous: true,
  })
  if (!accepted) return
  deletingUnsupportedBlockId.value = issue.owner_id
  try {
    await api.value.deleteUnsupportedBlock(issue.owner_id)
    notify({ tone: 'success', title: t('library.unsupportedBlock.succeeded') })
    await refreshRepositoryValidation()
  } catch (error) {
    notify({
      tone: 'danger',
      title: t('library.unsupportedBlock.failed'),
      message: managementError.describe(error).display,
    })
  } finally {
    deletingUnsupportedBlockId.value = ''
  }
}

function deletedCount(result: unknown): number {
  if (!result || typeof result !== 'object' || !('deleted' in result)) return 0
  return Number((result as { deleted: unknown }).deleted) || 0
}

const libraryTableConfig: DataTableConfig<LibraryItem> = {
  id: 'configuration-library',
  title: () => currentCategoryLabel.value,
  ariaLabel: () => t('library.pagination.ariaLabel'),
  emptyMessage: () => t('library.empty'),
  filteredEmptyMessage: () => t('library.search.empty'),
  loadErrorTitle: () => t('library.loadFailed'),
  rowKey: (item) => item.id,
  provider: {
    mode: 'local',
    load: async () => {
      const category = currentCategory.value
      if (!category) throw new Error(t('library.unknownCategory', { type: activeCategoryId.value }))
      detailItem.value = null
      copyItem.value = null
      return listCategory(category)
    },
  },
  search: {
    label: () => t('library.search.label'),
    placeholder: () => t('library.search.placeholder'),
    values: (item) => [item.name, item.id],
  },
  columns: [{ key: 'name', label: () => t('library.columns.name'), value: (item) => item.name }],
  rowActions: [
    {
      key: 'view-configuration',
      label: () => t('common.view'),
      tone: 'info',
      run: showDetail,
    },
    {
      key: 'edit-configuration',
      label: () => t('common.edit'),
      tone: 'warning',
      run: editItem,
    },
    {
      key: 'copy-configuration',
      label: () => t('common.copy'),
      tone: 'success',
      run: openCopy,
    },
    {
      key: 'delete-configuration',
      label: () => t('common.delete'),
      busyLabel: () => t('common.deleting'),
      tone: 'danger',
      confirm: (item) => ({
        title: t('library.delete.title'),
        description: t('library.delete.description', { name: item.name, id: item.id }),
        confirmLabel: t('common.delete'),
        cancelLabel: t('common.cancel'),
        dangerous: true,
      }),
      run: async (item) => {
        const category = currentCategory.value
        if (!category) return
        if (category === 'primary-agent') await api.value.deletePrimaryAgent(item.id)
        else if (category === 'subagent-override') await api.value.deleteSubagentOverride(item.id)
        else if (category === 'worker-profile') await api.value.deleteWorkerProfile(item.id)
        else await api.value.deleteBlock(category, item.id)
        if (detailItem.value?.id === item.id) closeDetail()
        await refreshRepositoryValidation()
      },
      successTitle: () => t('library.delete.succeeded'),
      failureTitle: () => t('library.delete.failed'),
      reloadAfter: 'current',
    },
  ],
  bulkAction: {
    label: () => t('library.deleteFiltered.action'),
    busyLabel: () => t('common.deleting'),
    enabled: (context) => context.hasAppliedFilters && context.total > 0,
    confirm: (context) => ({
      title: t('library.deleteFiltered.title'),
      description: t('library.deleteFiltered.description', { count: context.total }),
      confirmLabel: t('common.delete'),
      cancelLabel: t('common.cancel'),
      dangerous: true,
    }),
    run: async (context) => {
      const category = currentCategory.value
      if (!category) return { deleted: 0 }
      const ids = context.matchingRows.map((item) => item.id)
      const result = category === 'primary-agent'
        ? await api.value.deletePrimaryAgents(ids)
        : category === 'subagent-override'
          ? await api.value.deleteSubagentOverrides(ids)
          : category === 'worker-profile'
            ? await api.value.deleteWorkerProfiles(ids)
          : await api.value.deleteBlocks(category, ids)
      closeDetail()
      await refreshRepositoryValidation()
      return result
    },
    successTitle: (result) => t('library.deleteFiltered.succeeded', { count: deletedCount(result) }),
    failureTitle: () => t('library.deleteFiltered.failed'),
  },
  pageSize: 20,
  pageSizeOptions: [20, 50, 100],
}

onMounted(async () => {
  const validationRequest = refreshRepositoryValidation()
  await loadCatalog()
  await validationRequest
})
</script>

<template>
  <PageShell>
    <template #actions>
      <LteButton
        :disabled="refreshing"
        theme="info"
        type="button"
        @click="refresh"
      >
        <span v-if="refreshing" class="spinner-border spinner-border-sm" aria-hidden="true" />
        {{ refreshing ? t('common.refreshing') : t('common.refresh') }}
      </LteButton>
    </template>

    <div
      v-if="componentCategoryItems.length"
      class="d-flex flex-wrap align-items-center gap-2 mb-2"
      data-testid="library-component-group"
    >
      <span class="fw-semibold">{{ t('library.groups.components') }}</span>
      <SectionNav
        :active-id="activeCategoryId"
        :aria-label="t('library.groups.components')"
        :items="componentCategoryItems"
        layout="inline"
        @select="selectCategory"
      />
    </div>
    <div
      v-if="agentCategoryItems.length"
      class="d-flex flex-wrap align-items-center gap-2 mb-3"
      data-testid="library-agent-group"
    >
      <span class="fw-semibold">{{ t('library.groups.agents') }}</span>
      <SectionNav
        :active-id="activeCategoryId"
        :aria-label="t('library.groups.agents')"
        :items="agentCategoryItems"
        layout="inline"
        @select="selectCategory"
      />
    </div>

    <div class="row g-3 align-items-start" data-testid="library-layout">
      <section class="col-lg-8" data-testid="library-content-region">
        <LteAlert
          v-if="catalogError"
          class="mb-3"
          data-testid="catalog-error"
          :title="t('library.catalogUnavailable')"
          theme="danger"
        >
          {{ catalogError }}
        </LteAlert>

        <DataTableWorkbench
          v-if="catalogReady && currentCategory"
          :key="activeCategoryId"
          ref="libraryTable"
          :config="libraryTableConfig"
        >
          <template #cell-name="{ value }">
            <span class="fw-semibold text-break">{{ value }}</span>
          </template>
        </DataTableWorkbench>
        <LteAlert v-else-if="catalogReady" :title="currentCategoryLabel" theme="danger">
          {{ currentCategoryLabel }}
        </LteAlert>
      </section>

      <aside class="col-lg-4" data-testid="library-validation-region">
        <ValidationChecklist
          :title="t('library.validationTitle')"
          :validation="repositoryValidation"
        >
          <template #issue-actions="{ issue }">
            <LteButton
              v-if="issue.code === 'storage.unknown_block_type' && issue.owner_id && issue.owner_type"
              :disabled="deletingUnsupportedBlockId === issue.owner_id"
              theme="danger"
              type="button"
              @click="deleteUnsupportedBlock(issue)"
            >
              {{ deletingUnsupportedBlockId === issue.owner_id
                ? t('common.deleting')
                : t('library.unsupportedBlock.action') }}
            </LteButton>
          </template>
        </ValidationChecklist>
      </aside>
    </div>
  </PageShell>

  <ModalHost
    :open="detailItem !== null"
    size="wide"
    :title="detailItem ? t('library.detail.title', { name: detailItem.name }) : t('library.detail.titleFallback')"
    @close="closeDetail"
  >
    <div class="d-flex flex-wrap gap-2 mb-3">
      <div class="form-check">
        <input id="detail-card-mode" v-model="detailMode" class="form-check-input" type="radio" value="card">
        <label class="form-check-label" for="detail-card-mode">{{ t('library.detail.cardMode') }}</label>
      </div>
      <div class="form-check">
        <input
          id="detail-json-mode"
          v-model="detailMode"
          class="form-check-input"
          data-testid="detail-json-mode"
          type="radio"
          value="json"
        >
        <label class="form-check-label" for="detail-json-mode">{{ t('library.detail.jsonMode') }}</label>
      </div>
    </div>
    <ConfigDetail
      :hidden-keys="['id']"
      :mode="detailMode"
      :value="detailValue"
    />
    <template #footer>
      <LteButton theme="warning" type="button" @click="closeDetail">
        {{ t('common.close') }}
      </LteButton>
      <LteButton
        v-if="detailItem"
        theme="primary"
        type="button"
        @click="editItem(detailItem)"
      >
        {{ t('common.edit') }}
      </LteButton>
    </template>
  </ModalHost>

  <ModalHost
    :description="copyItem ? t('library.copy.description', { name: copyItem.name, id: copyItem.id }) : ''"
    :open="copyItem !== null"
    :title="t('library.copy.title')"
    @close="closeCopy"
  >
    <form
      id="library-copy-form"
      novalidate
      @submit.prevent="copyCurrentItem"
    >
      <FormField
        field-path="name"
        :hint="t('library.copy.nameHint')"
      >
        <input v-model="copyName" autocomplete="off" class="form-control">
      </FormField>
      <LteAlert
        v-if="copyError"
        data-testid="copy-error"
        theme="danger"
      >
        {{ copyError }}
      </LteAlert>
    </form>
    <template #footer>
      <LteButton
        :disabled="copying"
        theme="warning"
        type="button"
        @click="closeCopy"
      >
        {{ t('common.cancel') }}
      </LteButton>
      <LteButton
        :disabled="copying"
        form="library-copy-form"
        theme="primary"
        type="submit"
      >
        <span v-if="copying" class="spinner-border spinner-border-sm" aria-hidden="true" />
        {{ copying ? t('common.copying') : t('library.copy.submit') }}
      </LteButton>
    </template>
  </ModalHost>
</template>
