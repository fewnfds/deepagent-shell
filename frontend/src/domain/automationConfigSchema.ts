import type { AutomationConfigSchema } from '@/api'

export function automationConfigDefaults(
  schema: AutomationConfigSchema,
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(schema.properties).flatMap(([name, field]) => (
      Object.prototype.hasOwnProperty.call(field, 'default')
        ? [[name, field.default]]
        : []
    )),
  )
}
