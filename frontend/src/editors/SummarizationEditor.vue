<script setup lang="ts">
import { LteButton, LteTextarea } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import FormField from '@/components/FormField.vue'
import type {
  SummarizationDefaults,
  SummarizationDraft,
  SummarizationThresholdDraft,
  SummarizationThresholdType,
} from '@/domain/blocks'
import { useEditorModel } from './shared/useEditorModel'

const props = defineProps<{
  modelValue: SummarizationDraft
  defaults: SummarizationDefaults
}>()
const emit = defineEmits<{ 'update:modelValue': [value: SummarizationDraft] }>()
const { t } = useI18n()
const draft = useEditorModel(() => props.modelValue, (value) => emit('update:modelValue', value))
const thresholdTypes: SummarizationThresholdType[] = ['auto', 'fraction', 'tokens', 'messages']

function thresholdDefaultValue(type: SummarizationThresholdType): number | null {
  if (type === 'auto') return null
  if (type === 'fraction') return 0.85
  if (type === 'messages') return 20
  return null
}

function setThresholdType(threshold: SummarizationThresholdDraft, event: Event): void {
  const type = (event.target as HTMLSelectElement).value as SummarizationThresholdType
  if (threshold.type === type) return
  threshold.type = type
  threshold.value = thresholdDefaultValue(type)
}
</script>

<template>
  <div data-editor="summarization">
    <div class="form-check form-switch mb-3">
      <input id="summarization-enabled" v-model="draft.enabled" class="form-check-input" type="checkbox">
      <label class="form-check-label" for="summarization-enabled">
        {{ draft.enabled ? t('common.enabled') : t('common.disabled') }}
      </label>
    </div>

    <div class="row g-3">
      <div class="col-lg-3">
        <FormField field-path="trigger.type">
          <select :value="draft.trigger.type" class="form-select" @change="setThresholdType(draft.trigger, $event)">
            <option v-for="type in thresholdTypes" :key="type" :value="type">{{ t(`editors.summarization.thresholdTypes.${type}`) }}</option>
          </select>
        </FormField>
      </div>
      <div class="col-lg-3">
        <FormField field-path="trigger.value">
          <input v-model.number="draft.trigger.value" class="form-control" :disabled="draft.trigger.type === 'auto'" :max="draft.trigger.type === 'fraction' ? 1 : undefined" :min="draft.trigger.type === 'fraction' ? 0.01 : 1" :step="draft.trigger.type === 'fraction' ? 0.01 : 1" type="number">
        </FormField>
      </div>
      <div class="col-lg-3">
        <FormField field-path="keep.type">
          <select :value="draft.keep.type" class="form-select" @change="setThresholdType(draft.keep, $event)">
            <option v-for="type in thresholdTypes" :key="type" :value="type">{{ t(`editors.summarization.thresholdTypes.${type}`) }}</option>
          </select>
        </FormField>
      </div>
      <div class="col-lg-3">
        <FormField field-path="keep.value">
          <input v-model.number="draft.keep.value" class="form-control" :disabled="draft.keep.type === 'auto'" :max="draft.keep.type === 'fraction' ? 1 : undefined" :min="draft.keep.type === 'fraction' ? 0.01 : 1" :step="draft.keep.type === 'fraction' ? 0.01 : 1" type="number">
        </FormField>
      </div>
    </div>

    <div class="form-check form-switch mb-3">
      <input id="summarization-truncate-args-enabled" v-model="draft.truncate_args_enabled" class="form-check-input" type="checkbox">
      <label class="form-check-label" for="summarization-truncate-args-enabled">{{ t('editors.summarization.truncateArgsEnabled') }}</label>
    </div>
    <div class="row g-3">
      <div class="col-lg-3">
        <FormField field-path="truncate_args_trigger.type">
          <select :value="draft.truncate_args_trigger.type" class="form-select" :disabled="!draft.truncate_args_enabled" @change="setThresholdType(draft.truncate_args_trigger, $event)">
            <option v-for="type in thresholdTypes" :key="type" :value="type">{{ t(`editors.summarization.thresholdTypes.${type}`) }}</option>
          </select>
        </FormField>
      </div>
      <div class="col-lg-3">
        <FormField field-path="truncate_args_trigger.value">
          <input v-model.number="draft.truncate_args_trigger.value" class="form-control" :disabled="!draft.truncate_args_enabled || draft.truncate_args_trigger.type === 'auto'" :max="draft.truncate_args_trigger.type === 'fraction' ? 1 : undefined" :min="draft.truncate_args_trigger.type === 'fraction' ? 0.01 : 1" :step="draft.truncate_args_trigger.type === 'fraction' ? 0.01 : 1" type="number">
        </FormField>
      </div>
      <div class="col-lg-3">
        <FormField field-path="truncate_args_keep.type">
          <select :value="draft.truncate_args_keep.type" class="form-select" :disabled="!draft.truncate_args_enabled" @change="setThresholdType(draft.truncate_args_keep, $event)">
            <option v-for="type in thresholdTypes" :key="type" :value="type">{{ t(`editors.summarization.thresholdTypes.${type}`) }}</option>
          </select>
        </FormField>
      </div>
      <div class="col-lg-3">
        <FormField field-path="truncate_args_keep.value">
          <input v-model.number="draft.truncate_args_keep.value" class="form-control" :disabled="!draft.truncate_args_enabled || draft.truncate_args_keep.type === 'auto'" :max="draft.truncate_args_keep.type === 'fraction' ? 1 : undefined" :min="draft.truncate_args_keep.type === 'fraction' ? 0.01 : 1" :step="draft.truncate_args_keep.type === 'fraction' ? 0.01 : 1" type="number">
        </FormField>
      </div>
      <div class="col-lg-6">
        <FormField field-path="truncate_args_max_length">
          <input v-model.number="draft.truncate_args_max_length" class="form-control" :disabled="!draft.truncate_args_enabled" min="1" step="1" type="number">
        </FormField>
      </div>
      <div class="col-lg-6">
        <FormField field-path="trim_tokens_to_summarize">
          <input v-model.number="draft.trim_tokens_to_summarize" class="form-control" min="1" step="1" type="number">
        </FormField>
      </div>
    </div>
    <FormField :hint="t('editors.summarization.truncateArgsTextHint')" field-path="truncate_args_text">
      <LteTextarea v-model="draft.truncate_args_text" :rows="3" />
    </FormField>
    <div class="d-flex justify-content-end mb-3">
      <LteButton data-action="restore-summary-prompt" theme="warning" type="button" @click="draft.summary_prompt_override = defaults.summary_prompt_default">
        {{ t('editors.common.restoreDefault') }}
      </LteButton>
    </div>
    <FormField :hint="t('editors.summarization.summaryPromptHint')" field-path="summary_prompt_override">
      <LteTextarea v-model="draft.summary_prompt_override" :rows="14" />
    </FormField>
  </div>
</template>
