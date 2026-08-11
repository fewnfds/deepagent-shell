import { flushPromises, mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'

import type { ManagementEvent } from '@/api'
import { en } from '@/locales/en'

import EventFeedPage from './EventFeedPage.vue'

function api() {
  return {
    listEventFeed: vi.fn(async () => ({
      items: [],
      page: 1,
      page_size: 50,
      total: 0,
      total_pages: 1,
    })),
    downloadEvent: vi.fn(async () => new Blob(['{}'])),
    getInterceptionTest: vi.fn(async () => ({ enabled: false })),
    getInterceptionRetention: vi.fn(async () => ({
      retention_limit: 20,
      max_retention_limit: 10_000,
    })),
    updateInterceptionRetention: vi.fn(async (retentionLimit: number) => ({
      retention_limit: retentionLimit,
      max_retention_limit: 10_000,
    })),
    getRuntimeDiagnostics: vi.fn(async () => ({
      retention_limit: 20,
      max_retention_limit: 10_000,
      debug_enabled: false,
    })),
    updateRuntimeLogRetention: vi.fn(async (retentionLimit: number) => ({
      retention_limit: retentionLimit,
      max_retention_limit: 10_000,
      debug_enabled: false,
    })),
    updateRuntimeDebug: vi.fn(async (enabled: boolean) => ({
      retention_limit: 20,
      max_retention_limit: 10_000,
      debug_enabled: enabled,
    })),
    getSystemLogSettings: vi.fn(async () => ({
      max_size_mib: 5,
      min_size_mib: 1,
      max_size_mib_limit: 1024,
    })),
    updateSystemLogSettings: vi.fn(async (maxSizeMib: number) => ({
      max_size_mib: maxSizeMib,
      min_size_mib: 1,
      max_size_mib_limit: 1024,
    })),
    deleteMatchingEventFeed: vi.fn(async () => ({ deleted: 0 })),
    watchApiServerEvents: vi.fn((_handler: (event: ManagementEvent) => void) => vi.fn()),
  }
}

async function mountPage(mockApi: ReturnType<typeof api>) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/system/events', component: EventFeedPage }],
  })
  await router.push('/system/events?source=runtime')
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

describe('EventFeedPage', () => {
  it('shows the supported log controls and saves the debug switch', async () => {
    const mockApi = api()
    const wrapper = await mountPage(mockApi)

    expect(wrapper.find('[data-testid="retention-interception"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="retention-runtime"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="retention-api_call"]').exists()).toBe(false)
    const debugSwitch = wrapper.get<HTMLInputElement>('#runtime-debug-enabled')
    expect(debugSwitch.element.checked).toBe(false)
    await debugSwitch.setValue(true)
    await flushPromises()
    expect(mockApi.updateRuntimeDebug).toHaveBeenCalledWith(true)
    expect(mockApi.listEventFeed).toHaveBeenCalledWith(expect.objectContaining({
      source: ['runtime'],
    }))
  })
})
