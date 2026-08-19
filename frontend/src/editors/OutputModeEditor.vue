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
          <FormField :field-path="`event_outputs.${row.event.key}.output_source`">
            <LteTextarea :id="`event-output-source-${row.event.key}`" v-model="row.setting.output_source" :rows="9" />
          </FormField>
        </div>
      </article>
    </div>
  </div>
</template>
