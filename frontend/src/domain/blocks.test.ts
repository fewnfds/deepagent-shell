import { describe, expect, it } from 'vitest'

import {
  blockAdapters,
  blockTypes,
  managedComponentTypes,
  customMiddlewareAdapter,
  customToolAdapter,
  filesystemAdapter,
  modelAdapter,
  outputModeAdapter,
  skillAdapter,
  subagentAdapter,
  systemPromptAdapter,
  todoListAdapter,
  type FilesystemDefaults,
  type ModelApiRecord,
  type OutputModeDefaults,
  type SkillDefaults,
  type SubagentDefaults,
  type TodoListDefaults,
} from './blocks'

const filesystemDefaults: FilesystemDefaults = {
  system_prompt: 'filesystem default',
  tool_token_limit_before_evict: 20_000,
  tools: [
    { name: 'read_file', configurable: false, visible: true, default_description: 'read default' },
    { name: 'delete', configurable: true, visible: false, default_description: 'delete default' },
    { name: 'execute', configurable: false, visible: false, default_description: 'execute default' },
  ],
}

const outputDefaults: OutputModeDefaults = {
  events: [{ key: 'assistant_text', fields: ['message'] }],
  filter_fields: ['message'],
  default_value: {
    filter_mode: 'blocklist',
    filter_mappings: [],
    event_outputs: {
      assistant_text: {
        enabled: true,
        output_source: 'def output(event):\n    return event["message"]\n',
      },
    },
  },
}

const skillDefaults: SkillDefaults = { system_prompt: 'skill default' }
const subagentDefaults: SubagentDefaults = {
  system_prompt: 'subagent default',
  tool_description: 'task default',
}
const todoDefaults: TodoListDefaults = {
  system_prompt: 'todo default',
  tool_description: 'write_todos default',
}
function modelRecord(): ModelApiRecord {
  return {
    id: 'model-id', name: 'Model', provider: 'openai', base_url: 'https://example.test/v1', model: 'example-model',
    credential: { status: 'masked' }, provider_settings: { stop_sequences: ['END'] },
    tool_choice: 'auto', response_format: {
      title: 'Result', description: 'Structured result', type: 'object',
    },
    model_settings: { parallel_tool_calls: false },
  }
}

