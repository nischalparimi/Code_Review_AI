export function categoryForRule(ruleId: string) {
  if (ruleId.startsWith('STYLE')) return 'Style'
  if (ruleId.startsWith('BUG')) return 'Bug pattern'
  if (ruleId.startsWith('SEC')) return 'Security'
  if (ruleId.startsWith('SMELL')) return 'Code smell'
  if (ruleId.startsWith('MAINT')) return 'Maintainability'
  return 'Other'
}

export function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}
