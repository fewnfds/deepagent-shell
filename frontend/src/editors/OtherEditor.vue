<script setup lang="ts">
import { LteButton, LteTextarea } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import FormField from '@/components/FormField.vue'
import type {
  OtherDefaults,
  OtherDraft,
  SummarizationThresholdDraft,
  SummarizationThresholdType,
} from '@/domain/blocks'
import { useEditorModel } from './shared/useEditorModel'

const props = defineProps<{
  modelValue: OtherDraft
  defaults: OtherDefaults
}>()
const emit = defineEmits<{ 'update:modelValue': [value: OtherDraft] }>()
const { t } = useI18n()
const draft = useEditorModel(() => props.modelValue, (value) => emit('update:modelValue', value))
const thresholdTypes: SummarizationThresholdType[] = ['auto', 'fraction', 'tokens', 'messages']

function thresholdLabel(type: SummarizationThresholdType): string {
  return t(`editors.other.thresholdTypes.${type}`)
}

function thresholdDefaultValue(type: SummarizationThresholdType): number | null {
  if (type === 'auto') return null
  if (type === 'fraction') return 0.85
  if (type === 'messages') return 20
  // Token thresholds depend on the model/context and must be entered explicitly.
  return null
}

function setThresholdType(threshold: SummarizationThresholdDraft, event: Event): void {
  const type = (event.target as HTMLSelectElement).value as SummarizationThresholdType
  if (threshold.type === type) return
  threshold.type = type
  threshold.value = thresholdDefaultValue(type)
}

function restoreSummaryPrompt(): void {
  draft.summarization.summary_prompt_override = props.defaults.summary_prompt_default
}
</script>

