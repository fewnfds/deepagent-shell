<script setup lang="ts">
import { LteButton, LteTextarea } from '@adminlte/vue'
import { computed, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'

import FormField from '@/components/FormField.vue'
import {
  type OutputModeDefaults,
  type OutputModeDraft,
} from '@/domain/blocks'

import { useEditorModel } from './shared/useEditorModel'

const props = defineProps<{
  modelValue: OutputModeDraft
  defaults: OutputModeDefaults
}>()
const emit = defineEmits<{ 'update:modelValue': [value: OutputModeDraft] }>()
const { t } = useI18n()
const draft = useEditorModel(() => props.modelValue, (value) => emit('update:modelValue', value))

const eventRows = computed(() => props.defaults.events.flatMap((event) => {
  const setting = draft.event_outputs[event.key]
  return setting ? [{ event, setting }] : []
}))

function insertField(eventKey: string, field: string): void {
  const setting = draft.event_outputs[eventKey]
  if (!setting) return
  const token = `event[${JSON.stringify(field)}]`
  const textarea = document.getElementById(`event-output-source-${eventKey}`) as HTMLTextAreaElement | null
  const start = textarea?.selectionStart ?? setting.output_source.length
  const end = textarea?.selectionEnd ?? start
  setting.output_source = `${setting.output_source.slice(0, start)}${token}${setting.output_source.slice(end)}`
  void nextTick(() => {
    const target = document.getElementById(`event-output-source-${eventKey}`) as HTMLTextAreaElement | null
    target?.focus()
    target?.setSelectionRange(start + token.length, start + token.length)
  })
}
</script>

<template>
  <div data-editor="output-mode">
    <section class="card mb-3" data-testid="output-filter-settings">
      <header class="card-header">
        <h3 class="card-title">{{ t('editors.outputMode.filtersTitle') }}</h3>
        <p class="small text-body-secondary mb-0">{{ t('editors.outputMode.filtersHint') }}</p>
      </header>
      <div class="card-body">
        <div class="row g-3">
          <div class="col-12">
            <FormField field-path="filter_mode">
              <select v-model="draft.filter_mode" class="form-select">
                <option value="allowlist">{{ t('editors.outputMode.allowlist') }}</option>
                <option value="blocklist">{{ t('editors.outputMode.blocklist') }}</option>
              </select>
            </FormField>
          </div>
        </div>
        <p class="text-body-secondary mb-3">{{ t('editors.outputMode.mappingHint') }}</p>
        <div v-if="draft.filter_mappings.length" class="simple-mapping-list">
          <div v-for="(mapping, index) in draft.filter_mappings" :key="index" class="simple-mapping-row" data-testid="output-filter-row">
            <div class="simple-mapping-primary">
              <label class="visually-hidden" :for="`output-filter-field-${index}`">{{ t('fields.field') }}</label>
              <input :id="`output-filter-field-${index}`" v-model="mapping.field" class="form-control" :list="`filter-fields-${index}`">
              <datalist :id="`filter-fields-${index}`">
                <option v-for="field in defaults.filter_fields" :key="field" :value="field" />
              </datalist>
            </div>
            <div class="simple-mapping-secondary">
              <label class="visually-hidden" :for="`output-filter-value-${index}`">{{ t('fields.value') }}</label>
              <input :id="`output-filter-value-${index}`" v-model="mapping.value" class="form-control">
            </div>
            <div class="simple-mapping-actions">
              <LteButton :aria-label="t('editors.common.remove')" :title="t('editors.common.remove')" size="sm" theme="danger" type="button" @click="draft.filter_mappings.splice(index, 1)"><i class="bi bi-trash" aria-hidden="true" /></LteButton>
            </div>
          </div>
        </div>
        <p v-else class="text-body-secondary mb-0">{{ t('editors.outputMode.emptyMappings') }}</p>
        <div class="simple-mapping-footer">
          <LteButton :aria-label="t('editors.outputMode.addMapping')" :title="t('editors.outputMode.addMapping')" data-action="add-filter-mapping" size="sm" theme="success" type="button" @click="draft.filter_mappings.push({ field: '', value: '' })">
            <i class="bi bi-plus-lg" aria-hidden="true" />
          </LteButton>
        </div>
      </div>
    </section>

    <div data-testid="event-output-list">
      <article v-for="row in eventRows" :key="row.event.key" class="card mb-3" data-testid="event-output-script">
        <header class="card-header d-flex flex-wrap align-items-center justify-content-between gap-2">
          <h3 class="card-title">{{ t(`editors.outputMode.events.${row.event.key}.label`) }}</h3>
          <div class="form-check form-switch ms-auto">
            <input :id="`event-enabled-${row.event.key}`" v-model="row.setting.enabled" class="form-check-input" type="checkbox">
            <label class="form-check-label" :for="`event-enabled-${row.event.key}`">
              {{ row.setting.enabled ? t('editors.common.enabled') : t('editors.common.disabled') }}
            </label>
          </div>
        </header>
        <div class="card-body">
          <div
            v-if="row.event.fields.length"
            class="d-flex flex-wrap gap-2 mb-3"
            :aria-label="t('editors.outputMode.fieldsTitle')"
          >
            <LteButton
              v-for="field in row.event.fields"
              :key="field"
              class="font-monospace"
              data-testid="output-field"
              size="sm"
              theme="secondary"
              type="button"
              @click="insertField(row.event.key, field)"
            >
              {{ field }}
            </LteButton>
          </div>
          <FormField :field-path="`event_outputs.${row.event.key}.output_source`" :hint="t('editors.outputMode.scriptHint')">
            <LteTextarea :id="`event-output-source-${row.event.key}`" v-model="row.setting.output_source" :rows="9" />
          </FormField>
        </div>
      </article>
    </div>
  </div>
</template>
