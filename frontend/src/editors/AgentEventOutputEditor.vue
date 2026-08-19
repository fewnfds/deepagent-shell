<script setup lang="ts">
import type { LocalizedMessagePayload } from '@/api'
import PythonPackageEditor from '@/components/PythonPackageEditor.vue'
import {
  type AgentEventOutputCatalogItem,
  type AgentEventOutputDraft,
} from '@/domain/blocks'
import type { PythonPackageDraftState } from '@/domain/blocks/pythonPackage'
import { useEditorModel } from './shared/useEditorModel'

const props = withDefaults(defineProps<{
  modelValue: AgentEventOutputDraft
  catalog?: AgentEventOutputCatalogItem[]
  errors?: Record<string, LocalizedMessagePayload>
  loading?: boolean
}>(), {
  catalog: () => [],
  errors: () => ({}),
  loading: false,
})
const emit = defineEmits<{
  'update:modelValue': [value: AgentEventOutputDraft]
  'load-files': [paths: string[]]
  refresh: []
}>()
const draft = useEditorModel(() => props.modelValue, (value) => emit('update:modelValue', value))

function updatePackage(value: PythonPackageDraftState): void {
  draft.python_package = value.python_package
  draft.python_package_files = value.python_package_files
  draft.python_package_manifest = value.python_package_manifest
  draft.python_package_error = value.python_package_error
  draft.dependency_status = value.dependency_status
  draft.editable_paths_source = value.editable_paths_source
}
</script>

<template>
  <div data-editor="agent-event-output">
    <PythonPackageEditor
      :catalog="catalog"
      :errors="errors"
      id-prefix="agent-event-output"
      :loading="loading"
      :model-value="draft"
      :saved="Boolean(draft.id)"
      @load-files="emit('load-files', $event)"
      @refresh="emit('refresh')"
      @update:model-value="updatePackage"
    />
  </div>
</template>
