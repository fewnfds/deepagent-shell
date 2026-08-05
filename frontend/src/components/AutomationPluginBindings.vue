<script setup lang="ts">
import { LteButton } from '@adminlte/vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import type { AutomationScriptResource } from '@/api'
import AutomationPluginConfigForm from '@/components/AutomationPluginConfigForm.vue'
import {
  blankAutomationPluginBinding,
  blankPeriodicAutomationPluginBinding,
  type AutomationConfigurationDraft,
  type AutomationPluginBindingDraft,
  type PeriodicAutomationPluginBindingDraft,
  type SubagentAutomationDraft,
} from '@/domain/automation'
import { automationConfigDefaults } from '@/domain/automationConfigSchema'

type BindingKind = 'hooks' | 'periodic'
type OverrideMode = 'inherit' | 'replace' | 'disabled'
type BindingDraft = AutomationPluginBindingDraft | PeriodicAutomationPluginBindingDraft

const bindingKinds: BindingKind[] = ['hooks', 'periodic']
const props = defineProps<{
  modelValue: AutomationConfigurationDraft | SubagentAutomationDraft
  plugins: AutomationScriptResource[]
  pathPrefix: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: AutomationConfigurationDraft | SubagentAutomationDraft]
}>()

const { t } = useI18n()
const isSubagent = computed(() => !Array.isArray(props.modelValue.hooks))

function selectionFor(kind: BindingKind) {
  if (!isSubagent.value) return null
  return (props.modelValue as SubagentAutomationDraft)[kind]
}

function pluginsFor(kind: BindingKind): BindingDraft[] {
  if (isSubagent.value) return selectionFor(kind)?.plugins ?? []
  return (props.modelValue as AutomationConfigurationDraft)[kind]
}

function updatePlugins(kind: BindingKind, plugins: BindingDraft[]): void {
  if (isSubagent.value) {
    const current = props.modelValue as SubagentAutomationDraft
    emit('update:modelValue', {
      ...current,
      [kind]: { ...current[kind], plugins },
    } as SubagentAutomationDraft)
    return
  }
  const current = props.modelValue as AutomationConfigurationDraft
  emit('update:modelValue', { ...current, [kind]: plugins } as AutomationConfigurationDraft)
}

function updateBinding(
  kind: BindingKind,
  index: number,
  patch: Partial<BindingDraft>,
): void {
  updatePlugins(kind, pluginsFor(kind).map((binding, current) => (
    current === index ? { ...binding, ...patch } as BindingDraft : binding
  )))
}

function addBinding(kind: BindingKind): void {
  const binding = kind === 'periodic'
    ? blankPeriodicAutomationPluginBinding()
    : blankAutomationPluginBinding()
  updatePlugins(kind, [...pluginsFor(kind), binding])
}

function removeBinding(kind: BindingKind, index: number): void {
  updatePlugins(kind, pluginsFor(kind).filter((_binding, current) => current !== index))
}

function moveBinding(kind: BindingKind, index: number, offset: number): void {
  const plugins = pluginsFor(kind)
  const target = index + offset
  if (target < 0 || target >= plugins.length) return
  const next = [...plugins]
  ;[next[index], next[target]] = [next[target]!, next[index]!]
  updatePlugins(kind, next)
}

function updateMode(kind: BindingKind, mode: OverrideMode): void {
  if (!isSubagent.value) return
  const current = props.modelValue as SubagentAutomationDraft
  emit('update:modelValue', {
    ...current,
    [kind]: {
      mode,
      plugins: mode === 'replace' ? current[kind].plugins : [],
    },
  } as SubagentAutomationDraft)
}

function isEditable(kind: BindingKind): boolean {
  return !isSubagent.value || selectionFor(kind)?.mode === 'replace'
}

function availablePlugins(kind: BindingKind): AutomationScriptResource[] {
  return props.plugins.filter((plugin) => (
    kind === 'periodic'
      ? plugin.entrypoints.includes('lifecycle')
      : plugin.entrypoints.some((entrypoint) => (
        entrypoint === 'middleware' || entrypoint === 'prepare'
      ))
  ))
}

function pluginLabel(plugin: AutomationScriptResource): string {
  const status = plugin.dependency_status === 'ready'
    ? ''
    : ` - ${t(`automation.scripts.status.${plugin.dependency_status === 'failed' ? 'failed' : 'restartRequired'}`)}`
  return `${plugin.name} (${plugin.id})${status}`
}

function selectedPlugin(binding: BindingDraft): AutomationScriptResource | undefined {
  return props.plugins.find((plugin) => plugin.id === binding.plugin_id)
}

function changePlugin(kind: BindingKind, index: number, pluginId: string): void {
  const plugin = props.plugins.find((item) => item.id === pluginId)
  updateBinding(kind, index, {
    plugin_id: pluginId,
    config: plugin ? automationConfigDefaults(plugin.config_schema) : {},
  })
}
</script>

