import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { EventFeedItem, ManagementEvent } from '@/api'
import { en } from '@/locales/en'
import { useConfirmation } from '@/composables/useConfirmation'
import { useToasts } from '@/composables/useToasts'

import EventFeedPage from './EventFeedPage.vue'

function item(source: EventFeedItem['source'], id: string): EventFeedItem {
  return {
    id,
    source,
    occurred_at: '2026-07-30T00:00:00.000+00:00',
    level: 'info',
    request_id: `request-${id}`,
    summary: `summary-${id}`,
    inline_content: id === 'short'
      ? '{"source":"api_call","entry":{"message":"visible"}}'
      : null,
    matched_in_content: id === 'long',
    download_available: id === 'long',
  }
}

function api(items: EventFeedItem[]) {
  let eventHandler: ((event: ManagementEvent) => void) | undefined
  return {
    listEventFeed: vi.fn(async () => ({
      items,
      page: 1,
      page_size: 50,
      total: items.length,
      total_pages: 1,
    })),
    getApiEventPreview: vi.fn(async (id: string) => ({
      content: JSON.stringify({
        source: 'api_call',
        entry: {
          request_id: `request-${id}`,
          request_body: { messages_omitted: 1 },
        },
      }),
    })),
    downloadEvent: vi.fn(async () => new Blob(['{}'])),
    getInterceptionTest: vi.fn(async () => ({ enabled: false })),
    updateInterceptionTest: vi.fn(async (enabled: boolean) => ({ enabled })),
    getApiHistoryRetention: vi.fn(async () => ({ retention_limit: 20, max_retention_limit: 10_000 })),
    updateApiHistoryRetention: vi.fn(async (value: number) => ({ retention_limit: value, max_retention_limit: 10_000 })),
    getInterceptionRetention: vi.fn(async () => ({ retention_limit: 20, max_retention_limit: 10_000 })),
    updateInterceptionRetention: vi.fn(async (value: number) => ({ retention_limit: value, max_retention_limit: 10_000 })),
    getRuntimeDiagnostics: vi.fn(async () => ({ verbose: false, retention_limit: 20, max_retention_limit: 10_000 })),
    getSystemLogSettings: vi.fn(async () => ({
      max_size_mib: 5,
      min_size_mib: 1,
      max_size_mib_limit: 1024,
    })),
    updateSystemLogSettings: vi.fn(async (value: number) => ({
      max_size_mib: value,
      min_size_mib: 1,
      max_size_mib_limit: 1024,
    })),
    updateRuntimeDiagnostics: vi.fn(async (verbose: boolean) => ({
      verbose,
      retention_limit: 20,
      max_retention_limit: 10_000,
    })),
    updateRuntimeLogRetention: vi.fn(async (value: number) => ({
      verbose: false,
      retention_limit: value,
      max_retention_limit: 10_000,
    })),
    deleteMatchingEventFeed: vi.fn(async () => ({ deleted: 63 })),
    watchApiServerEvents: vi.fn((handler: (event: ManagementEvent) => void) => {
      eventHandler = handler
      handler({ type: 'event_stream_connected' })
      return vi.fn()
    }),
    emit(event: ManagementEvent) { eventHandler?.(event) },
  }
}

async function mountPage(mockApi: ReturnType<typeof api>) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/system/events', component: EventFeedPage }],
  })
  await router.push('/system/events?source=api_call')
  await router.isReady()
  const wrapper = mount(EventFeedPage, {
    props: { api: mockApi },
    global: {
      plugins: [
        router,
        createI18n({ legacy: false, locale: 'en', messages: { en } }),
      ],
    },
  })
  await flushPromises()
  return wrapper
}

afterEach(() => {
  vi.useRealTimers()
  useConfirmation().cancel()
  const toasts = useToasts()
  for (const toast of toasts.items.value) toasts.dismiss(toast.id)
})