<template>
  <div data-editor="other">
    <section class="card mb-3">
      <header class="card-header">
        <div class="d-flex align-items-center justify-content-between gap-2">
          <div>
            <h3 class="h5 fw-semibold mb-1">{{ t('editors.other.summarizationTitle') }}</h3>
            <p class="small text-body-secondary mb-0">{{ t('editors.other.summarizationHint') }}</p>
          </div>
          <div class="form-check form-switch">
            <input id="other-summarization-enabled" v-model="draft.summarization.enabled" class="form-check-input" type="checkbox">
            <label class="form-check-label" for="other-summarization-enabled">{{ draft.summarization.enabled ? t('common.enabled') : t('common.disabled') }}</label>
          </div>
        </div>
      </header>
      <div class="card-body">
        <div class="row g-3">
          <div class="col-lg-3">
            <FormField field-path="summarization.trigger.type">
              <select :value="draft.summarization.trigger.type" class="form-select" @change="setThresholdType(draft.summarization.trigger, $event)">
                <option v-for="type in thresholdTypes" :key="type" :value="type">{{ thresholdLabel(type) }}</option>
              </select>
            </FormField>
          </div>
          <div class="col-lg-3">
            <FormField field-path="summarization.trigger.value">
              <input v-model.number="draft.summarization.trigger.value" class="form-control" :disabled="draft.summarization.trigger.type === 'auto'" :max="draft.summarization.trigger.type === 'fraction' ? 1 : undefined" :min="draft.summarization.trigger.type === 'fraction' ? 0.01 : 1" :step="draft.summarization.trigger.type === 'fraction' ? 0.01 : 1" type="number">
            </FormField>
          </div>
          <div class="col-lg-3">
            <FormField field-path="summarization.keep.type">
              <select :value="draft.summarization.keep.type" class="form-select" @change="setThresholdType(draft.summarization.keep, $event)">
                <option v-for="type in thresholdTypes" :key="type" :value="type">{{ thresholdLabel(type) }}</option>
              </select>
            </FormField>
          </div>
          <div class="col-lg-3">
            <FormField field-path="summarization.keep.value">
              <input v-model.number="draft.summarization.keep.value" class="form-control" :disabled="draft.summarization.keep.type === 'auto'" :max="draft.summarization.keep.type === 'fraction' ? 1 : undefined" :min="draft.summarization.keep.type === 'fraction' ? 0.01 : 1" :step="draft.summarization.keep.type === 'fraction' ? 0.01 : 1" type="number">
            </FormField>
          </div>
        </div>

        <div class="form-check form-switch mb-3">
          <input id="other-truncate-args-enabled" v-model="draft.summarization.truncate_args_enabled" class="form-check-input" type="checkbox">
          <label class="form-check-label" for="other-truncate-args-enabled">{{ t('editors.other.truncateArgsEnabled') }}</label>
        </div>
        <div class="row g-3">
          <div class="col-lg-3">
            <FormField field-path="summarization.truncate_args_trigger.type">
              <select :value="draft.summarization.truncate_args_trigger.type" class="form-select" :disabled="!draft.summarization.truncate_args_enabled" @change="setThresholdType(draft.summarization.truncate_args_trigger, $event)">
                <option v-for="type in thresholdTypes" :key="type" :value="type">{{ thresholdLabel(type) }}</option>
              </select>
            </FormField>
          </div>
          <div class="col-lg-3">
            <FormField field-path="summarization.truncate_args_trigger.value">
              <input v-model.number="draft.summarization.truncate_args_trigger.value" class="form-control" :disabled="!draft.summarization.truncate_args_enabled || draft.summarization.truncate_args_trigger.type === 'auto'" :max="draft.summarization.truncate_args_trigger.type === 'fraction' ? 1 : undefined" :min="draft.summarization.truncate_args_trigger.type === 'fraction' ? 0.01 : 1" :step="draft.summarization.truncate_args_trigger.type === 'fraction' ? 0.01 : 1" type="number">
            </FormField>
          </div>
          <div class="col-lg-3">
            <FormField field-path="summarization.truncate_args_keep.type">
              <select :value="draft.summarization.truncate_args_keep.type" class="form-select" :disabled="!draft.summarization.truncate_args_enabled" @change="setThresholdType(draft.summarization.truncate_args_keep, $event)">
                <option v-for="type in thresholdTypes" :key="type" :value="type">{{ thresholdLabel(type) }}</option>
              </select>
            </FormField>
          </div>
          <div class="col-lg-3">
            <FormField field-path="summarization.truncate_args_keep.value">
              <input v-model.number="draft.summarization.truncate_args_keep.value" class="form-control" :disabled="!draft.summarization.truncate_args_enabled || draft.summarization.truncate_args_keep.type === 'auto'" :max="draft.summarization.truncate_args_keep.type === 'fraction' ? 1 : undefined" :min="draft.summarization.truncate_args_keep.type === 'fraction' ? 0.01 : 1" :step="draft.summarization.truncate_args_keep.type === 'fraction' ? 0.01 : 1" type="number">
            </FormField>
          </div>
          <div class="col-lg-6">
            <FormField field-path="summarization.truncate_args_max_length">
              <input v-model.number="draft.summarization.truncate_args_max_length" class="form-control" :disabled="!draft.summarization.truncate_args_enabled" min="1" step="1" type="number">
            </FormField>
          </div>
          <div class="col-lg-6">
            <FormField field-path="summarization.trim_tokens_to_summarize">
              <input v-model.number="draft.summarization.trim_tokens_to_summarize" class="form-control" min="1" step="1" type="number">
            </FormField>
          </div>
        </div>
        <FormField
          :hint="t('editors.other.truncateArgsTextHint')"
          field-path="summarization.truncate_args_text"
        >
          <LteTextarea v-model="draft.summarization.truncate_args_text" :rows="3" />
        </FormField>
        <div class="d-flex justify-content-end mb-3">
          <LteButton
            data-action="restore-summary-prompt"
            theme="warning"
            type="button"
            @click="restoreSummaryPrompt"
          >
            {{ t('editors.common.restoreDefault') }}
          </LteButton>
        </div>
        <FormField
          :hint="t('editors.other.summaryPromptHint')"
          field-path="summarization.summary_prompt_override"
        >
          <LteTextarea v-model="draft.summarization.summary_prompt_override" :rows="14" />
        </FormField>
      </div>
    </section>

    <section class="card mb-3">
      <header class="card-header">
        <div class="d-flex align-items-center justify-content-between gap-2">
          <div>
            <h3 class="h5 fw-semibold mb-1">{{ t('editors.other.promptCachingTitle') }}</h3>
            <p class="small text-body-secondary mb-0">{{ t('editors.other.promptCachingHint') }}</p>
          </div>
          <div class="form-check form-switch">
            <input id="other-prompt-caching-enabled" v-model="draft.prompt_caching.enabled" class="form-check-input" type="checkbox">
            <label class="form-check-label" for="other-prompt-caching-enabled">{{ draft.prompt_caching.enabled ? t('common.enabled') : t('common.disabled') }}</label>
          </div>
        </div>
      </header>
      <div class="card-body">
        <div class="row g-3">
          <div class="col-lg-4">
            <FormField field-path="prompt_caching.type">
              <select v-model="draft.prompt_caching.type" class="form-select" disabled><option value="ephemeral">{{ t('editors.other.cacheTypes.ephemeral') }}</option></select>
            </FormField>
          </div>
          <div class="col-lg-4">
            <FormField field-path="prompt_caching.ttl">
              <select v-model="draft.prompt_caching.ttl" class="form-select">
                <option value="5m">5m</option>
                <option value="1h">1h</option>
              </select>
            </FormField>
          </div>
          <div class="col-lg-4">
            <FormField field-path="prompt_caching.min_messages_to_cache">
              <input v-model.number="draft.prompt_caching.min_messages_to_cache" class="form-control" min="0" step="1" type="number">
            </FormField>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
