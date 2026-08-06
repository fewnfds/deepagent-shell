import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import type {
  ApiServerSettings,
  ConfigurationValidationSettings,
  SystemSettings,
} from '@/api'
import { i18n } from '@/locales'

import SystemSettingsPage from './SystemSettingsPage.vue'

const systemSettings: SystemSettings = {
  host: '127.0.0.1',
  port: 19100,
  allow_remote: false,
  langsmith_tracing_enabled: false,
  management_token: { configured: true },
  cors_origins: [],
  trusted_proxy_cidrs: [],
  restart_required: false,
  active_management_url: 'http://127.0.0.1:19100/admin',
}

const apiServerSettings: ApiServerSettings = {
  enabled: true,
  status: 'running',
  api_key: { configured: true },
  max_initial_messages: 1000,
  api_base_url: 'http://127.0.0.1:19100/v1',
  models_endpoint: 'http://127.0.0.1:19100/v1/models',
  chat_completions_endpoint: 'http://127.0.0.1:19100/v1/chat/completions',
  runtime: 'model_streaming',
}

function validationSettings(debounceMs: number): ConfigurationValidationSettings {
  return {
    debounce_ms: debounceMs,
    min_debounce_ms: 100,
    max_debounce_ms: 10_000,
  }
}

describe('SystemSettingsPage', () => {
  it('loads and saves the shared configuration alert interval', async () => {
    const api = {
      getSystemSettings: vi.fn(async () => systemSettings),
      updateSystemSettings: vi.fn(async () => systemSettings),
      getApiServer: vi.fn(async () => apiServerSettings),
      saveApiServer: vi.fn(async () => apiServerSettings),
      getInterceptionTest: vi.fn(async () => ({ enabled: false })),
      updateInterceptionTest: vi.fn(async () => ({ enabled: false })),
      getValidationSettings: vi.fn(async () => validationSettings(1000)),
      updateValidationSettings: vi.fn(async (value: number) => validationSettings(value)),
    }
    const wrapper = mount(SystemSettingsPage, {
      props: { api },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    const interval = wrapper.get('#configuration-validation-debounce')
    expect((interval.element as HTMLInputElement).value).toBe('1000')

    await interval.setValue('500')
    await wrapper.get('#system-settings-form').trigger('submit')
    await flushPromises()

    expect(api.updateValidationSettings).toHaveBeenCalledWith(500)
    wrapper.unmount()
  })

  it('shows backend wire fields instead of frontend refs in debug locale', async () => {
    i18n.global.locale.value = 'debug'
    const api = {
      getSystemSettings: vi.fn(async () => systemSettings),
      updateSystemSettings: vi.fn(async () => systemSettings),
      getApiServer: vi.fn(async () => apiServerSettings),
      saveApiServer: vi.fn(async () => apiServerSettings),
      getInterceptionTest: vi.fn(async () => ({ enabled: false })),
      updateInterceptionTest: vi.fn(async () => ({ enabled: false })),
      getValidationSettings: vi.fn(async () => validationSettings(1000)),
      updateValidationSettings: vi.fn(async (value: number) => validationSettings(value)),
    }
    const wrapper = mount(SystemSettingsPage, {
      props: { api },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    for (const wireField of [
      'host',
      'port',
      'allow_remote',
      'langsmith_tracing_enabled',
      'management_token',
      'api_key',
      'max_initial_messages',
      'debounce_ms',
      'cors_origins',
      'trusted_proxy_cidrs',
    ]) {
      expect(wrapper.text()).toContain(wireField)
    }
    expect(wrapper.text()).not.toContain('managementPassword')
    expect(wrapper.text()).not.toContain('trustedProxies')

    wrapper.unmount()
    i18n.global.locale.value = 'zh-CN'
  })
})
