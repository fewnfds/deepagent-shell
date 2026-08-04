<script setup lang="ts">
import { LteButton } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import type { AutomationScriptResource } from '@/api'
import {
  blankAutomationPluginBinding,
  type AutomationConfigurationDraft,
  type AutomationPluginBindingDraft,
} from '@/domain/automation'

const props = defineProps<{
  modelValue: AutomationConfigurationDraft
  plugins: AutomationScriptResource[]
  pathPrefix: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: AutomationConfigurationDraft]
}>()

const { t } = useI18n()

function updatePlugins(plugins: AutomationPluginBindingDraft[]): void {
  emit('update:modelValue', { ...props.modelValue, plugins })
}

function updateBinding(index: number, patch: Partial<AutomationPluginBindingDraft>): void {
  updatePlugins(props.modelValue.plugins.map((binding, current) => (
    current === index ? { ...binding, ...patch } : binding
  )))
}

function addBinding(): void {
  updatePlugins([...props.modelValue.plugins, blankAutomationPluginBinding()])
}

function removeBinding(index: number): void {
  updatePlugins(props.modelValue.plugins.filter((_binding, current) => current !== index))
}

function moveBinding(index: number, offset: number): void {
  const target = index + offset
  if (target < 0 || target >= props.modelValue.plugins.length) return
  const next = [...props.modelValue.plugins]
  ;[next[index], next[target]] = [next[target]!, next[index]!]
  updatePlugins(next)
}

function updateLifecycle(enabled: boolean): void {
  emit('update:modelValue', {
    ...props.modelValue,
    lifecycle_interval_seconds: enabled
      ? props.modelValue.lifecycle_interval_seconds ?? 2
      : null,
  })
}

function updateInterval(value: number): void {
  emit('update:modelValue', {
    ...props.modelValue,
    lifecycle_interval_seconds: Number.isFinite(value) ? value : 2,
  })
}

function pluginLabel(plugin: AutomationScriptResource): string {
  const status = plugin.dependency_status === 'ready'
    ? ''
    : ` - ${t(`automation.scripts.status.${plugin.dependency_status === 'failed' ? 'failed' : 'restartRequired'}`)}`
  return `${plugin.name} (${plugin.id})${status}`
}
</script>

<template>
  <section class="card mb-3" :aria-label="t('agents.automation.title')">
    <header class="card-header d-flex flex-wrap align-items-center justify-content-between gap-2">
      <h2 class="card-title mb-0">{{ t('agents.automation.title') }}</h2>
      <LteButton
        :aria-label="t('automation.bindings.add')"
        :title="t('automation.bindings.add')"
        size="sm"
        theme="success"
        type="button"
        @click="addBinding"
      >
        <i class="bi bi-plus-lg" aria-hidden="true" />
      </LteButton>
    </header>

    <div v-if="modelValue.plugins.length" class="list-group list-group-flush">
      <div
        v-for="(binding, index) in modelValue.plugins"
        :key="binding.key"
        class="list-group-item"
      >
        <div class="row g-3 align-items-end">
          <div class="col-lg-8">
            <label class="form-label" :for="`${pathPrefix}-plugin-${binding.key}`">
              {{ t('automation.bindings.plugin') }}
            </label>
            <select
              :id="`${pathPrefix}-plugin-${binding.key}`"
              class="form-select"
              :value="binding.plugin_id"
              @change="updateBinding(index, { plugin_id: ($event.target as HTMLSelectElement).value })"
            >
              <option value="">{{ t('agents.capability.notAttached') }}</option>
              <option v-for="plugin in plugins" :key="plugin.id" :value="plugin.id">
                {{ pluginLabel(plugin) }}
              </option>
            </select>
          </div>
          <div class="col-lg-4">
            <div class="d-flex align-items-center justify-content-end gap-2">
              <div class="form-check form-switch">
                <input
                  :id="`${pathPrefix}-enabled-${binding.key}`"
                  class="form-check-input"
                  type="checkbox"
                  :checked="binding.enabled"
                  @change="updateBinding(index, { enabled: ($event.target as HTMLInputElement).checked })"
                >
                <label class="form-check-label" :for="`${pathPrefix}-enabled-${binding.key}`">
                  {{ t('automation.bindings.enabled') }}
                </label>
              </div>
              <LteButton
                :aria-label="t('automation.bindings.moveUp')"
                :disabled="index === 0"
                :title="t('automation.bindings.moveUp')"
                size="sm"
                theme="secondary"
                type="button"
                @click="moveBinding(index, -1)"
              ><i class="bi bi-arrow-up" aria-hidden="true" /></LteButton>
              <LteButton
                :aria-label="t('automation.bindings.moveDown')"
                :disabled="index === modelValue.plugins.length - 1"
                :title="t('automation.bindings.moveDown')"
                size="sm"
                theme="secondary"
                type="button"
                @click="moveBinding(index, 1)"
              ><i class="bi bi-arrow-down" aria-hidden="true" /></LteButton>
              <LteButton
                :aria-label="t('automation.bindings.remove')"
                :title="t('automation.bindings.remove')"
                size="sm"
                theme="danger"
                type="button"
                @click="removeBinding(index)"
              ><i class="bi bi-trash" aria-hidden="true" /></LteButton>
            </div>
          </div>
          <div class="col-12">
            <label class="form-label" :for="`${pathPrefix}-config-${binding.key}`">
              {{ t('automation.bindings.config') }}
            </label>
            <textarea
              :id="`${pathPrefix}-config-${binding.key}`"
              class="form-control font-monospace"
              rows="4"
              :value="binding.config_text"
              @input="updateBinding(index, { config_text: ($event.target as HTMLTextAreaElement).value })"
            />
          </div>
        </div>
      </div>
    </div>
    <div v-else class="card-body text-body-secondary">{{ t('automation.bindings.empty') }}</div>

    <footer class="card-footer">
      <div class="row g-3 align-items-end">
        <div class="col-md-6">
          <div class="form-check form-switch">
            <input
              :id="`${pathPrefix}-lifecycle-enabled`"
              class="form-check-input"
              type="checkbox"
              :checked="modelValue.lifecycle_interval_seconds !== null"
              @change="updateLifecycle(($event.target as HTMLInputElement).checked)"
            >
            <label class="form-check-label" :for="`${pathPrefix}-lifecycle-enabled`">
              {{ t('automation.lifecycle.enabled') }}
            </label>
          </div>
        </div>
        <div v-if="modelValue.lifecycle_interval_seconds !== null" class="col-md-6">
          <label class="form-label" :for="`${pathPrefix}-lifecycle-interval`">
            {{ t('automation.lifecycle.interval') }}
          </label>
          <input
            :id="`${pathPrefix}-lifecycle-interval`"
            class="form-control"
            max="86400"
            min="0.1"
            step="0.1"
            type="number"
            :value="modelValue.lifecycle_interval_seconds"
            @input="updateInterval(($event.target as HTMLInputElement).valueAsNumber)"
          >
        </div>
      </div>
    </footer>
  </section>
</template>
