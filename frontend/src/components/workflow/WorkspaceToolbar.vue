<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  name: string
  isNew: boolean
  dirty: boolean
  saving: boolean
  validating: boolean
  valid: boolean | null
  runActive: boolean
  canUndo: boolean
  canRedo: boolean
}>()
const { t } = useI18n()
const emit = defineEmits<{
  back: []
  save: []
  validate: []
  run: []
  newWorkflow: []
  undo: []
  redo: []
}>()
const statusLabel = computed(() => {
  if (props.saving) return '保存中'
  if (props.validating) return '校验中'
  if (props.valid === false) return '校验失败'
  if (props.dirty) return '未保存'
  return '已保存'
})
</script>

<template>
  <header class="workspace-toolbar">
    <div class="workspace-toolbar__leading">
      <button class="btn btn-sm btn-outline-secondary" type="button" aria-label="返回 Workflow 列表" @click="emit('back')">
        <i class="bi bi-chevron-left" aria-hidden="true" />
        <span>Workflows</span>
      </button>
      <span class="workspace-toolbar__divider" aria-hidden="true" />
      <div class="workspace-toolbar__identity">
        <span class="workspace-toolbar__eyebrow">GRAPH WORKSPACE</span>
        <input :value="name" class="workspace-toolbar__name" type="text" aria-label="Workflow 名称" readonly>
      </div>
      <span class="workspace-toolbar__status" :data-dirty="dirty || undefined">{{ statusLabel }}</span>
    </div>
    <div class="workspace-toolbar__actions">
      <button class="btn btn-sm btn-outline-secondary" type="button" @click="emit('newWorkflow')">
        <i class="bi bi-plus-lg" aria-hidden="true" /> 新建
      </button>
      <button class="btn btn-sm btn-outline-secondary" type="button" :disabled="!canUndo" aria-label="撤销" title="撤销" @click="emit('undo')"><i class="bi bi-arrow-counterclockwise" aria-hidden="true" /></button>
      <button class="btn btn-sm btn-outline-secondary" type="button" :disabled="!canRedo" aria-label="重做" title="重做" @click="emit('redo')"><i class="bi bi-arrow-clockwise" aria-hidden="true" /></button>
      <button class="btn btn-sm btn-outline-secondary" type="button" :disabled="validating" @click="emit('validate')">
        <i class="bi bi-check-circle" aria-hidden="true" /> 校验
      </button>
      <button class="btn btn-sm btn-primary" type="button" :disabled="saving" @click="emit('save')">
        <i class="bi bi-download" aria-hidden="true" /> 保存
      </button>
      <button class="btn btn-sm btn-success" type="button" :disabled="runActive || isNew || dirty" :title="dirty ? t('workflow.runSaveRequired') : undefined" @click="emit('run')">
        <i class="bi bi-play-fill" aria-hidden="true" /> 运行
      </button>
    </div>
  </header>
</template>
