import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import type {
  CapabilityManifest,
  CatalogResponse,
  SavedBlock,
  ValidationReport,
} from '@/api'
import ModalHost from '@/components/ModalHost.vue'
import { useConfirmation } from '@/composables/useConfirmation'
import { useToasts } from '@/composables/useToasts'
import type { ConfigLibraryApi } from '@/pages/configLibrary'

import ConfigLibraryPage from './ConfigLibraryPage.vue'

const messages = {
  library: {
    eyebrow: 'Library',
    title: 'Configuration library',
    description: 'Saved configurations.',
    validationTitle: 'Repository validation',
    groups: {
      components: 'Components',
      agents: 'Agents',
    },
    catalogUnavailable: 'Catalog unavailable',
    unknownCategory: 'Unknown category {type}',
    loadFailed: 'Load failed',
    empty: 'No saved configurations.',
    resultCount: '{count} configurations',
    search: {
      label: 'Search this category',
      placeholder: 'Name or UUID',
      applied: 'Applied search: {query}',
      all: 'All configurations',
      empty: 'No matches',
    },
    columns: { name: 'Name', actions: 'Actions' },
    pagination: { ariaLabel: 'Library pages' },
    detail: {
      title: 'Details for {name}',
      titleFallback: 'Configuration details',
      cardMode: 'Card',
      jsonMode: 'JSON',
    },
    copy: {
      title: 'Copy configuration',
      description: 'Copy {name} ({id})',
      nameHint: 'Enter a distinct name.',
      nameRequired: 'Enter a name.',
      submit: 'Copy',
      succeeded: 'Configuration copied',
      failed: 'Copy failed',
    },
    delete: {
      title: 'Delete configuration',
      description: 'Delete {name}?',
      succeeded: 'Configuration deleted',
      failed: 'Delete failed',
    },
    unsupportedBlock: {
      action: 'Delete retired configuration',
      title: 'Delete retired configuration?',
      description: 'Delete {type} {name}',
      succeeded: 'Retired configuration deleted',
      failed: 'Retired configuration delete failed',
    },
    deleteFiltered: {
      action: 'Delete filtered results',
      title: 'Delete filtered configurations?',
      description: 'Delete {count} configurations',
      succeeded: 'Deleted {count} configurations',
      failed: 'Bulk delete failed',
    },
  },
  common: {
    refresh: 'Refresh',
    refreshing: 'Refreshing',
    loading: 'Loading',
    retry: 'Retry',
    view: 'View',
    edit: 'Edit',
    copy: 'Copy',
    copying: 'Copying',
    delete: 'Delete',
    deleting: 'Deleting',
    search: 'Search',
    reset: 'Reset',
    cancel: 'Cancel',
    close: 'Close',
    detailSeparator: ': ',
    itemSeparator: '; ',
    previousPage: 'Previous page',
    nextPage: 'Next page',
    pagination: {
      first: 'First',
      last: 'Last',
      pageLabel: 'Page {page}',
      pageSize: 'Page size',
      pageSizeOption: '{count} items',
      jump: 'Go to page',
      jumpAction: 'Go',
      numberedSummary: '{total} items, {start}-{end}, page {page} of {totalPages}',
    },
    dataTable: {
      actions: 'Actions',
      operations: 'Operations',
    },
  },
  capabilities: {
    filesystem: { label: 'Filesystem' },
    model: { label: 'Model' },
    'primary-agent': { label: 'Primary Agent' },
    'subagent-override': { label: 'Subagent override' },
  },
  validation: {
    status: {
      unavailable: 'Unavailable',
      validating: 'Validating',
      valid: 'Valid',
      invalid: 'Invalid',
    },
    validatingDetail: 'Checking repository.',
    unavailableDetail: 'Validation unavailable.',
    issueSummary: 'Configuration problems: {count}. Expand to view the full details',
    scope: {},
  },
  fields: {
    id: 'UUID',
    name: 'Configuration name',
    unknown: 'Unknown field',
  },
  errors: {
    requestFailed: 'Request failed',
  },
}

