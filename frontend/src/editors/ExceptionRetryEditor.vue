<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import FormField from '@/components/FormField.vue'
import type {
  ExceptionRetryCondition,
  ExceptionRetryDefaults,
  ExceptionRetryDraft,
} from '@/domain/blocks'

import { useEditorModel } from './shared/useEditorModel'

const props = defineProps<{
  modelValue: ExceptionRetryDraft
  defaults: ExceptionRetryDefaults
}>()
const emit = defineEmits<{ 'update:modelValue': [value: ExceptionRetryDraft] }>()
const { t } = useI18n()
const draft = useEditorModel(() => props.modelValue, (value) => emit('update:modelValue', value))

function conditionEnabled(condition: ExceptionRetryCondition): boolean {
  return draft.retry_on.includes(condition)
}

function setCondition(condition: ExceptionRetryCondition, enabled: boolean): void {
  draft.retry_on = enabled
    ? [...new Set([...draft.retry_on, condition])]
    : draft.retry_on.filter((item) => item !== condition)
}

function onConditionChange(condition: ExceptionRetryCondition, event: Event): void {
  setCondition(condition, (event.target as HTMLInputElement).checked)
}
</script>

<template>
  <div data-editor="exception-retry">
    <section class="card mb-3" data-testid="retry-owner">
      <header class="card-header">
        <h3 class="card-title">{{ t('editors.exceptionRetry.strategyTitle') }}</h3>
        <p class="small text-body-secondary mb-0">{{ t('editors.exceptionRetry.strategyHint') }}</p>
      </header>
      <div class="card-body">
        <fieldset>
          <legend class="visually-hidden">{{ t('editors.exceptionRetry.strategyTitle') }}</legend>
          <div v-for="strategy in defaults.strategies" :key="strategy" class="form-check mb-3">
            <input
              :id="`retry-strategy-${strategy}`"
              v-model="draft.strategy"
              class="form-check-input"
              name="exception-retry-strategy"
              type="radio"
              :value="strategy"
            >
            <label class="form-check-label" :for="`retry-strategy-${strategy}`">
              {{ t(`editors.exceptionRetry.strategies.${strategy}.label`) }}
            </label>
            <div class="form-text">{{ t(`editors.exceptionRetry.strategies.${strategy}.hint`) }}</div>
          </div>
        </fieldset>

        <div class="form-check form-switch mb-3">
          <input
            id="force_non_streaming"
            v-model="draft.force_non_streaming"
            class="form-check-input"
            type="checkbox"
          >
          <label class="form-check-label" for="force_non_streaming">
            {{ t('editors.exceptionRetry.forceNonStreamingLabel') }}
          </label>
          <div class="form-text">{{ t('editors.exceptionRetry.forceNonStreamingHint') }}</div>
        </div>

        <FormField field-path="max_retries" :hint="t('editors.exceptionRetry.maxRetriesHint')">
          <input v-model.number="draft.max_retries" class="form-control" min="0" max="10" step="1" type="number">
        </FormField>
      </div>
    </section>

    <section
      v-if="draft.strategy === 'model_retry_middleware'"
      class="card mb-3"
      data-testid="middleware-policy"
    >
      <header class="card-header">
        <h3 class="card-title">{{ t('editors.exceptionRetry.conditionsTitle') }}</h3>
        <p class="small text-body-secondary mb-0">{{ t('editors.exceptionRetry.conditionsHint') }}</p>
      </header>
      <div class="card-body">
        <fieldset>
          <legend class="visually-hidden">{{ t('editors.exceptionRetry.conditionsTitle') }}</legend>
          <div v-for="condition in defaults.conditions" :key="condition" class="form-check mb-3">
            <input
              :id="`retry-${condition}`"
              class="form-check-input"
              type="checkbox"
              :checked="conditionEnabled(condition)"
              @change="onConditionChange(condition, $event)"
            >
            <label class="form-check-label" :for="`retry-${condition}`">
              {{ t(`editors.exceptionRetry.conditions.${condition}.label`) }}
            </label>
            <div class="form-text">{{ t(`editors.exceptionRetry.conditions.${condition}.hint`) }}</div>
          </div>
        </fieldset>
      </div>
    </section>
  </div>
</template>
