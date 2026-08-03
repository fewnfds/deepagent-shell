<script setup lang="ts">
import { LteButton } from '@adminlte/vue'
import { useI18n } from 'vue-i18n'

import FormField from '@/components/FormField.vue'
import type { AutomationScriptResource } from '@/api'
import { blankAutomationNode, type AutomationNodeDraft } from '@/domain/automation'

const props = defineProps<{
  fieldPrefix: string
  modelValue: AutomationNodeDraft[]
  scripts: AutomationScriptResource[]
  title: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: AutomationNodeDraft[]]
}>()

const { t } = useI18n()

function update(nodes: AutomationNodeDraft[]): void {
  emit('update:modelValue', nodes)
}

function add(): void {
  update([...props.modelValue, blankAutomationNode()])
}

function remove(index: number): void {
  update(props.modelValue.filter((_node, nodeIndex) => nodeIndex !== index))
}

function move(index: number, offset: number): void {
  const target = index + offset
  if (target < 0 || target >= props.modelValue.length) return
  const nodes = [...props.modelValue]
  const [node] = nodes.splice(index, 1)
  if (!node) return
  nodes.splice(target, 0, node)
  update(nodes)
}

function patch(index: number, values: Partial<AutomationNodeDraft>): void {
  update(props.modelValue.map((node, nodeIndex) => (
    nodeIndex === index ? { ...node, ...values } : node
  )))
}
</script>

<template>
  <section class="card mb-3">
    <header class="card-header d-flex align-items-center justify-content-between gap-2">
      <h2 class="card-title h5 mb-0 fw-semibold">{{ title }}</h2>
      <LteButton
        :aria-label="t('automation.nodes.add')"
        :title="t('automation.nodes.add')"
        size="sm"
        theme="success"
        type="button"
        @click="add"
      >
        <i class="bi bi-plus-lg" aria-hidden="true" />
      </LteButton>
    </header>
    <ul v-if="modelValue.length" class="list-group list-group-flush">
      <li v-for="(node, index) in modelValue" :key="node.key" class="list-group-item">
        <div class="row g-3 align-items-start">
          <div class="col-lg-4">
            <FormField :field-path="`${fieldPrefix}.${index}.script_id`" label-key="automation.nodes.script">
              <select
                class="form-select"
                :value="node.script_id"
                @change="patch(index, { script_id: ($event.target as HTMLSelectElement).value })"
              >
                <option disabled value="">{{ t('common.chooseConfiguration') }}</option>
                <option v-for="script in scripts" :key="script.id" :value="script.id">
                  {{ script.name }}
                </option>
              </select>
            </FormField>
          </div>
          <div class="col-lg-8">
            <FormField :field-path="`${fieldPrefix}.${index}.config`" label-key="automation.nodes.config">
              <textarea
                class="form-control font-monospace"
                rows="4"
                :value="node.config_text"
                @input="patch(index, { config_text: ($event.target as HTMLTextAreaElement).value })"
              />
            </FormField>
          </div>
          <div class="col-12 d-flex justify-content-end gap-1">
            <LteButton
              :aria-label="t('automation.nodes.moveUp')"
              :disabled="index === 0"
              :title="t('automation.nodes.moveUp')"
              size="sm"
              theme="secondary"
              type="button"
              @click="move(index, -1)"
            >
              <i class="bi bi-arrow-up" aria-hidden="true" />
            </LteButton>
            <LteButton
              :aria-label="t('automation.nodes.moveDown')"
              :disabled="index === modelValue.length - 1"
              :title="t('automation.nodes.moveDown')"
              size="sm"
              theme="secondary"
              type="button"
              @click="move(index, 1)"
            >
              <i class="bi bi-arrow-down" aria-hidden="true" />
            </LteButton>
            <LteButton
              :aria-label="t('common.delete')"
              :title="t('common.delete')"
              size="sm"
              theme="danger"
              type="button"
              @click="remove(index)"
            >
              <i class="bi bi-trash" aria-hidden="true" />
            </LteButton>
          </div>
        </div>
      </li>
    </ul>
    <div v-else class="card-body text-body-secondary">
      {{ t('automation.nodes.empty') }}
    </div>
  </section>
</template>
