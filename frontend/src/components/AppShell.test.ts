import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  ManagementApiError,
  type ApiServerSettings,
  type CatalogResponse,
} from '@/api'
import { useToasts } from '@/composables/useToasts'
import { i18n, setLocale } from '@/locales'

import AppShell from './AppShell.vue'

const storage = new Map<string, string>()
const storageMock = {
  clear: () => storage.clear(),
  getItem: (key: string) => storage.get(key) ?? null,
  key: (index: number) => [...storage.keys()][index] ?? null,
  get length() {
    return storage.size
  },
  removeItem: (key: string) => storage.delete(key),
  setItem: (key: string, value: string) => storage.set(key, String(value)),
}

let narrow = false
let wrapper: VueWrapper | null = null

const stoppedSettings: ApiServerSettings = {
  enabled: false,
  status: 'stopped',
  api_key: { configured: true },
  max_initial_messages: 1000,
  api_base_url: 'http://127.0.0.1:19100/v1',
  models_endpoint: 'http://127.0.0.1:19100/v1/models',
  chat_completions_endpoint: 'http://127.0.0.1:19100/v1/chat/completions',
  runtime: 'model_streaming',
}

function createShellApi(overrides: Record<string, unknown> = {}) {
  return {
    getCatalog: vi.fn(async (): Promise<CatalogResponse> => ({
      block_types: [
        {
          type: 'skill',
          terminology_key: 'skill',
          label: 'Ignored',
          order: 2,
          icon_key: 'book',
          editor_key: 'skill',
          subagent_overrideable: true,
          required: false,
          subagent_policy: 'inherit',
          tool_names: [],
        },
        {
          type: 'model',
          terminology_key: 'model',
          label: 'Ignored',
          order: 1,
          icon_key: 'bot',
          editor_key: 'model',
          subagent_overrideable: true,
          required: true,
          subagent_policy: 'inherit',
          tool_names: [],
        },
      ],
      editor_defaults: {},
    })),
    getApiServer: vi.fn(async () => stoppedSettings),
    startApiServer: vi.fn(async () => ({ ...stoppedSettings, enabled: true, status: 'running' as const })),
    stopApiServer: vi.fn(async () => stoppedSettings),
    watchApiServerEvents: vi.fn(() => vi.fn()),
    ...overrides,
  }
}

function mediaQuery(query: string) {
  return {
    matches: query.includes('max-width') ? narrow : false,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }
}

function titleKeyForPath(path: string): string {
  if (path.startsWith('/system/')) return 'navigation.system'
  if (path.startsWith('/agents/')) return 'navigation.agents'
  if (path.startsWith('/components/')) return 'components.title'
  if (path.startsWith('/library/')) return 'library.title'
  if (path === '/terminology') return 'terminology.title'
  if (path === '/style-lab') return 'styleLab.title'
  return 'apiServer.homeTitle'
}

async function mountShell(path = '/', api = createShellApi()) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      '/',
      '/system/config',
      '/system/files',
      '/system/events',
      '/system/agent-sessions',
      '/style-lab',
      '/agents/primary',
      '/agents/subagents',
      '/components/model',
      '/components/skill',
      '/library/model',
      '/terminology',
    ].map((routePath) => ({
      path: routePath,
      component: { template: `<p>${routePath}</p>` },
      meta: { titleKey: titleKeyForPath(routePath) },
    })),
  })
  await router.push(path)
  await router.isReady()
  wrapper = mount(AppShell, {
    attachTo: document.body,
    props: { api },
    global: { plugins: [router, i18n] },
  })
  await nextTick()
  return { router, wrapper }
}

beforeEach(() => {
  narrow = false
  storage.clear()
  vi.stubGlobal('localStorage', storageMock)
  vi.stubGlobal('matchMedia', vi.fn(mediaQuery))
  setLocale('zh-CN')
})

afterEach(() => {
  const toasts = useToasts()
  for (const toast of toasts.items.value) toasts.dismiss(toast.id)
  wrapper?.unmount()
  wrapper = null
  document.body.className = ''
  document.body.innerHTML = ''
  document.documentElement.removeAttribute('data-bs-theme')
  storage.clear()
  vi.unstubAllGlobals()
})