describe('block adapters', () => {
  it('registers exactly one explicit adapter for every current block type', () => {
    expect(Object.keys(blockAdapters)).toEqual(managedComponentTypes)
  })

  it('maps model credentials and nullable parameters without validating provider behavior', () => {
    const draft = modelAdapter.fromApi(modelRecord())
    expect(draft.credential_secret).toBe('')
    expect(draft.credential_status).toBe('masked')
    expect(draft.provider_settings.stop_sequences).toBe('["END"]')

    draft.name = '  Updated model  '
    draft.credential_secret = 'secret'
    draft.provider_settings.temperature = ''
    draft.provider_settings.stop_sequences = 'not-json-yet'
    const payload = modelAdapter.toPayload(draft)
    expect(payload).toMatchObject({
      name: 'Updated model', credential: 'secret', provider_settings: {
        stop_sequences: 'not-json-yet',
      },
      tool_choice: 'auto', response_format: {
        title: 'Result', description: 'Structured result', type: 'object',
      },
      model_settings: { parallel_tool_calls: false },
    })
  })

  it('keeps the configuration extension reference and file payload mechanical', () => {
    const toolDraft = customToolAdapter.blank()
    toolDraft.name = ' Tools '
    toolDraft.tools = ['one', ' one ', '', 'two']
    expect(customToolAdapter.toPayload(toolDraft)).toEqual({ name: 'Tools', tools: ['one', 'two'] })

    const middlewareDraft = customMiddlewareAdapter.fromApi({
      id: 'middleware-id',
      name: 'Middleware',
      python_package: { folder: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', editable_files: ['main.py', 'requirements.txt'] },
      python_package_files: {
        files: [
          { path: 'main.py', content: 'def create_middleware(agent):\n    return middleware\n', exists: true },
          { path: 'requirements.txt', content: 'httpx==1\n', exists: true },
        ],
        revision: 'revision',
      },
      python_package_error: {
        message_key: 'resource.error.pythonPackage.syntax',
        message_args: { line: 2 },
      },
    })
    const payload = customMiddlewareAdapter.toPayload(middlewareDraft)
    expect(payload.python_package).toEqual({
      folder: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', editable_files: ['main.py', 'requirements.txt'],
    })
    expect(payload.python_package_files).toMatchObject({
      files: [
        { path: 'main.py', content: expect.any(String) },
        { path: 'requirements.txt', content: 'httpx==1\n' },
      ],
      revision: 'revision',
    })
    expect(middlewareDraft.python_package_error).toEqual({
      message_key: 'resource.error.pythonPackage.syntax',
      message_args: { line: 2 },
    })
  })

  it('creates output drafts from an independent copy of the catalog default', () => {
    const blank = outputModeAdapter.blank(outputDefaults)
    expect(blank.event_outputs.assistant_text?.output_source)
      .toBe('def output(event):\n    return event["message"]\n')
    blank.filter_mappings.push({ field: 'message', value: 'hidden' })
    expect(outputDefaults.default_value.filter_mappings).toEqual([])
    expect(outputModeAdapter.toPayload(blank)).not.toHaveProperty('id')
  })

  it('loads only the current output event scripts before an explicit save', () => {
    const saved = {
      id: 'output-id',
      name: 'Legacy output',
      filter_mode: 'blocklist',
      filter_mappings: [],
      event_outputs: {
        assistant_text: {
          enabled: true,
          output_source: 'def output(event):\n    return "<assistant>" + event["message"] + "</assistant>"\n',
        },
        other: { enabled: true, output_source: 'def output(event):\n    return event["message"]\n' },
      },
    }
    const draft = outputModeAdapter.fromApi(saved as never, outputDefaults)

    expect(draft.event_outputs).toEqual({
      assistant_text: {
        enabled: true,
        output_source: 'def output(event):\n    return "<assistant>" + event["message"] + "</assistant>"\n',
      },
    })
    expect(outputModeAdapter.toPayload(draft).event_outputs).toEqual(
      draft.event_outputs,
    )
  })

  it('projects malformed saved components into repairable current drafts', () => {
    const model = modelAdapter.fromApi({
      ...modelRecord(),
      provider: undefined,
      provider_settings: ['invalid'],
      model_settings: ['invalid'],
      legacy_parameter: 'discarded',
    } as never)
    expect(model.provider).toBe('openai')
    expect(model.provider_settings).toEqual({})
    expect(model.model_settings).toBe('{}')
    expect(model).not.toHaveProperty('legacy_parameter')

    expect(customToolAdapter.fromApi({
      id: 'tools', name: 'Tools', tools: ['kept', 42], legacy: true,
    } as never)).toEqual({ id: 'tools', name: 'Tools', tools: ['kept'] })

    const middleware = customMiddlewareAdapter.fromApi({
      id: 'middleware', name: 'Middleware',
      python_package: {
        folder: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
        editable_files: ['main.py', 42],
      },
      python_package_files: {
        files: ['invalid'],
        revision: 7,
      },
    } as never)
    expect(middleware.python_package).toEqual({
      folder: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', editable_files: ['main.py'],
    })
    expect(middleware.python_package_files).toMatchObject({
      files: [{ path: 'main.py', content: '', exists: false }], revision: '',
    })

    const output = outputModeAdapter.fromApi({
      id: 'output', name: 'Output', filter_mode: 'legacy',
      filter_mappings: [{ field: 'message', value: 'kept' }, 'discarded'],
      event_outputs: {
        assistant_text: {
          enabled: false,
          output_source: 'def output(event):\n    return "kept " + event["message"]\n',
        },
        legacy_event: { enabled: true, output_source: 'def output(event):\n    return "discarded"\n' },
      },
    } as never, outputDefaults)
    expect(output.filter_mode).toBe(outputDefaults.default_value.filter_mode)
    expect(output.filter_mappings).toEqual([{ field: 'message', value: 'kept' }])
    expect(output.event_outputs).toEqual({
      assistant_text: {
        enabled: false,
        output_source: 'def output(event):\n    return "kept " + event["message"]\n',
      },
    })

    const filesystem = filesystemAdapter.fromApi({
      id: 'files', name: 'Files',
      mapped_directories: [{ virtual_path: '/kept/', local_path: 'H:\\kept' }, 42],
      virtual_directories: 'invalid', virtual_files: [],
      system_prompt_override: 42, tool_token_limit_before_evict: {},
      tool_configs: {
        read_file: { visible: false, description_override: 42 },
      },
    } as never, filesystemDefaults)
    expect(filesystem.mapped_directories).toEqual([
      {
        virtual_path: '/kept/',
        local_path: 'H:\\kept',
        path_origin: 'absolute',
        lifecycle_mode: 'fixed',
      },
    ])
    expect(filesystem.virtual_directories).toEqual([])
    expect(filesystem.system_prompt_override).toBe(filesystemDefaults.system_prompt)
    expect(filesystem.tool_configs.read_file).toEqual({
      visible: true, description_override: 'read default',
    })
    expect(filesystem.tool_configs.delete).toEqual({
      visible: false, description_override: 'delete default',
    })

    expect(skillAdapter.fromApi({
      id: 'skill', name: 'Skill', skills: ['kept', 42],
      system_prompt_enabled: false, instruction_override: 42,
    } as never, skillDefaults)).toMatchObject({
      skills: ['kept'], system_prompt_enabled: false, instruction_override: 'skill default',
    })
    expect(systemPromptAdapter.fromApi({
      id: 'system', name: 'System', system_prompt: 42,
    } as never).system_prompt).toBe('')
    expect(subagentAdapter.fromApi({
      id: 'subagent', name: 'Subagent', instruction_override: 42,
      task_description_override: 'kept',
    } as never, subagentDefaults)).toMatchObject({
      instruction_override: 'subagent default',
      task_description_override: 'kept',
    })
    expect(todoListAdapter.fromApi({
      id: 'todo', name: 'Todo', system_prompt_override: 42,
      tool_description_override: 'kept',
    } as never, todoDefaults)).toMatchObject({
      system_prompt_override: 'todo default', tool_description_override: 'kept',
    })
  })

  it('maps filesystem defaults and rows without enforcing path rules', () => {
    const blank = filesystemAdapter.blank(filesystemDefaults)
    expect(blank.tool_configs.read_file?.description_override).toBe('read default')
    expect(blank.tool_configs.execute?.visible).toBe(false)

    blank.name = ' Files '
    blank.mapped_directories.push(
      {
        virtual_path: '', local_path: '', path_origin: 'absolute', lifecycle_mode: 'fixed',
      },
      {
        virtual_path: ' /workspace/ ',
        local_path: ' workspaces ',
        path_origin: 'data-root-relative',
        lifecycle_mode: 'dynamic',
      },
    )
    const payload = filesystemAdapter.toPayload(blank, filesystemDefaults)
    expect(payload.mapped_directories).toEqual([
      {
        virtual_path: '/workspace/',
        local_path: 'workspaces',
        path_origin: 'data-root-relative',
        lifecycle_mode: 'dynamic',
      },
    ])
    expect(payload.system_prompt_override).toBeNull()
    blank.tool_configs.read_file.visible = false
    blank.tool_configs.execute.visible = true
    expect(payload.tool_configs.read_file?.description_override).toBeNull()
    const repairedPayload = filesystemAdapter.toPayload(blank, filesystemDefaults)
    expect(repairedPayload.tool_configs.read_file?.visible).toBe(true)
    expect(repairedPayload.tool_configs.delete?.visible).toBe(false)
    expect(repairedPayload.tool_configs.execute?.visible).toBe(false)
  })

  it('round-trips the remaining simple editors and removes displayed defaults', () => {
    const skill = skillAdapter.blank(skillDefaults)
    skill.name = ' Skill '
    skill.skills = ['alpha', 'alpha']
    expect(skillAdapter.toPayload(skill, skillDefaults)).toEqual({
      name: 'Skill', skills: ['alpha'], system_prompt_enabled: true, instruction_override: null,
    })
    skill.system_prompt_enabled = false
    skill.instruction_override = 'Custom but disabled'
    expect(skillAdapter.toPayload(skill, skillDefaults)).toEqual({
      name: 'Skill', skills: ['alpha'], system_prompt_enabled: false, instruction_override: null,
    })

    const systemPrompt = systemPromptAdapter.blank()
    systemPrompt.name = ' System '
    systemPrompt.system_prompt = ' Prompt body '
    expect(systemPromptAdapter.toPayload(systemPrompt)).toEqual({
      name: 'System', system_prompt: 'Prompt body',
    })

    const subagent = subagentAdapter.blank(subagentDefaults)
    subagent.name = ' Subagent '
    expect(subagentAdapter.toPayload(subagent, subagentDefaults)).toEqual({
      name: 'Subagent',
      instruction_override: null,
      task_description_override: null,
    })

    const todo = todoListAdapter.blank(todoDefaults)
    todo.name = ' Todos '
    expect(todoListAdapter.toPayload(todo, todoDefaults)).toEqual({
      name: 'Todos', system_prompt_override: null, tool_description_override: null,
    })

  })
})
