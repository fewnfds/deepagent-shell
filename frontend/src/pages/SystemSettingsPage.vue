<script setup lang="ts">
import {
  LteAlert,
  LteButton,
  LteInput,
  LteTextarea,
} from '@adminlte/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  managementApi,
  type ApiServerSettings,
  type ApiServerSettingsUpdate,
  type ConfigurationValidationSettings,
  type SystemSettings,
  type SystemSettingsUpdate,
} from '@/api'
import PageShell from '@/components/PageShell.vue'
import { useConfigurationValidationSettings } from '@/composables/useConfigurationValidationSettings'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'

interface SystemSettingsApi {
  getSystemSettings(): Promise<SystemSettings>
  updateSystemSettings(payload: SystemSettingsUpdate): Promise<SystemSettings>
  getApiServer(): Promise<ApiServerSettings>
  saveApiServer(payload: ApiServerSettingsUpdate): Promise<ApiServerSettings>
  getValidationSettings(): Promise<ConfigurationValidationSettings>
  updateValidationSettings(debounceMs: number): Promise<ConfigurationValidationSettings>
  getInterceptionTest(): Promise<{ enabled: boolean }>
  updateInterceptionTest(enabled: boolean): Promise<{ enabled: boolean }>
}

const props = defineProps<{ api?: SystemSettingsApi }>()
const api = props.api ?? managementApi
const { locale, t } = useI18n()
const managementError = useManagementError()
const { notify } = useToasts()
const validationSettingsController = useConfigurationValidationSettings()

const settings = ref<SystemSettings | null>(null)
const apiServerSettings = ref<ApiServerSettings | null>(null)
const loading = ref(true)
const saving = ref(false)
const pageError = ref('')
const host = ref('127.0.0.1')
const port = ref(19100)
const allowRemote = ref(false)
const langsmithTracingEnabled = ref(false)
const managementPassword = ref('')
const showManagementPassword = ref(false)
const apiKey = ref('')
const apiKeyDirty = ref(false)
const showApiKey = ref(false)
const maxInitialMessages = ref(1000)
const validationDebounceMs = ref(1000)
const validationDebounceMin = ref(100)
const validationDebounceMax = ref(10_000)
const interceptionEnabled = ref(false)
const corsOrigins = ref('')
const trustedProxies = ref('')

const apiKeyPlaceholder = computed(() => apiServerSettings.value?.api_key.configured
  ? t('common.configuredSecretPlaceholder')
  : t('common.apiKeyPlaceholder'))

function fieldLabel(messageKey: string, wireField: string): string {
  return locale.value === 'debug' ? wireField : t(messageKey)
}

const settingsValid = computed(() => {
  const normalizedPort = Number(port.value)
  const normalizedMessageLimit = Number(maxInitialMessages.value)
  const normalizedValidationDebounce = Number(validationDebounceMs.value)
  return Number.isInteger(normalizedPort)
    && normalizedPort >= 1
    && normalizedPort <= 65_535
    && Number.isInteger(normalizedMessageLimit)
    && normalizedMessageLimit >= 1
    && normalizedMessageLimit <= 10_000
    && Number.isInteger(normalizedValidationDebounce)
    && normalizedValidationDebounce >= validationDebounceMin.value
    && normalizedValidationDebounce <= validationDebounceMax.value
})

function lines(value: string): string[] {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
}

function applySystemSettings(value: SystemSettings): void {
  settings.value = value
  host.value = value.host
  port.value = value.port
  allowRemote.value = value.allow_remote
  langsmithTracingEnabled.value = value.langsmith_tracing_enabled
  corsOrigins.value = value.cors_origins.join('\n')
  trustedProxies.value = value.trusted_proxy_cidrs.join('\n')
  managementPassword.value = ''
  showManagementPassword.value = false
}

function applyApiServerSettings(value: ApiServerSettings): void {
  apiServerSettings.value = value
  apiKey.value = ''
  apiKeyDirty.value = false
  showApiKey.value = false
  maxInitialMessages.value = value.max_initial_messages
}

function applyInterceptionSetting(interception: { enabled: boolean }): void {
  interceptionEnabled.value = interception.enabled
}

function applyValidationSettings(value: ConfigurationValidationSettings): void {
  validationDebounceMs.value = value.debounce_ms
  validationDebounceMin.value = value.min_debounce_ms
  validationDebounceMax.value = value.max_debounce_ms
  validationSettingsController.apply(value)
}