<template>
  <section
    v-for="kind in bindingKinds"
    :key="kind"
    class="card mb-3"
    :aria-label="t(`automation.groups.${kind}`)"
  >
    <header class="card-header d-flex flex-wrap align-items-center justify-content-between gap-2">
      <h2 class="card-title mb-0">{{ t(`automation.groups.${kind}`) }}</h2>
      <LteButton
        v-if="isEditable(kind)"
        class="ms-auto"
        :aria-label="t('automation.bindings.add', { kind: t(`automation.groups.${kind}`) })"
        :title="t('automation.bindings.add', { kind: t(`automation.groups.${kind}`) })"
        size="sm"
        theme="success"
        type="button"
        @click="addBinding(kind)"
      >
        <i class="bi bi-plus-lg" aria-hidden="true" />
      </LteButton>
    </header>
    <div v-if="isSubagent" class="card-body">
      <select
        :id="`${pathPrefix}-${kind}-mode`"
        class="form-select"
        :aria-label="t('automation.bindings.mode', { kind: t(`automation.groups.${kind}`) })"
        :value="selectionFor(kind)?.mode"
        @change="updateMode(kind, ($event.target as HTMLSelectElement).value as OverrideMode)"
      >
        <option value="inherit">{{ t('agents.override.mode.inherit') }}</option>
        <option value="replace">{{ t('agents.override.mode.replace') }}</option>
        <option value="disabled">{{ t('agents.override.mode.disabled') }}</option>
      </select>
    </div>

    <div v-if="isEditable(kind) && pluginsFor(kind).length" class="list-group list-group-flush">
      <div
        v-for="(binding, index) in pluginsFor(kind)"
        :key="binding.key"
        class="list-group-item"
      >
        <div class="row g-3 align-items-end">
          <div class="col-lg-6">
            <label class="visually-hidden" :for="`${pathPrefix}-${kind}-plugin-${binding.key}`">
              {{ t('automation.bindings.plugin') }}
            </label>
            <select
              :id="`${pathPrefix}-${kind}-plugin-${binding.key}`"
              class="form-select"
              :data-testid="`automation-${kind}-plugin`"
              :value="binding.plugin_id"
              @change="changePlugin(kind, index, ($event.target as HTMLSelectElement).value)"
            >
              <option value="">{{ t('agents.capability.notAttached') }}</option>
              <option
                v-for="plugin in availablePlugins(kind)"
                :key="plugin.id"
                :value="plugin.id"
              >
                {{ pluginLabel(plugin) }}
              </option>
            </select>
          </div>
          <div v-if="kind === 'periodic'" class="col-lg-3">
            <label class="form-label" :for="`${pathPrefix}-${kind}-interval-${binding.key}`">
              {{ t('automation.bindings.interval') }}
            </label>
            <input
              :id="`${pathPrefix}-${kind}-interval-${binding.key}`"
              class="form-control"
              max="86400"
              min="0.1"
              step="0.1"
              type="number"
              :value="(binding as PeriodicAutomationPluginBindingDraft).interval_seconds"
              @input="updateBinding(kind, index, {
                interval_seconds: Number.isFinite(($event.target as HTMLInputElement).valueAsNumber)
                  ? ($event.target as HTMLInputElement).valueAsNumber
                  : 2,
              })"
            >
          </div>
          <div class="col-lg-3 ms-auto">
            <div class="d-flex align-items-center justify-content-end gap-2">
              <div class="form-check form-switch">
                <input
                  :id="`${pathPrefix}-${kind}-enabled-${binding.key}`"
                  class="form-check-input"
                  type="checkbox"
                  :checked="binding.enabled"
                  @change="updateBinding(kind, index, { enabled: ($event.target as HTMLInputElement).checked })"
                >
                <label class="visually-hidden" :for="`${pathPrefix}-${kind}-enabled-${binding.key}`">
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
                @click="moveBinding(kind, index, -1)"
              ><i class="bi bi-arrow-up" aria-hidden="true" /></LteButton>
              <LteButton
                :aria-label="t('automation.bindings.moveDown')"
                :disabled="index === pluginsFor(kind).length - 1"
                :title="t('automation.bindings.moveDown')"
                size="sm"
                theme="secondary"
                type="button"
                @click="moveBinding(kind, index, 1)"
              ><i class="bi bi-arrow-down" aria-hidden="true" /></LteButton>
              <LteButton
                :aria-label="t('automation.bindings.remove')"
                :title="t('automation.bindings.remove')"
                size="sm"
                theme="danger"
                type="button"
                @click="removeBinding(kind, index)"
              ><i class="bi bi-trash" aria-hidden="true" /></LteButton>
            </div>
          </div>
          <div v-if="selectedPlugin(binding)" class="col-12">
            <AutomationPluginConfigForm
              :id-prefix="`${pathPrefix}-${kind}-config-${binding.key}`"
              :model-value="binding.config"
              :schema="selectedPlugin(binding)!.config_schema"
              @update:model-value="updateBinding(kind, index, { config: $event })"
            />
          </div>
        </div>
      </div>
    </div>
    <div v-else-if="isEditable(kind)" class="card-body text-body-secondary">
      {{ t('automation.bindings.empty', { kind: t(`automation.groups.${kind}`) }) }}
    </div>
  </section>
</template>
