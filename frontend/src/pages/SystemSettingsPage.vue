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
  type SystemSettings,
  type SystemSettingsUpdate,
} from '@/api'
import PageShell from '@/components/PageShell.vue'
import { useManagementError } from '@/composables/useManagementError'
import { useToasts } from '@/composables/useToasts'

interface SystemSettingsApi {
  getSystemSettings(): Promise<SystemSettings>
  updateSystemSettings(payload: SystemSettingsUpdate): Promise<SystemSettings>
  getApiServer(): Promise<ApiServerSettings>
  saveApiServer(payload: ApiServerSettingsUpdate): Promise<ApiServerSettings>
  getInterceptionTest(): Promise<{ enabled: boolean }>
  updateInterceptionTest(enabled: boolean): Promise<{ enabled: boolean }>
}

const props = defineProps<{ api?: SystemSettingsApi }>()
const api = props.api ?? managementApi
const { t } = useI18n()
const managementError = useManagementError()
const { notify } = useToasts()

const settings = ref<SystemSettings | null>(null)
const apiServerSettings = ref<ApiServerSettings | null>(null)
const loading = ref(true)
const saving = ref(false)
const pageError = ref('')
const host = ref('127.0.0.1')
const port = ref(19100)
const allowRemote = ref(false)
const managementPassword = ref('')
const showManagementPassword = ref(false)
const apiKey = ref('')
const apiKeyDirty = ref(false)
const showApiKey = ref(false)
const maxInitialMessages = ref(1000)
const interceptionEnabled = ref(false)
const corsOrigins = ref('')
const trustedProxies = ref('')

const apiKeyPlaceholder = computed(() => apiServerSettings.value?.api_key.configured
  ? t('common.configuredSecretPlaceholder')
  : t('common.apiKeyPlaceholder'))

const settingsValid = computed(() => {
  const normalizedPort = Number(port.value)
  const normalizedMessageLimit = Number(maxInitialMessages.value)
  return Number.isInteger(normalizedPort)
    && normalizedPort >= 1
    && normalizedPort <= 65_535
    && Number.isInteger(normalizedMessageLimit)
    && normalizedMessageLimit >= 1
    && normalizedMessageLimit <= 10_000
})

function lines(value: string): string[] {
  return value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
}

function applySystemSettings(value: SystemSettings): void {
  settings.value = value
  host.value = value.host
  port.value = value.port
  allowRemote.value = value.allow_remote
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

async function load(): Promise<void> {
  loading.value = true
  pageError.value = ''
  try {
    const [
      loadedSystemSettings,
      loadedApiServerSettings,
      loadedInterception,
    ] = await Promise.all([
      api.getSystemSettings(),
      api.getApiServer(),
      api.getInterceptionTest(),
    ])
    applySystemSettings(loadedSystemSettings)
    applyApiServerSettings(loadedApiServerSettings)
    applyInterceptionSetting(loadedInterception)
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
    ] = await Promise.all([
      api.updateSystemSettings({
        host: host.value.trim(),
        port: Number(port.value),
        allow_remote: allowRemote.value,
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
    ])
    applySystemSettings(savedSystemSettings)
    applyApiServerSettings(savedApiServerSettings)
    applyInterceptionSetting(savedInterception)
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
                <LteInput v-model="host" :label="t('systemSettings.host')" spellcheck="false" />
              </div>
              <div class="col-md-6">
                <label class="form-label" for="system-port">
                  {{ t('systemSettings.port') }}
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
                  {{ t('systemSettings.allowRemote') }}
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
                {{ t('systemSettings.managementPassword') }}
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
              <label class="form-label" for="api-server-key">{{ t('apiServer.key.title') }}</label>
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
            <label class="form-label" for="max-initial-messages">
              {{ t('apiServer.request.maxInitialMessages') }}
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
                    {{ t('eventFeed.controls.interception') }}
                  </label>
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
              <LteTextarea v-model="corsOrigins" :label="t('systemSettings.corsOrigins')" :rows="4" />
            </div>
            <LteTextarea v-model="trustedProxies" :label="t('systemSettings.trustedProxies')" :rows="4" />
            </div>
          </section>
        </div>
      </div>
    </form>
  </PageShell>
</template>
