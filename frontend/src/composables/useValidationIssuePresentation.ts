import { useI18n } from 'vue-i18n'

import type { JsonPrimitive, ValidationIssue } from '@/api'
import { fieldLabelKeys } from '@/locales/fieldLabels'

const resolutionKeys: Record<string, string> = {
  'assembly.primary_not_found': 'primaryNotFound',
  'assembly.referenced_block_invalid': 'referencedBlockInvalid',
  'assembly.reference_not_found': 'referenceNotFound',
  'assembly.required_capability_missing': 'requiredCapabilityMissing',
  'assembly.tool_name_conflict': 'toolNameConflict',
  'assembly.subagent_override_not_found': 'subagentOverrideNotFound',
  'assembly.subagent_override_invalid': 'subagentOverrideInvalid',
  'assembly.subagent_binding_required': 'subagentBindingRequired',
  'assembly.prompt_preset_required': 'promptPresetRequired',
  'assembly.prompt_preset_scope_invalid': 'promptPresetScopeInvalid',
  'assembly.prompt_preset_variable_required': 'promptPresetVariableRequired',
  'contract.subagent_name_required': 'subagentNameRequired',
  'contract.subagent_name_format_invalid': 'subagentNameFormatInvalid',
  'contract.subagent_description_required': 'subagentDescriptionRequired',
  'contract.subagent_name_duplicate': 'subagentNameDuplicate',
  'contract.output_event_types_invalid': 'outputEventTypesInvalid',
  'contract.output_template_empty': 'outputTemplateEmpty',
  'contract.output_template_malformed': 'outputTemplateMalformed',
  'contract.output_template_unknown_variables': 'outputTemplateUnknownVariables',
  'storage.credential_metadata_invalid': 'credentialMetadataInvalid',
  'storage.unknown_block_type': 'unknownBlockType',
  'runtime.configuration': 'runtimeConfiguration',
}

function pathTokens(path: string): Array<string | number> {
  return [...path.matchAll(/([^.[\]]+)|\[(\d+)]/g)].flatMap((match) => {
    const value = match[1] ?? match[2]
    if (value === undefined) return []
    return /^\d+$/.test(value) ? [Number(value)] : [value]
  })
}

export function useValidationIssuePresentation() {
  const { t, te } = useI18n()

  function scopeLabel(issue: ValidationIssue): string {
    return t(`validation.scope.${issue.scope}`)
  }

  function ownerLabel(issue: ValidationIssue): string {
    if (issue.scope === 'block' && issue.owner_type) {
      return issue.owner_name
        ? t('validation.location.typedBlockOwner', {
            name: issue.owner_name,
            type: capabilityLabel(issue.owner_type),
          })
        : t('validation.location.currentTypedBlockOwner', {
            type: capabilityLabel(issue.owner_type),
          })
    }
    const scope = scopeLabel(issue)
    return issue.owner_name
      ? t('validation.location.namedOwner', { scope, name: issue.owner_name })
      : t('validation.location.currentOwner', { scope })
  }

  function fieldName(issue: ValidationIssue): string {
    const token = pathTokens(issue.path).findLast((part) => typeof part === 'string')
    return typeof token === 'string' ? token : issue.path
  }

  function fieldLabel(issue: ValidationIssue): string {
    const key = fieldLabelKeys(issue.path).find((candidate) => te(candidate))
    return key ? t(key) : fieldName(issue) || t('validation.location.wholeConfiguration')
  }

  function capabilityLabel(capabilityType: string): string {
    const key = `capabilities.${capabilityType}.label`
    return te(key) ? t(key) : capabilityType
  }

  function outputEventLabel(eventName: string): string {
    const key = `editors.outputMode.events.${eventName}.label`
    return te(key) ? t(key) : eventName
  }

  function messageArgs(issue: ValidationIssue): Record<string, JsonPrimitive> {
    const args = { ...issue.message_args }
    for (const key of [
      'capability_type',
      'dependency_type',
      'first_capability_type',
      'second_capability_type',
    ]) {
      const value = issue.message_args[key]
      if (typeof value !== 'string') continue
      args[`${key}_label`] = capabilityLabel(value)
    }
    const eventName = issue.message_args.event_name
    if (typeof eventName === 'string') {
      args.event_name_label = outputEventLabel(eventName)
    }
    return args
  }

  function location(issue: ValidationIssue): string {
    const tokens = pathTokens(issue.path)
    if (tokens.length === 0) return t('validation.location.wholeConfiguration')

    const labels: string[] = []
    let prefix = ''
    for (const token of tokens) {
      if (typeof token === 'number') {
        prefix = prefix ? `${prefix}.${token}` : String(token)
        const collection = labels.pop() ?? t('fields.unknown')
        labels.push(t('validation.location.indexedItem', {
          collection,
          index: token + 1,
        }))
        continue
      }

      const parentPrefix = prefix
      prefix = prefix ? `${prefix}.${token}` : token
      if (parentPrefix === 'capability_refs') {
        labels.push(capabilityLabel(token))
        continue
      }
      if (parentPrefix === 'event_templates') {
        labels.push(outputEventLabel(token))
        continue
      }
      const key = fieldLabelKeys(prefix).find((candidate) => te(candidate))
      labels.push(key
        ? t(key)
        : t('validation.location.unknownField', { field: token }))
    }
    const [first, ...rest] = labels
    if (!first) return t('validation.location.wholeConfiguration')
    return rest.reduce(
      (parent, child) => t('validation.location.nested', { parent, child }),
      first,
    )
  }

  function message(issue: ValidationIssue): string {
    if (issue.code === 'contract.text_too_short' && fieldName(issue) === 'name') {
      return t('validation.issue.contract.requiredText', { field: fieldLabel(issue) })
    }
    const args = messageArgs(issue)
    if (!te(issue.message_key)) {
      return t('validation.issue.fallback', {
        code: issue.code,
        location: location(issue),
      })
    }
    return t(issue.message_key, issue.code.startsWith('contract.')
      ? {
          ...args,
          field: issue.code === 'contract.unknown_field'
            ? fieldName(issue)
            : fieldLabel(issue),
        }
      : args)
  }

  function resolution(issue: ValidationIssue): string {
    const mappedKey = resolutionKeys[issue.code]
    if (mappedKey) {
      return t(`validation.resolution.${mappedKey}`, messageArgs(issue))
    }
    if (issue.code === 'contract.invalid_value') {
      return t('validation.resolution.checkValue', { field: fieldLabel(issue) })
    }
    if (issue.code.startsWith('contract.') && issue.code !== 'contract.unknown_field') {
      return t('validation.resolution.fixField', { field: fieldLabel(issue) })
    }
    if (issue.code !== 'contract.unknown_field') {
      return t('validation.resolution.reviewIssue', {
        code: issue.code,
        location: location(issue),
      })
    }
    const tokens = pathTokens(issue.path)
    const subagentIndex = tokens[0] === 'subagents' && typeof tokens[1] === 'number'
      ? tokens[1]
      : null
    if (issue.scope === 'primary' && issue.owner_name && subagentIndex !== null) {
      return t('validation.resolution.unknownPrimarySubagentField', {
        owner: issue.owner_name,
        index: subagentIndex + 1,
      })
    }
    if (issue.owner_name) {
      return t('validation.resolution.unknownOwnedField', {
        scope: scopeLabel(issue),
        owner: issue.owner_name,
      })
    }
    return t('validation.resolution.unknownField', { field: fieldName(issue) })
  }

  return { location, message, ownerLabel, resolution }
}