const manifests: CapabilityManifest[] = [
  {
    type: 'model',
    terminology_key: 'model',
    label: 'ignored',
    order: 2,
    icon_key: 'bot',
    editor_key: 'model',
    subagent_overrideable: true,
    required: true,
    subagent_policy: 'inherit',
    tool_names: [],
  },
  {
    type: 'filesystem',
    terminology_key: 'file-system',
    label: 'ignored',
    order: 1,
    icon_key: 'folder',
    editor_key: 'filesystem',
    subagent_overrideable: false,
    required: true,
    subagent_policy: 'inherit',
    tool_names: [],
  },
]

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((accept) => {
    resolve = accept
  })
  return { promise, resolve }
}

function createApi() {
  const block: SavedBlock = { id: 'block-uuid', name: 'Original model' }
  const copied: SavedBlock = { id: 'copy-uuid', name: 'Copied model' }
  let stored = [block]
  const getCatalog = vi.fn(async (): Promise<CatalogResponse> => ({
    block_types: manifests,
    editor_defaults: {},
  }))
  const validateRepository = vi.fn(async (): Promise<ValidationReport> => ({
    valid: true,
    stage: 'repository',
    issues: [],
  }))
  const listBlocks = vi.fn(async () => [...stored])
  const listPrimaryAgents = vi.fn(async () => [])
  const listSubagentOverrides = vi.fn(async () => [])
  const copyBlock = vi.fn(async () => {
    stored = [...stored, copied]
    return copied
  })
  const deleteBlock = vi.fn(async (_type: string, id: string) => {
    stored = stored.filter((item) => item.id !== id)
    return { ok: true }
  })
  const deleteUnsupportedBlock = vi.fn(async () => ({ ok: true }))
  const deleteBlocks = vi.fn(async (ids: string[]) => {
    stored = stored.filter((item) => !ids.includes(item.id))
    return { deleted: ids.length }
  })
  const service: ConfigLibraryApi = {
    getCatalog,
    validateRepository,
    listBlocks,
    listPrimaryAgents,
    listSubagentOverrides,
    copyBlock,
    copyPrimaryAgent: vi.fn(),
    copySubagentOverride: vi.fn(),
    deleteBlock,
    deleteUnsupportedBlock,
    deleteBlocks: vi.fn(async (_type, ids) => deleteBlocks(ids)),
    deletePrimaryAgent: vi.fn(),
    deleteSubagentOverride: vi.fn(),
    deletePrimaryAgents: vi.fn(),
    deleteSubagentOverrides: vi.fn(),
  }
  return {
    service,
    block,
    getCatalog,
    validateRepository,
    listBlocks,
    listPrimaryAgents,
    listSubagentOverrides,
    copyBlock,
    deleteBlock,
    deleteUnsupportedBlock,
    deleteBlocks,
  }
}

async function mountPage(service: ConfigLibraryApi) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/library/:type', component: ConfigLibraryPage }],
  })
  await router.push('/library/model')
  await router.isReady()
  const i18n = createI18n({
    legacy: false,
    locale: 'en',
    messages: { en: messages },
  })
  const wrapper = mount(ConfigLibraryPage, {
    props: { api: service },
    global: {
      plugins: [router, i18n],
    },
  })
  await flushPromises()
  return { wrapper, router }
}

function buttonByText(wrapper: ReturnType<typeof mount>, text: string) {
  const button = wrapper.findAll('button').find((item) => item.text() === text)
  if (!button) throw new Error(`Button not found: ${text}`)
  return button
}

afterEach(() => {
  useConfirmation().cancel()
  const toasts = useToasts()
  for (const item of toasts.items.value) toasts.dismiss(item.id)
})

