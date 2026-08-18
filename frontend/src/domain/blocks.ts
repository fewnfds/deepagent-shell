import { customMiddlewareAdapter } from './blocks/customMiddleware'
import { customToolAdapter } from './blocks/customTool'
import { exceptionRetryAdapter } from './blocks/exceptionRetry'
import { filesystemAdapter } from './blocks/filesystem'
import { filesystemPermissionsAdapter } from './blocks/filesystemPermissions'
import { modelAdapter } from './blocks/model'
import { outputModeAdapter } from './blocks/outputMode'
import { promptCachingAdapter } from './blocks/promptCaching'
import { skillAdapter } from './blocks/skill'
import { subagentAdapter } from './blocks/subagent'
import { summarizationAdapter } from './blocks/summarization'
import { systemPromptAdapter } from './blocks/systemPrompt'
import { todoListAdapter } from './blocks/todoList'
import { workflowEventOutputAdapter } from './blocks/workflowEventOutput'
import { conditionRouterAdapter } from './blocks/conditionRouter'
import { taskDispatcherAdapter } from './blocks/taskDispatcher'

export type {
  CustomMiddlewareCatalogItem,
  CustomMiddlewareDraft,
} from './blocks/customMiddleware'
export type {
  CustomToolCatalogItem,
  CustomToolDraft,
} from './blocks/customTool'
export type {
  ExceptionRetryCondition,
  ExceptionRetryDefaults,
  ExceptionRetryDraft,
} from './blocks/exceptionRetry'
export type {
  FilesystemDefaults,
  FilesystemDraft,
  FilesystemImportSource,
  FilesystemToolDefault,
  MappedDirectory,
  VirtualSource,
} from './blocks/filesystem'
export type {
  FilesystemPermissionEntryDraft,
  FilesystemPermissionsDefaults,
  FilesystemPermissionsDraft,
  FilesystemPermissionValue,
} from './blocks/filesystemPermissions'
export type {
  ModelApiRecord,
  ModelDraft,
  ModelProviderSettingInput,
} from './blocks/model'
export type { OutputModeDefaults, OutputModeDraft } from './blocks/outputMode'
export type {
  PromptCachingDefaults,
  PromptCachingDraft,
} from './blocks/promptCaching'
export type { BlockDraftBase } from './blocks/shared'
export type { SkillCatalogItem, SkillDefaults, SkillDraft } from './blocks/skill'
export type { SubagentDefaults, SubagentDraft } from './blocks/subagent'
export type {
  SummarizationDefaults,
  SummarizationDraft,
  SummarizationThresholdDraft,
  SummarizationThresholdType,
} from './blocks/summarization'
export type { SystemPromptDraft } from './blocks/systemPrompt'
export type { TodoListDefaults, TodoListDraft } from './blocks/todoList'
export type { WorkflowEventOutputDefaults, WorkflowEventOutputDraft } from './blocks/workflowEventOutput'
export type {
  ConditionRouterCatalogItem,
  ConditionRouterDefaults,
  ConditionRouterDraft,
} from './blocks/conditionRouter'
export type {
  TaskDispatcherCatalogItem,
  TaskDispatcherDefaults,
  TaskDispatcherDraft,
} from './blocks/taskDispatcher'

export {
  customMiddlewareAdapter,
  customToolAdapter,
  exceptionRetryAdapter,
  filesystemAdapter,
  filesystemPermissionsAdapter,
  modelAdapter,
  outputModeAdapter,
  promptCachingAdapter,
  skillAdapter,
  subagentAdapter,
  summarizationAdapter,
  systemPromptAdapter,
  todoListAdapter,
  workflowEventOutputAdapter,
  conditionRouterAdapter,
  taskDispatcherAdapter,
}

export const blockTypes = [
  'model',
  'custom-tool',
  'custom-middleware',
  'output-mode',
  'exception-retry',
  'filesystem',
  'filesystem-permissions',
  'skill',
  'system-prompt',
  'subagent',
  'todo-list',
  'summarization',
  'prompt-caching',
] as const

export const managedComponentTypes = [
  ...blockTypes,
  'workflow-event-output',
  'condition-router',
  'task-dispatcher',
] as const

export const blockAdapters = {
  model: modelAdapter,
  'custom-tool': customToolAdapter,
  'custom-middleware': customMiddlewareAdapter,
  'output-mode': outputModeAdapter,
  'exception-retry': exceptionRetryAdapter,
  filesystem: filesystemAdapter,
  'filesystem-permissions': filesystemPermissionsAdapter,
  skill: skillAdapter,
  'system-prompt': systemPromptAdapter,
  subagent: subagentAdapter,
  'todo-list': todoListAdapter,
  summarization: summarizationAdapter,
  'prompt-caching': promptCachingAdapter,
  'workflow-event-output': workflowEventOutputAdapter,
  'condition-router': conditionRouterAdapter,
  'task-dispatcher': taskDispatcherAdapter,
} as const
