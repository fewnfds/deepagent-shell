<script setup lang="ts">
import { useValidationIssuePresentation } from '@/composables/useValidationIssuePresentation'
import type { WorkflowCanvasProblem } from '@/domain/workflowCanvasProblems'

defineProps<{
  expanded: boolean
  problems: WorkflowCanvasProblem[]
}>()

const emit = defineEmits<{
  selectProblem: [problem: WorkflowCanvasProblem]
  toggle: []
}>()

const issuePresentation = useValidationIssuePresentation()

function problemKey(problem: WorkflowCanvasProblem, index: number): string {
  return `${problem.source}:${problem.code}:${problem.owner_id}:${problem.path}:${index}`
}
</script>

<template>
  <section class="workflow-problems" aria-live="polite">
    <button
      class="workflow-problems-toggle"
      :aria-expanded="expanded"
      type="button"
      @click="emit('toggle')"
    >
      <i
        v-if="problems.length > 0"
        class="bi bi-exclamation-triangle text-danger"
        aria-hidden="true"
      />
      <i v-else class="bi bi-check-circle text-success" aria-hidden="true" />
      <span class="workflow-problems-title">{{ $t('workflows.editor.canvasProblems.title') }}</span>
      <span v-if="problems.length > 0" class="badge text-bg-danger">{{ problems.length }}</span>
      <span v-else class="badge text-bg-secondary">0</span>
      <i v-if="expanded" class="bi bi-arrow-down" aria-hidden="true" />
      <i v-else class="bi bi-arrow-up" aria-hidden="true" />
    </button>

    <div v-if="expanded" class="workflow-problems-body">
      <p v-if="problems.length === 0" class="workflow-problems-empty">
        {{ $t('workflows.editor.canvasProblems.none') }}
      </p>
      <div v-else class="workflow-problems-list">
        <button
          v-for="(problem, index) in problems"
          :key="problemKey(problem, index)"
          class="workflow-problems-item"
          type="button"
          @click="emit('selectProblem', problem)"
        >
          <span class="workflow-problems-message">{{ issuePresentation.message(problem) }}</span>
          <span v-if="problem.owner_id" class="workflow-problems-owner">{{ problem.owner_id }}</span>
        </button>
      </div>
    </div>
  </section>
</template>
