import type { Issue } from '../../types'

interface Suggestion {
  title: string
  guidance: string[]
  before?: string
  after?: string
}

const suggestions: Record<string, Omit<Suggestion, 'before' | 'after'>> = {
  SEC001: { title: 'Avoid dynamic evaluation', guidance: ['Avoid evaluating untrusted input.', 'Parse the expected data format or map allowed operations to explicit handlers.', 'Do not replace eval() with another unsafe execution method.'] },
  SEC002: { title: 'Move secrets out of source', guidance: ['Provide credentials through environment variables or a secret manager.', 'Rotate any secret that has already been committed.'] },
  SEC003: { title: 'Pass subprocess arguments safely', guidance: ['Avoid shell=True where possible.', 'Pass a list of validated arguments and keep user input separate from command syntax.', 'The correct executable and arguments depend on the intended command.'] },
  SEC004: { title: 'Use a suitable cryptographic hash', guidance: ['Do not use MD5 or SHA-1 for security-sensitive hashing.', 'Choose a modern algorithm for integrity use cases. For passwords, use a dedicated password-hashing algorithm such as Argon2, scrypt, or bcrypt, not plain SHA-256.'] },
  SEC005: { title: 'Parameterize SQL inputs', guidance: ['Use the database driver’s parameterized query interface.', 'Placeholder syntax differs between database drivers; check the driver documentation.'] },
  BUG001: { title: 'Catch expected exceptions', guidance: ['Catch the specific exception types the operation can raise.', 'Avoid silently swallowing errors; handle, log, or propagate them deliberately.'] },
  BUG002: { title: 'Avoid mutable defaults', guidance: ['Use None as the default and create a fresh list or dictionary inside the function.', 'Mutable default objects are created once and can be shared across calls.'] },
  STYLE001: { title: 'Break up the long line', guidance: ['Split the expression into readable parts.', 'Use parentheses for a continued expression where appropriate.'] },
  STYLE002: { title: 'Document the public interface', guidance: ['Add a meaningful docstring describing the function or class purpose and relevant behavior.', 'Avoid placeholder docstrings that add no useful context.'] },
  SMELL001: { title: 'Make the function interface easier to use', guidance: ['Group closely related options only when it clarifies the API.', 'Consider keyword-only arguments; avoid adding abstractions for a small, simple function.'] },
  SMELL002: { title: 'Reduce nesting', guidance: ['Use early returns or guard clauses where they clarify the flow.', 'Consider extracting a logically separate operation into a helper.'] },
  SMELL003: { title: 'Simplify complex branching', guidance: ['Split distinct responsibilities into smaller functions.', 'Simplify branching while preserving behavior, and add focused tests when refactoring.'] },
  MAINT001: { title: 'Resolve or track the unfinished work', guidance: ['Decide whether the task should be completed now, documented, or tracked in your issue system.'] },
  MAINT002: { title: 'Verify and remove unused imports', guidance: ['Remove imports that are genuinely unused.', 'Check dynamic access and import side effects before removing an import.'] },
}

function previewFor(issue: Issue, sourceLine: string): Pick<Suggestion, 'before' | 'after'> {
  if (issue.rule_id !== 'SEC002') return {}
  const assignment = sourceLine.match(/^(\s*)([A-Za-z_]\w*)\s*=\s*.*$/)
  if (!assignment) return {}
  const [, indent, variable] = assignment
  return { before: sourceLine, after: `import os\n\n${indent}${variable} = os.getenv("${variable}")` }
}

export default function FixSuggestion({ issue, sourceLine }: { issue: Issue; sourceLine?: string }) {
  const known = suggestions[issue.rule_id]
  const details: Suggestion = known ? {
    ...known,
    ...previewFor(issue, sourceLine ?? ''),
  } : {
    title: 'Review this finding',
    guidance: [issue.remediation || 'Review the rule documentation and update the code to address this finding. No rule-specific suggestion is available.'],
  }

  return <section className="fix-suggestion" aria-label="Fix suggestion">
    <div className="fix-suggestion-heading"><div><strong>{details.title}</strong><span>Informational suggestion · review before changing code</span></div></div>
    <ul>{details.guidance.map(item => <li key={item}>{item}</li>)}</ul>
    {details.before !== undefined && details.after !== undefined && <div className="fix-preview">
      <div><span>Before · original line</span><pre><code>{details.before}</code></pre></div>
      <div><span>After · illustrative suggestion</span><pre><code>{details.after}</code></pre></div>
    </div>}
    <p className="fix-safety-note">Suggestions are examples, not guaranteed fixes. They are never applied automatically, and the submitted source stays unchanged.</p>
  </section>
}