async function load(): Promise<void> {
  loading.value = true
  pageError.value = ''
  try {
    const [
      loadedSystemSettings,
      loadedApiServerSettings,
      loadedInterception,
      loadedValidationSettings,
    ] = await Promise.all([
      api.getSystemSettings(),
      api.getApiServer(),
      api.getInterceptionTest(),
      api.getValidationSettings(),
    ])
    applySystemSettings(loadedSystemSettings)
    applyApiServerSettings(loadedApiServerSettings)
    applyInterceptionSetting(loadedInterception)
    applyValidationSettings(loadedValidationSettings)
  } catch (error) {
    pageError.value = managementError.describe(error).display
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (!settingsValid.value) {
    pageError.value = t('systemSettings.invalid')
    return
  }
  saving.value = true
  pageError.value = ''
  try {
    const apiKeyUpdate: ApiServerSettingsUpdate['api_key'] = apiKey.value
      ? { operation: 'replace', value: apiKey.value }
      : apiKeyDirty.value
        ? { operation: 'clear' }
        : { operation: 'keep' }
    const [
      savedSystemSettings,
      savedApiServerSettings,
      savedInterception,
      savedValidationSettings,
    ] = await Promise.all([
      api.updateSystemSettings({
        host: host.value.trim(),
        port: Number(port.value),
        allow_remote: allowRemote.value,
        langsmith_tracing_enabled: langsmithTracingEnabled.value,
        management_token: managementPassword.value
          ? { operation: 'replace', value: managementPassword.value }
          : { operation: 'preserve' },
        cors_origins: lines(corsOrigins.value),
        trusted_proxy_cidrs: lines(trustedProxies.value),
      }),
      api.saveApiServer({
        api_key: apiKeyUpdate,
        max_initial_messages: Number(maxInitialMessages.value),
      }),
      api.updateInterceptionTest(interceptionEnabled.value),
      api.updateValidationSettings(Number(validationDebounceMs.value)),
    ])
    applySystemSettings(savedSystemSettings)
    applyApiServerSettings(savedApiServerSettings)
    applyInterceptionSetting(savedInterception)
    applyValidationSettings(savedValidationSettings)
    notify({ tone: 'success', title: t('systemSettings.saved') })
  } catch (error) {
    pageError.value = managementError.describe(error).display
  } finally {
    saving.value = false
  }
}

onMounted(() => { void load() })
</script>

<template>
  <PageShell>
    <template #actions>
      <LteButton :disabled="loading || saving" theme="info" type="button" @click="load">
        <span v-if="loading" class="spinner-border spinner-border-sm" aria-hidden="true" />
        {{ t('common.refresh') }}
      </LteButton>
      <LteButton
        :disabled="loading || !settings || !apiServerSettings || saving || !settingsValid"
        theme="primary"
        type="button"
        @click="save"
      >
        <span v-if="saving" class="spinner-border spinner-border-sm" aria-hidden="true" />
        {{ t('common.save') }}
      </LteButton>
    </template>

    <template #status>
      <LteAlert v-if="pageError" theme="danger" :title="t('systemSettings.saveFailed')">
        {{ pageError }}
      </LteAlert>
      <LteAlert
        v-else-if="settings?.restart_required"
        theme="warning"
        :title="t('systemSettings.restartRequired')"
      >
        <span class="font-monospace text-break">{{ settings.active_management_url }}</span>
      </LteAlert>
    </template>

    <div v-if="loading" class="d-flex align-items-center gap-2" aria-busy="true">
      <span class="spinner-border" aria-hidden="true" />
      <span>{{ t('common.loading') }}</span>
    </div>

    <form
      v-else-if="settings && apiServerSettings"
      id="system-settings-form"
      data-testid="system-settings-form"
      @submit.prevent="save"
    >
      <div class="row g-3">
        <div class="col-lg-6">
          <section class="card mb-3" data-testid="system-card-network">
            <header class="card-header">
              <h2 class="card-title">
                <i class="bi bi-hdd-network me-2" aria-hidden="true" />
                {{ t('systemSettings.network') }}
              </h2>
            </header>
            <div class="card-body">
              <div class="row g-3">
                <div class="col-md-6">
                  <LteInput v-model="host" :label="fieldLabel('systemSettings.host', 'host')" spellcheck="false" />
                </div>
                <div class="col-md-6">
                  <label class="form-label" for="system-port">
                    {{ fieldLabel('systemSettings.port', 'port') }}
                  </label>
                  <input
                    id="system-port"
                    v-model.number="port"
                    class="form-control"
                    max="65535"
                    min="1"
                    required
                    step="1"
                    type="number"
                  >
                </div>
              </div>
              <div class="mt-3">
                <div class="form-check form-switch">
                  <input
                    id="allow-remote"
                    v-model="allowRemote"
                    class="form-check-input"
                    role="switch"
                    type="checkbox"
                  >
                  <label class="form-check-label" for="allow-remote">
                    {{ fieldLabel('systemSettings.allowRemote', 'allow_remote') }}
                  </label>
                </div>
              </div>
            </div>
          </section>

          <section class="card" data-testid="system-card-credentials">
            <header class="card-header">
              <h2 class="card-title">
                <i class="bi bi-key me-2" aria-hidden="true" />
                {{ t('systemSettings.credentials') }}
              </h2>
            </header>
            <div class="card-body">
              <div class="mb-3">
                <label class="form-label" for="management-password">
                  {{ fieldLabel('systemSettings.managementPassword', 'management_token') }}
                </label>
                <div class="input-group">
                  <input
                    id="management-password"
                    v-model="managementPassword"
                    autocomplete="new-password"
                    class="form-control"
                    :placeholder="settings.management_token.configured ? t('common.configuredSecretPlaceholder') : ''"
                    spellcheck="false"
                    :type="showManagementPassword ? 'text' : 'password'"
                  >
                  <LteButton
                    :aria-label="showManagementPassword ? t('common.hide') : t('common.show')"
                    :aria-pressed="showManagementPassword"
                    theme="info"
                    type="button"
                    @click="showManagementPassword = !showManagementPassword"
                  >
                    <i v-if="showManagementPassword" class="bi bi-eye-slash" aria-hidden="true" />
                    <i v-else class="bi bi-eye" aria-hidden="true" />
                  </LteButton>
                </div>
              </div>

              <div>
                <label class="form-label" for="api-server-key">{{ fieldLabel('apiServer.key.title', 'api_key') }}</label>
                <div class="input-group">
                  <input
                    id="api-server-key"
                    v-model="apiKey"
                    autocomplete="off"
                    class="form-control"
                    :placeholder="apiKeyPlaceholder"
                    spellcheck="false"
                    :type="showApiKey ? 'text' : 'password'"
                    @input="apiKeyDirty = true"
                  >
                  <LteButton
                    :aria-label="showApiKey ? t('common.hide') : t('common.show')"
                    :aria-pressed="showApiKey"
                    theme="info"
                    type="button"
                    @click="showApiKey = !showApiKey"
                  >
                    <i v-if="showApiKey" class="bi bi-eye-slash" aria-hidden="true" />
                    <i v-else class="bi bi-eye" aria-hidden="true" />
                  </LteButton>
                </div>
              </div>
            </div>
          </section>
        </div>

        <div class="col-lg-6">
          <section class="card mb-3" data-testid="system-card-runtime">
            <header class="card-header">
              <h2 class="card-title">
                <i class="bi bi-sliders me-2" aria-hidden="true" />
                {{ t('systemSettings.runtimeControls') }}
              </h2>
            </header>
            <div class="card-body">
              <div class="mb-3">
                <label class="form-label" for="max-initial-messages">
                  {{ fieldLabel('apiServer.request.maxInitialMessages', 'max_initial_messages') }}
                </label>
                <input
                  id="max-initial-messages"
                  v-model.number="maxInitialMessages"
                  class="form-control"
                  max="10000"
                  min="1"
                  required
                  step="1"
                  type="number"
                >
              </div>

              <div>
                <label class="form-label" for="configuration-validation-debounce">
                  {{ fieldLabel('systemSettings.validationDebounceMs', 'debounce_ms') }}
                </label>
                <input
                  id="configuration-validation-debounce"
                  v-model.number="validationDebounceMs"
                  class="form-control"
                  :max="validationDebounceMax"
                  :min="validationDebounceMin"
                  required
                  step="100"
                  type="number"
                >
              </div>

              <div class="row g-3 mt-2">
                <div class="col-md-6">
                  <div class="form-check form-switch">
                    <input
                      id="interception-test"
                      v-model="interceptionEnabled"
                      class="form-check-input"
                      role="switch"
                      type="checkbox"
                    >
                    <label class="form-check-label" for="interception-test">
                      {{ fieldLabel('eventFeed.controls.interception', 'enabled') }}
                    </label>
                  </div>
                </div>
                <div class="col-12">
                  <div class="form-check form-switch">
                    <input
                      id="langsmith-tracing"
                      v-model="langsmithTracingEnabled"
                      class="form-check-input"
                      role="switch"
                      type="checkbox"
                    >
                    <label class="form-check-label" for="langsmith-tracing">
                      {{ fieldLabel('systemSettings.langsmithTracing', 'langsmith_tracing_enabled') }}
                    </label>
                  </div>
                  <div class="form-text">
                    {{ t('systemSettings.langsmithTracingHint') }}
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section class="card" data-testid="system-card-proxy">
            <header class="card-header">
              <h2 class="card-title">
                <i class="bi bi-shield-lock me-2" aria-hidden="true" />
                {{ t('systemSettings.proxyAndDiagnostics') }}
              </h2>
            </header>
            <div class="card-body">
              <div class="mb-3">
                <LteTextarea v-model="corsOrigins" :label="fieldLabel('systemSettings.corsOrigins', 'cors_origins')" :rows="4" />
              </div>
              <LteTextarea v-model="trustedProxies" :label="fieldLabel('systemSettings.trustedProxies', 'trusted_proxy_cidrs')" :rows="4" />
            </div>
          </section>
        </div>
      </div>
    </form>
  </PageShell>
</template>
