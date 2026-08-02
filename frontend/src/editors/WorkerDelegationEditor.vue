<script setup lang="ts">
import { LteTextarea } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import FormField from '@/components/FormField.vue'
import type { WorkerDelegationDefaults, WorkerDelegationDraft } from '@/domain/blocks'

import { useEditorModel } from './shared/useEditorModel'

const props = defineProps<{
  modelValue: WorkerDelegationDraft
  defaults: WorkerDelegationDefaults
}>()
const emit = defineEmits<{ 'update:modelValue': [value: WorkerDelegationDraft] }>()
const { t } = useI18n()
const draft = useEditorModel(() => props.modelValue, (value) => emit('update:modelValue', value))
</script>

<template>
  <div data-editor="worker-delegation">
    <section class="card mb-3">
      <header class="card-header">
        <h3 class="card-title">{{ t('editors.workerDelegation.toolTitle') }}</h3>
        <p class="small text-body-secondary mb-0">{{ t('editors.workerDelegation.toolHint') }}</p>
      </header>
      <div class="card-body">
        <FormField field-path="tool_description">
          <LteTextarea v-model="draft.tool_description" :rows="5" />
        </FormField>
        <FormField field-path="worker_parameter_description">
          <LteTextarea v-model="draft.worker_parameter_description" :rows="4" />
        </FormField>
        <FormField field-path="task_parameter_description">
          <LteTextarea v-model="draft.task_parameter_description" :rows="4" />
        </FormField>
      </div>
    </section>

    <section class="card mb-3">
      <header class="card-header">
        <h3 class="card-title">{{ t('editors.workerDelegation.limitsTitle') }}</h3>
      </header>
      <div class="card-body">
        <div class="row g-3">
          <div class="col-md-6">
            <FormField field-path="max_worker_calls_per_request" :hint="t('editors.workerDelegation.callLimitHint')">
              <input v-model.number="draft.max_worker_calls_per_request" class="form-control" min="1" max="64" step="1" type="number">
            </FormField>
          </div>
          <div class="col-md-6">
            <FormField field-path="max_parallel_workers" :hint="t('editors.workerDelegation.parallelLimitHint')">
              <input v-model.number="draft.max_parallel_workers" class="form-control" min="1" max="16" step="1" type="number">
            </FormField>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