describe('ConfigLibraryPage', () => {
  it('keeps list and copy failures in their local error regions without toasts', async () => {
    const listFailure = createApi()
    listFailure.listBlocks.mockRejectedValueOnce(new Error('offline'))
    const { wrapper: listWrapper } = await mountPage(listFailure.service)

    expect(listWrapper.get('[data-testid="data-table-error"]').attributes('role')).toBe('alert')
    expect(useToasts().items.value).toHaveLength(0)
    listWrapper.unmount()

    const copyFailure = createApi()
    copyFailure.copyBlock.mockRejectedValueOnce(new Error('copy failed'))
    const { wrapper: copyWrapper } = await mountPage(copyFailure.service)
    await buttonByText(copyWrapper, 'Copy').trigger('click')
    await copyWrapper.get('#library-copy-form input').setValue('Copied model')
    await copyWrapper.get('#library-copy-form').trigger('submit')
    await flushPromises()

    expect(copyWrapper.get('[data-testid="copy-error"]').attributes('role')).toBe('alert')
    expect(useToasts().items.value).toHaveLength(0)
    copyWrapper.unmount()
  })

  it('uses catalog order and loads only the route category', async () => {
    const api = createApi()
    const { wrapper } = await mountPage(api.service)

    expect(api.getCatalog).toHaveBeenCalledOnce()
    expect(api.listBlocks).toHaveBeenCalledOnce()
    expect(api.listBlocks).toHaveBeenCalledWith('model')
    expect(api.listPrimaryAgents).not.toHaveBeenCalled()
    expect(api.listSubagentOverrides).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="library-component-group"] > span').text()).toBe('Components')
    expect(wrapper
      .get('[data-testid="library-component-group"] [data-testid="section-nav"]')
      .findAll('button')
      .map((item) => item.text())).toEqual(['Filesystem', 'Model'])
    expect(wrapper.get('[data-testid="library-agent-group"] > span').text()).toBe('Agents')
    expect(wrapper
      .get('[data-testid="library-agent-group"] [data-testid="section-nav"]')
      .findAll('button')
      .map((item) => item.text())).toEqual(['Primary Agent', 'Subagent override'])
    expect(wrapper.findAll('[data-testid="section-nav"] button').every((button) => !button.classes().includes('w-100'))).toBe(true)
    expect(wrapper.findAll('[data-testid="section-nav"] button').map((button) => (
      button.classes().includes('btn-primary') ? 'primary' : 'secondary'
    ))).toEqual(['secondary', 'primary', 'secondary', 'secondary'])
    expect(wrapper.find('[data-testid="navigation-region"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="library-content-region"]').classes()).toContain('col-lg-8')
    expect(wrapper.get('[data-testid="library-validation-region"]').classes()).toContain('col-lg-4')
    expect(wrapper.get('[data-testid="library-content-region"]').find('.card-title').text()).toBe('Model')
    expect(wrapper.get('[data-testid="data-table-row"]').text()).not.toContain('block-uuid')
  })

  it('deletes an unsupported component from its validation issue after confirmation', async () => {
    const api = createApi()
    api.validateRepository
      .mockResolvedValueOnce({
        valid: false,
        stage: 'repository_load',
        issues: [{
          code: 'storage.unknown_block_type',
          scope: 'block',
          owner_id: 'legacy-block-id',
          owner_name: 'tag-test',
          owner_type: 'prompt-injection',
          path: 'block_type',
          message: 'unsupported',
          message_key: 'errors.unknownConfigurationType',
          message_args: { type: 'prompt-injection' },
        }],
      })
      .mockResolvedValueOnce({ valid: true, stage: 'repository_load', issues: [] })
    const { wrapper } = await mountPage(api.service)

    await wrapper.get('.accordion-button').trigger('click')
    await buttonByText(wrapper, 'Delete retired configuration').trigger('click')
    expect(useConfirmation().current.value).toMatchObject({
      dangerous: true,
      description: 'Delete prompt-injection tag-test',
    })
    useConfirmation().accept()
    await flushPromises()

    expect(api.deleteUnsupportedBlock).toHaveBeenCalledWith('legacy-block-id')
    expect(api.validateRepository).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-testid="validation-issue"]').exists()).toBe(false)
  })

  it('keeps the latest repository validation when an earlier request finishes late', async () => {
    const staleValidation = deferred<ValidationReport>()
    const latestValidation = deferred<ValidationReport>()
    const api = createApi()
    api.validateRepository
      .mockImplementationOnce(() => staleValidation.promise)
      .mockImplementationOnce(() => latestValidation.promise)
    const { wrapper } = await mountPage(api.service)

    await buttonByText(wrapper, 'Refresh').trigger('click')
    latestValidation.resolve({ valid: true, stage: 'repository_load', issues: [] })
    await flushPromises()
    staleValidation.resolve({
      valid: false,
      stage: 'repository_load',
      issues: [{
        code: 'stale.validation',
        scope: 'repository',
        owner_id: '',
        owner_name: '',
        path: 'repository',
        message: 'stale result',
        message_key: 'errors.requestFailed',
        message_args: {},
      }],
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="validation-checklist"]').attributes('data-status')).toBe('valid')
    expect(wrapper.find('[data-testid="validation-issue"]').exists()).toBe(false)
  })

  it('hides internal IDs in ordinary views while actions still use the selected UUID', async () => {
    const api = createApi()
    const { wrapper, router } = await mountPage(api.service)

    await buttonByText(wrapper, 'View').trigger('click')
    await flushPromises()
    const detailModal = wrapper.findAllComponents(ModalHost).find((item) => (
      item.props('title') === 'Details for Original model'
    ))
    expect(detailModal?.props('size')).toBe('wide')
    expect(detailModal?.props('description')).toBeUndefined()
    expect(wrapper.get('[data-testid="config-detail-list"]').text()).not.toContain('block-uuid')
    expect(wrapper.get('[data-testid="config-detail-list"] dt').classes()).toContain('text-end')
    expect(wrapper.get('[data-testid="config-detail-list"] dd').classes()).toContain('text-start')
    await wrapper.get('[data-testid="detail-json-mode"]').setValue(true)
    await flushPromises()
    expect(wrapper.get('[data-testid="config-detail-json"]').text()).toContain('block-uuid')
    await buttonByText(wrapper, 'Close').trigger('click')

    await buttonByText(wrapper, 'Copy').trigger('click')
    await flushPromises()
    await wrapper.get('#library-copy-form input').setValue('Copied model')
    await wrapper.get('#library-copy-form').trigger('submit')
    await flushPromises()
    expect(api.copyBlock).toHaveBeenCalledWith('model', 'block-uuid', 'Copied model')

    await buttonByText(wrapper, 'Delete').trigger('click')
    expect(useConfirmation().current.value?.description).toContain('Original model')
    expect(useConfirmation().current.value?.description).not.toContain('block-uuid')
    useConfirmation().accept()
    await flushPromises()
    expect(api.deleteBlock).toHaveBeenCalledWith('model', 'block-uuid')

    await buttonByText(wrapper, 'Edit').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/components/model')
    expect(router.currentRoute.value.query.id).toBe('copy-uuid')
  })

  it('deletes only the submitted search results through one category batch command', async () => {
    const api = createApi()
    api.listBlocks.mockResolvedValueOnce([
      api.block,
      { id: 'other-uuid', name: 'Other model' },
    ])
    const { wrapper } = await mountPage(api.service)

    await wrapper.get('#configuration-library-query').setValue('Original')
    const bulk = buttonByText(wrapper, 'Delete filtered results')
    expect(bulk.attributes('disabled')).toBeDefined()
    await wrapper.get('form[role="search"]').trigger('submit')
    await flushPromises()
    expect(wrapper.findAll('[data-testid="data-table-row"]')).toHaveLength(1)

    await bulk.trigger('click')
    useConfirmation().accept()
    await flushPromises()
    expect(api.deleteBlocks).toHaveBeenCalledWith(['block-uuid'])
  })
})
