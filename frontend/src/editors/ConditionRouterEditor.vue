<script setup lang="ts">
import { LteButton, LteTextarea } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import FormField from '@/components/FormField.vue'
import {
  newConditionRouterBranch,
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

function removeBranch(index: number): void {
  if (draft.branches[index]?.key === 'otherwise') return
  draft.branches.splice(index, 1)
}

function addBranch(): void {
  const otherwiseIndex = draft.branches.findIndex((branch) => branch.key === 'otherwise')
  draft.branches.splice(otherwiseIndex < 0 ? draft.branches.length : otherwiseIndex, 0, newConditionRouterBranch())
}

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
        <h3 class="card-title h5 mb-0">{{ t('editors.conditionRouter.branchesTitle') }}</h3>
      </header>
      <div class="card-body">
        <p class="form-text">{{ t('editors.conditionRouter.branchesHint') }}</p>
        <div class="list-group list-group-flush">
          <div v-for="(branch, index) in draft.branches" :key="branch._key" class="list-group-item">
            <div class="simple-mapping-row">
              <div class="simple-mapping-primary">
                <FormField field-path="branches[].key">
                  <input
                    v-model="branch.key"
                    :disabled="branch.key === 'otherwise'"
                    class="form-control"
                    type="text"
                  >
                </FormField>
              </div>
              <div class="simple-mapping-secondary">
                <FormField field-path="branches[].label">
                  <input v-model="branch.label" class="form-control" type="text">
                </FormField>
              </div>
              <div class="simple-mapping-actions">
                <LteButton
                  :aria-label="t('editors.conditionRouter.removeBranch')"
                  :disabled="branch.key === 'otherwise'"
                  size="sm"
                  theme="danger"
                  type="button"
                  @click="removeBranch(index)"
                >
                  <i class="bi bi-trash" aria-hidden="true" />
                </LteButton>
              </div>
            </div>
          </div>
        </div>
        <div class="simple-mapping-footer">
          <LteButton
            :aria-label="t('editors.conditionRouter.addBranch')"
            :title="t('editors.conditionRouter.addBranch')"
            size="sm"
            theme="success"
            type="button"
            @click="addBranch"
          >
            <i class="bi bi-plus-lg" aria-hidden="true" />
          </LteButton>
        </div>
      </div>
    </section>

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