describe('AppShell', () => {
  it('renders real hash-router navigation without AdminLTE demo content', async () => {
    const { wrapper: shell } = await mountShell('/system/files')

    expect(shell.get('a[href="/system/files"]').classes()).toContain('active')
    expect(shell.text()).toContain('文件管理')
    expect(shell.text()).not.toContain('Alexander Pierce')
    expect(shell.text()).not.toContain('Followers')
    expect(shell.find('[data-bs-toggle="dropdown"]').exists()).toBe(false)
    expect(shell.find('.app-footer').exists()).toBe(false)
    expect(shell.get('a[href="/"] .nav-icon').classes()).toContain('bi-house')
    expect(shell.get('a[href="/system/files"] .nav-icon').classes()).toContain('bi-circle')
    expect(shell.get('a[href="/system/agent-sessions"]').text()).toContain('历史会话')
    expect(shell.get('a[href="/system/agent-sessions"]').element.closest('ul')?.textContent).toContain('系统配置')
    expect(shell.get('a[href="/style-lab"] .nav-icon').classes()).toContain('bi-sliders')
    const topLevelLinks = shell.findAll('.nav-sidebar > .nav-item > .nav-link')
      .map((link) => link.attributes('href'))
    expect(topLevelLinks.indexOf('/style-lab')).toBeGreaterThan(topLevelLinks.indexOf('/terminology'))
    expect(shell.findAll('a[href^="/components/"]').map((link) => link.attributes('href')))
      .toEqual(['/components/model', '/components/skill'])
  })

  it('renders the localized route title beside the navigation toggle', async () => {
    const { router, wrapper: shell } = await mountShell('/system/files')

    const title = shell.get('.app-header .app-page-title')
    expect(title.element.previousElementSibling?.classList).toContain('navbar-nav')
    expect(title.text()).toBe('系统')

    await router.push('/components/model')
    await nextTick()
    expect(title.text()).toBe('组件配置')

    await shell.get('#app-language').trigger('click')
    await nextTick()
    expect(title.text()).toBe('Component configuration')
  })

  it('uses the official color-mode state and persists user changes', async () => {
    storage.set('lte-theme', 'dark')
    const { wrapper: shell } = await mountShell()

    const themeButton = shell.get('#app-theme')
    expect(themeButton.get('i').classes()).toContain('bi-moon-fill')
    expect(document.documentElement.getAttribute('data-bs-theme')).toBe('dark')

    await themeButton.trigger('click')
    await nextTick()

    expect(storage.get('lte-theme')).toBe('auto')
    expect(themeButton.get('i').classes()).toContain('bi-circle-half')

    await themeButton.trigger('click')
    await nextTick()

    expect(storage.get('lte-theme')).toBe('light')
    expect(document.documentElement.getAttribute('data-bs-theme')).toBe('light')
    expect(themeButton.get('i').classes()).toContain('bi-sun-fill')
  })

  it('shows and controls the API Server lifecycle from the right side of the navbar', async () => {
    const api = createShellApi()
    const { wrapper: shell } = await mountShell('/', api)
    await flushPromises()

    let statusButton = shell.get('#app-api-server-status')
    expect(statusButton.classes()).toContain('api-status-indicator--stopped')
    expect(statusButton.get('i').classes()).toContain('bi-stop-fill')
    expect(statusButton.attributes('title')).toContain('点击启动')

    await statusButton.trigger('click')
    await flushPromises()

    expect(api.startApiServer).toHaveBeenCalledTimes(1)
    statusButton = shell.get('#app-api-server-status')
    expect(statusButton.classes()).toContain('api-status-indicator--running')
    expect(statusButton.get('i').classes()).toContain('bi-play-fill')
    expect(statusButton.attributes('title')).toContain('点击停止')

    await statusButton.trigger('click')
    await flushPromises()
    expect(api.stopApiServer).toHaveBeenCalledTimes(1)
    expect(shell.get('#app-api-server-status').get('i').classes()).toContain('bi-stop-fill')
  })

  it('reports an API Server lifecycle failure once through the shared toast owner', async () => {
    const api = createShellApi({
      startApiServer: vi.fn().mockRejectedValue(new ManagementApiError({
        status: 422,
        code: 'configuration_validation_failed',
        message: 'raw backend detail',
        messageKey: 'validation.failure.configuration',
        requestId: 'request-navbar-start',
        validation: null,
      })),
    })
    const { wrapper: shell } = await mountShell('/', api)
    await flushPromises()

    await shell.get('#app-api-server-status').trigger('click')
    await flushPromises()

    expect(useToasts().items.value).toHaveLength(1)
    expect(useToasts().items.value[0]).toMatchObject({
      tone: 'danger',
      title: '启动 API Server 失败',
    })
    expect(useToasts().items.value[0]?.message).toContain('request-navbar-start')
  })

  it('switches language through the existing locale owner', async () => {
    const { wrapper: shell } = await mountShell()

    const languageButton = shell.get('#app-language')
    expect(languageButton.get('i').classes()).toContain('bi-translate')
    expect(languageButton.attributes('aria-label')).toBe('Switch to English')

    await languageButton.trigger('click')
    await nextTick()

    expect(document.documentElement.lang).toBe('en')
    expect(shell.text()).toContain('System settings')
    expect(languageButton.attributes('aria-label')).toBe('切换到中文')
  })

  it('collapses desktop navigation and closes the mobile sidebar after routing', async () => {
    const { router, wrapper: shell } = await mountShell()
    const toggle = shell.get('button[aria-label="展开或收起导航"]')

    await toggle.trigger('click')
    expect(document.body.classList.contains('sidebar-collapse')).toBe(true)

    document.body.classList.remove('sidebar-collapse')
    narrow = true
    await toggle.trigger('click')
    expect(document.body.classList.contains('sidebar-open')).toBe(true)

    await router.push('/terminology')
    await nextTick()

    expect(document.body.classList.contains('sidebar-open')).toBe(false)
    expect(document.activeElement?.id).toBe('main-content')
  })
})
