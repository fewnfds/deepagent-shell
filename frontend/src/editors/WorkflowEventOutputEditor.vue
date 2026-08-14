<script setup lang="ts">
import { LteButton, LteTextarea } from '@adminlte/vue'
import { computed, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'

import FormField from '@/components/FormField.vue'
import type {
  WorkflowEventOutputDefaults,
  WorkflowEventOutputDraft,
} from '@/domain/blocks'
import { useEditorModel } from './shared/useEditorModel'

const props = defineProps<{
  modelValue: WorkflowEventOutputDraft
  defaults: WorkflowEventOutputDefaults
}>()
const emit = defineEmits<{ 'update:modelValue': [value: WorkflowEventOutputDraft] }>()
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
  const id = `workflow-event-output-source-${eventKey.replace('.', '-')}`
  const textarea = document.getElementById(id) as HTMLTextAreaElement | null
  const start = textarea?.selectionStart ?? setting.output_source.length
  const end = textarea?.selectionEnd ?? start
  setting.output_source = `${setting.output_source.slice(0, start)}${token}${setting.output_source.slice(end)}`
  void nextTick(() => {
    const target = document.getElementById(id) as HTMLTextAreaElement | null
    target?.focus()
    target?.setSelectionRange(start + token.length, start + token.length)
  })
}
</script>

<template>
  <div data-editor="workflow-event-output">
    <article v-for="row in eventRows" :key="row.event.key" class="card mb-3" data-testid="workflow-event-output">
      <header class="card-header d-flex flex-wrap align-items-center gap-2">
        <h3 class="card-title">{{ t(`editors.workflowEventOutput.events.${row.event.key}.label`) }}</h3>
        <div class="form-check form-switch ms-auto">
          <input :id="`workflow-event-enabled-${row.event.key}`" v-model="row.setting.enabled" class="form-check-input" type="checkbox">
          <label class="form-check-label" :for="`workflow-event-enabled-${row.event.key}`">
            {{ row.setting.enabled ? t('editors.common.enabled') : t('editors.common.disabled') }}
          </label>
        </div>
      </header>
      <div class="card-body">
        <div class="d-flex flex-wrap gap-2 mb-3" :aria-label="t('editors.outputMode.fieldsTitle')">
          <LteButton
            v-for="field in row.event.fields"
            :key="field"
            class="font-monospace"
            size="sm"
            theme="secondary"
            type="button"
            @click="insertField(row.event.key, field)"
          >
            {{ field }}
          </LteButton>
        </div>
        <FormField :field-path="`event_outputs.${row.event.key}.output_source`" :hint="t('editors.outputMode.scriptHint')">
          <LteTextarea
            :id="`workflow-event-output-source-${row.event.key.replace('.', '-')}`"
            v-model="row.setting.output_source"
            :rows="9"
          />
        </FormField>
      </div>
    </article>
  </div>
</template>
