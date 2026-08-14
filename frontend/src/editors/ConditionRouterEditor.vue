<script setup lang="ts">
import { LteTextarea } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import FormField from '@/components/FormField.vue'
import {
  type ConditionRouterDefaults,
  type ConditionRouterDraft,
} from '@/domain/blocks'
import { useEditorModel } from './shared/useEditorModel'

const props = defineProps<{
  modelValue: ConditionRouterDraft
  defaults?: ConditionRouterDefaults
}>()
const emit = defineEmits<{ 'update:modelValue': [value: ConditionRouterDraft] }>()
const { t } = useI18n()
const draft = useEditorModel(() => props.modelValue, (value) => emit('update:modelValue', value))

function setRequirements(value: string): void {
  draft.python_requirements = value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
}
</script>

<template>
  <div data-editor="condition-router">
    <p v-if="draft.dependency_status !== 'ready'" class="form-text">
      {{ t(`editors.scriptRequirements.status.${draft.dependency_status}`) }}
    </p>

    <section class="card mb-3">
      <header class="card-header">
        <h3 class="card-title h5 mb-0">{{ t('editors.conditionRouter.scriptTitle') }}</h3>
      </header>
      <div class="card-body">
        <FormField field-path="route_source" :hint="t('editors.conditionRouter.scriptHint')">
          <LteTextarea v-model="draft.route_source" :rows="16" />
        </FormField>
        <FormField field-path="python_requirements" :hint="t('editors.scriptRequirements.hint')">
          <LteTextarea :model-value="draft.python_requirements.join('\n')" :rows="4" @update:model-value="setRequirements($event)" />
        </FormField>
      </div>
    </section>
  </div>
</template>