describe('EventFeedPage', () => {
  it('loads the filtered feed and marks it stale when management SSE reports a change', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 7, 1, 12, 34, 56))
    const mockApi = api([item('api_call', 'short'), item('runtime', 'long')])
    const wrapper = await mountPage(mockApi)

    expect(mockApi.listEventFeed).toHaveBeenCalledWith(expect.objectContaining({
      started_at: new Date(2026, 7, 1, 0, 0, 0).toISOString(),
      ended_at: new Date(2026, 7, 1, 12, 34, 56).toISOString(),
      page: 1,
      source: ['api_call'],
      page_size: 50,
    }))
    expect(wrapper.text()).not.toContain('{"message":"visible"}')
    await wrapper.findAll('[data-testid="data-table-row"]')[0].trigger('click')
    await flushPromises()
    expect(mockApi.getApiEventPreview).toHaveBeenCalledWith('short')
    expect(wrapper.text()).toContain('messages_omitted')
    expect(wrapper.text()).toContain('request-short')
    expect(wrapper.text()).not.toContain('{"message":"visible"}')
    expect(wrapper.text()).toContain('RAW')
    expect(wrapper.text()).not.toContain('5000 hidden characters')

    mockApi.emit({ type: 'history_changed' })
    await flushPromises()
    expect(wrapper.text()).toContain('Load new events')
    expect(mockApi.listEventFeed).toHaveBeenCalledTimes(1)
    vi.setSystemTime(new Date(2026, 7, 1, 12, 35, 56))
    await wrapper.get('[data-testid="load-new-events"]').trigger('click')
    await flushPromises()
    expect(mockApi.listEventFeed).toHaveBeenCalledTimes(2)
    expect(mockApi.listEventFeed).toHaveBeenLastCalledWith(expect.objectContaining({
      started_at: new Date(2026, 7, 1, 0, 0, 0).toISOString(),
      ended_at: new Date(2026, 7, 1, 12, 35, 56).toISOString(),
      source: ['api_call'],
      page: 1,
    }))
  })

  it('keeps each log detail collapsed until its shared table row is clicked', async () => {
    const wrapper = await mountPage(api([item('api_call', 'short')]))
    const row = wrapper.get('[data-testid="data-table-row"]')

    expect(wrapper.find('[data-testid="data-table-detail"]').exists()).toBe(false)
    expect(row.attributes('aria-expanded')).toBe('false')
    await row.trigger('click')
    expect(wrapper.find('[data-testid="data-table-detail"]').exists()).toBe(true)
    expect(row.attributes('aria-expanded')).toBe('true')
    expect(wrapper.findAll('button').some(button => button.text() === 'Expand')).toBe(false)
  })

  it('declares only raw and debug download as API row actions', async () => {
    const wrapper = await mountPage(api([item('api_call', 'long')]))

    expect(wrapper.findAll('[data-testid="event-actions"]')).toHaveLength(0)
    expect(wrapper.findAll('[data-action]').map((action) => action.text())).toEqual([
      'RAW',
      'DEBUG',
    ])
  })

  it('submits source, level, and text filters from one filter card', async () => {
    const mockApi = api([])
    const wrapper = await mountPage(mockApi)

    expect(wrapper.findAll('.collection-filter-fieldset')).toHaveLength(3)
    expect(wrapper.text()).toContain('Operations')
    await wrapper.get('#event-feed-filter-source-runtime').setValue(true)
    await wrapper.get('#event-feed-filter-level-error').setValue(true)
    await wrapper.get('#event-feed-query').setValue('request-42')
    await wrapper.get('form[role="search"]').trigger('submit')
    await flushPromises()

    expect(mockApi.listEventFeed).toHaveBeenLastCalledWith(expect.objectContaining({
      source: ['api_call', 'runtime'],
      level: ['error'],
      query: 'request-42',
    }))
  })

  it('rejects an inverted draft window and transports a valid custom window as ISO', async () => {
    const mockApi = api([])
    const wrapper = await mountPage(mockApi)
    const initialCalls = mockApi.listEventFeed.mock.calls.length

    await wrapper.get('#event-feed-filter-started_at').setValue('2026-08-02T00:00:00')
    await wrapper.get('#event-feed-filter-ended_at').setValue('2026-08-01T23:59:59')
    await wrapper.get('form[role="search"]').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('The end time must not be earlier than the start time.')
    expect(mockApi.listEventFeed).toHaveBeenCalledTimes(initialCalls)

    await wrapper.get('#event-feed-filter-ended_at').setValue('2026-08-03T00:00:00')
    await wrapper.get('form[role="search"]').trigger('submit')
    await flushPromises()

    expect(mockApi.listEventFeed).toHaveBeenLastCalledWith(expect.objectContaining({
      started_at: new Date('2026-08-02T00:00:00').toISOString(),
      ended_at: new Date('2026-08-03T00:00:00').toISOString(),
    }))
  })

  it('confirms and deletes every result matching the active filters', async () => {
    const mockApi = api([item('api_call', 'short'), item('runtime', 'long')])
    const wrapper = await mountPage(mockApi)

    await wrapper.get('#event-feed-filter-source-runtime').setValue(true)
    await wrapper.get('#event-feed-filter-level-error').setValue(true)
    await wrapper.get('#event-feed-query').setValue('request-42')
    await wrapper.get('form[role="search"]').trigger('submit')
    await flushPromises()
    const remove = wrapper.findAll('button').find((button) => button.text() === 'Bulk delete')
    await remove!.trigger('click')
    expect(mockApi.deleteMatchingEventFeed).not.toHaveBeenCalled()
    useConfirmation().accept()
    await flushPromises()

    expect(mockApi.deleteMatchingEventFeed).toHaveBeenCalledWith(expect.objectContaining({
      source: ['api_call', 'runtime'],
      level: ['error'],
      query: 'request-42',
      started_at: expect.any(String),
      ended_at: expect.any(String),
    }))
  })

  it('confirms a destructive retention reduction before saving it', async () => {
    const mockApi = api([])
    const wrapper = await mountPage(mockApi)
    const apiRetention = wrapper.get('[data-testid="retention-api_call"]')

    await apiRetention.get('input').setValue('10')
    await apiRetention.trigger('submit')
    await flushPromises()
    expect(mockApi.updateApiHistoryRetention).not.toHaveBeenCalled()

    useConfirmation().accept()
    await flushPromises()
    expect(mockApi.updateApiHistoryRetention).toHaveBeenCalledWith(10)
  })

  it('saves the configurable one-file system log size', async () => {
    const mockApi = api([])
    const wrapper = await mountPage(mockApi)
    const settings = wrapper.get('[data-testid="system-log-settings"]')

    await settings.get('input').setValue('12')
    await settings.trigger('submit')
    await flushPromises()

    expect(mockApi.updateSystemLogSettings).toHaveBeenCalledWith(12)
    expect(wrapper.text()).toContain('Retention policy')
    expect(wrapper.text()).not.toContain('backups')
  })

  it('persists detailed diagnostics from the retention card', async () => {
    const mockApi = api([])
    const wrapper = await mountPage(mockApi)

    const retentionFields = [
      ...wrapper.findAll('[data-testid^="retention-"]'),
      wrapper.get('[data-testid="system-log-settings"]'),
    ]
    expect(retentionFields.every((field) => field.classes().includes('col-lg-3'))).toBe(true)
    expect(wrapper.text()).toContain('System log capacity')

    await wrapper.get('#verbose-diagnostics').setValue(true)
    await flushPromises()

    expect(mockApi.updateRuntimeDiagnostics).toHaveBeenCalledWith(true)
  })

  it('reloads controls from the page refresh action after an initial control failure', async () => {
    const mockApi = api([])
    mockApi.getInterceptionTest.mockRejectedValueOnce(new Error('control unavailable'))
    const wrapper = await mountPage(mockApi)

    expect(wrapper.find('[data-testid="retention-api_call"]').exists()).toBe(false)
    const refresh = wrapper.findAll('button').find((button) => button.text() === 'Refresh')
    await refresh!.trigger('click')
    await flushPromises()

    expect(mockApi.getInterceptionTest).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-testid="retention-api_call"]').exists()).toBe(true)
  })

  it('ignores an older feed response that finishes after a new search', async () => {
    const mockApi = api([])
    let resolveFirst!: (value: {
      items: EventFeedItem[]
      page: number
      page_size: number
      total: number
      total_pages: number
    }) => void
    mockApi.listEventFeed
      .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve }))
      .mockResolvedValueOnce({
        items: [item('api_call', 'new')],
        page: 1,
        page_size: 50,
        total: 1,
        total_pages: 1,
      })
    const wrapper = await mountPage(mockApi)

    await wrapper.get('#event-feed-query').setValue('new request')
    await wrapper.get('form[role="search"]').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('summary-new')

    resolveFirst({
      items: [item('api_call', 'old')],
      page: 1,
      page_size: 50,
      total: 1,
      total_pages: 1,
    })
    await flushPromises()
    expect(wrapper.text()).toContain('summary-new')
    expect(wrapper.text()).not.toContain('summary-old')
  })

  it('keeps the stale notice when an event arrives during a refresh', async () => {
    const mockApi = api([item('api_call', 'initial')])
    const wrapper = await mountPage(mockApi)
    let resolveRefresh!: (value: {
      items: EventFeedItem[]
      page: number
      page_size: number
      total: number
      total_pages: number
    }) => void
    mockApi.listEventFeed.mockImplementationOnce(
      () => new Promise((resolve) => { resolveRefresh = resolve }),
    )

    const refresh = wrapper.findAll('button').find((button) => button.text() === 'Refresh')
    await refresh!.trigger('click')
    mockApi.emit({ type: 'history_changed' })
    resolveRefresh({
      items: [item('api_call', 'refreshed')],
      page: 1,
      page_size: 50,
      total: 1,
      total_pages: 1,
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Load new events')
    expect(wrapper.text()).toContain('summary-refreshed')
  })

  it('uses numbered pages without changing the applied end time', async () => {
    const mockApi = api([])
    mockApi.listEventFeed
      .mockResolvedValueOnce({
        items: [item('api_call', 'first')],
        page: 1,
        page_size: 50,
        total: 51,
        total_pages: 2,
      })
      .mockResolvedValueOnce({
        items: [item('runtime', 'second')],
        page: 2,
        page_size: 50,
        total: 51,
        total_pages: 2,
      })
    const wrapper = await mountPage(mockApi)
    const firstWindow = mockApi.listEventFeed.mock.calls[0]![0]

    const next = wrapper.findAll('button').find((button) => button.text() === 'Next page')
    await next!.trigger('click')
    await flushPromises()

    expect(mockApi.listEventFeed).toHaveBeenLastCalledWith(expect.objectContaining({
      page: 2,
      started_at: firstWindow.started_at,
      ended_at: firstWindow.ended_at,
    }))
    expect(wrapper.findAll('[data-testid="data-table-row"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('summary-second')
    expect(wrapper.text()).not.toContain('summary-first')
  })

  it('refreshes the feed when filtered deletion fails', async () => {
    const mockApi = api([item('api_call', 'api-record')])
    mockApi.deleteMatchingEventFeed.mockRejectedValueOnce(new Error('delete failed'))
    const wrapper = await mountPage(mockApi)

    const remove = wrapper.findAll('button').find((button) => button.text() === 'Bulk delete')
    await remove!.trigger('click')
    useConfirmation().accept()
    await flushPromises()

    expect(mockApi.deleteMatchingEventFeed).toHaveBeenCalledWith(expect.objectContaining({
      source: ['api_call'],
      level: [],
      query: '',
      started_at: expect.any(String),
      ended_at: expect.any(String),
    }))
    expect(mockApi.listEventFeed).toHaveBeenCalledTimes(2)
  })
})
