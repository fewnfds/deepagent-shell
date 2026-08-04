import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { managementApi } from '@/api'
import AutomationPage from './AutomationPage.vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key, te: () => true }),
}))

afterEach(() => {
  vi.restoreAllMocks()
})

async function mountPage() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/automation', component: AutomationPage }],
  })
  await router.push('/automation')
  await router.isReady()
  const wrapper = mount(AutomationPage, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('AutomationPage', () => {
  it('shows installed plugin entrypoints and requirements', async () => {
    vi.spyOn(managementApi, 'listAutomationPlugins').mockResolvedValue({
      catalog: [{
        api_version: 2,
        id: 'market-context',
        name: 'Market context',
        description: 'Prepares current market messages.',
        entrypoints: ['middleware', 'prepare', 'complete'],
        folder: 'market-context',
        python_requirements: ['example-market-sdk>=2'],
        requirements_fingerprint: 'market-fingerprint',
        dependency_status: 'ready',
        dependency_error_code: '',
      }],
      errors: {},
    })

    const wrapper = await mountPage()

    expect(wrapper.text()).toContain('Market context')
    expect(wrapper.text()).toContain('market-context')
    expect(wrapper.text()).toContain('automation.entrypoints.middleware')
    expect(wrapper.text()).toContain('automation.entrypoints.prepare')
    expect(wrapper.text()).toContain('automation.entrypoints.complete')
    expect(wrapper.text()).toContain('example-market-sdk>=2')
    expect(wrapper.text()).toContain('automation.scripts.status.ready')
    wrapper.unmount()
  })

  it('reports dependency restart state and invalid plugin folders', async () => {
    vi.spyOn(managementApi, 'listAutomationPlugins').mockResolvedValue({
      catalog: [{
        api_version: 2,
        id: 'image-reader',
        name: 'Image reader',
        description: 'Reads image metadata.',
        entrypoints: ['prepare'],
        folder: 'image-reader',
        python_requirements: ['Pillow>=11'],
        requirements_fingerprint: 'pillow-fingerprint',
        dependency_status: 'restart_required',
        dependency_error_code: '',
      }],
      errors: {
        broken: {
          message_key: 'resource.error.automationScript.manifestInvalid',
          message: 'Invalid manifest.',
          message_args: {},
        },
      },
    })

    const wrapper = await mountPage()

    expect(wrapper.text()).toContain('automation.scripts.invalid')
    expect(wrapper.text()).toContain('automation.scripts.status.restartRequired')
    wrapper.unmount()
  })
})
