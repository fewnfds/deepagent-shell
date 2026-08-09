import type { MiddlewareConfigSchema } from '@/api'

export function middlewareConfigDefaults(
  schema: MiddlewareConfigSchema,
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(schema.properties).flatMap(([name, field]) => (
      Object.prototype.hasOwnProperty.call(field, 'default')
        ? [[name, field.default]]
        : []
    )),
  )
}
