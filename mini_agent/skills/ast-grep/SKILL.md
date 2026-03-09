---
name: ast-grep
description: Use ast-grep for massive structural code search and replacement. Use when user wants to refactor, rename, add patterns, or make bulk changes across a codebase - especially for 3+ files with complex AST-based transformations. Supports pattern matching with meta variables ($VAR, $$$VAR), YAML rules, JSON output, and 20+ languages including JavaScript, Python, Rust, Go.
---

# ast-grep: Structural Code Search and Replace

ast-grep (`sg`) uses tree-sitter AST parsing for semantic pattern matching. Use for bulk code refactoring across multiple files.

## When to Use

**USE when:** Renaming functions/classes, changing call patterns, converting code (var→const, lambda→def), refactoring APIs, 3+ files need similar changes.

**AVOID when:** 1-2 files, unique per-file changes, non-code files (JSON/YAML/Markdown), simple text replacement.

## Quick Start

### 1. Search (Dry Run)
```bash
sg scan --json -p 'PATTERN' .
sg scan --json -p 'PATTERN' -l python .
```

### 2. Preview Rewrite
```bash
sg run -p 'PATTERN' -r 'REPLACEMENT' .
```

### 3. Apply Changes
```bash
sg run -p 'PATTERN' -r 'REPLACEMENT' -U .
```

## Pattern Syntax

### Meta Variables

| Pattern | Matches |
|---------|---------|
| `$VAR` | Any single AST node |
| `$$$VAR` | Zero or more AST nodes |
| `$_VAR` | Non-capturing (faster) |
| `$$VAR` | Unnamed tree-sitter nodes |

**Naming:** `$A`, `$FUNC`, `$ARG1`, `$$$ARGS` (valid) vs `$lowercase`, `$123` (invalid)

### Capturing

Same-name variables capture AND reuse:
```bash
# $A == $A matches: a==a, x==x
# Does NOT match: a==b
sg scan -p '$A == $A'
```

Rewrite using captured: `sg run -p '$X = $Y' -r '$Y = $X'` swaps sides.

### JavaScript/TypeScript
```bash
# Function calls
sg scan -p 'console.log($MSG)'
sg scan -p '$OBJ.$METHOD($$$ARGS)'

# Declarations
sg scan -p 'var $X = $Y'
sg scan -p 'const $X = $Y'
sg scan -p 'const $NAME = ($ARGS) => $BODY'
```

### Python
```bash
# Functions
sg scan -p 'def $FUNC($$$ARGS):'
sg scan -p 'def $FUNC($ARG: $TYPE) -> $RET:'

# Lambda
sg scan -p 'lambda $ARGS: $BODY'

# Imports
sg scan -p 'from $MODULE import $$$NAMES'
```

### Rust
```bash
sg scan -p 'fn $FUNC($$$ARGS) -> $RET {$BODY}'
sg scan -p 'impl $NAME {$BODY}'
sg scan -p '$X.unwrap()'
```

### Go
```bash
sg scan -p 'func $NAME($$$PARAMS) $RETTYPE {$BODY}'
sg scan -p '$X, $ERR := $FUNC()'
```

## YAML Rules

For complex rules, create `rule.yml`:

```yaml
id: my-rule
language: python
rule:
  pattern: |
    def $FUNC($ARG):
      $$$BODY
fix: |
  def $FUNC($ARG):
    $$$BODY
    print("Called:", "$FUNC")
```

Run: `sg scan -r rule.yml . -U`

### Multiple Rules
```yaml
---
id: rule-1
rule:
  pattern: foo($X)
fix: bar($X)
---
id: rule-2
rule:
  pattern: old_func($X)
fix: new_func($X)
```

## Common CLI Options

| Option | Description |
|--------|-------------|
| `-p, --pattern` | AST pattern |
| `-r, --rewrite` | Replacement string |
| `-l, --lang` | Language (python, javascript, etc.) |
| `-U, --update-all` | Apply all changes without confirmation |
| `--json` | JSON output (pretty, stream, compact) |
| `--globs` | File filter (e.g., "*.js") |
| `-j, --threads` | Number of threads |
| `--stdin` | Read pattern from stdin |
| `-i, --interactive` | Interactive edit session |
| `--no-ignore` | Ignore .gitignore files |

```bash
# Rename function everywhere
sg run -p 'oldFunc($$$ARGS)' -r 'newFunc($$$ARGS)' -U .

# Convert var to const
sg run -p 'var $X = $Y' -r 'const $X = $Y' -U .

# Python print to logging
sg run -p 'print($MSG)' -r 'logger.info($MSG)' -U .

# Lambda to def
sg run -p '$F = lambda $A: $B' -r 'def $F($A):\n  return $B' -U .

# Add try-catch
sg run -p '$FUNC($$$ARGS)' -r 'try { $FUNC($$$ARGS) } catch (e) { }' -U .

# TypeScript types
sg run -p 'function $F($X)' -r 'function $F($X: string): void' -U .

# Remove object property (YAML)
# See references/yaml-examples.md
```

## Important Notes

1. **ALWAYS dry run first** - use `--json` to preview
2. **Backup with git** before mass changes
3. **Indentation preserved** in rewrite
4. **One rule at a time** for complex refactoring

## Troubleshooting

- **No matches:** Check pattern is valid code, verify language
- **Too many matches:** Make pattern more specific, use `--globs`
- **Syntax errors:** Ensure replacement is valid code

## More Details

See `references/` directory for:
- Complete YAML rule schema
- More examples by language
- Advanced features (expandStart, expandEnd, transformations)
