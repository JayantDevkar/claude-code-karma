# Context Engineering Principles

## Prompt as Software

### 1. Precision Over Verbosity
Every word in a prompt must earn its place.

```markdown
❌ Verbose:
"You are a helpful AI assistant that specializes in analyzing code and finding bugs
and issues and problems that might exist in the codebase..."

✅ Precise:
"Analyze code for bugs. Focus: logic errors, security vulnerabilities, performance issues."
```

### 2. Structured Context Hierarchy

```markdown
## Role
Single sentence defining agent's identity

## Objective
Specific, measurable goal

## Constraints
- Boundary 1
- Boundary 2
- Boundary 3

## Process
1. Step one
2. Step two
3. Step three

## Output Format
Exact structure required
```

### 3. Instruction Density

Maximize information per token:

```markdown
# Instead of:
"When you encounter an error, please make sure to handle it gracefully
and provide useful information to the user about what went wrong"

# Use:
"On error: log details, suggest fix, return structured error object"
```

## Context Boundaries

### Inclusion Principles

#### Always Include:
- Primary objective
- Input/output format
- Error handling instructions
- Scope boundaries

#### Never Include:
- Generic AI assistant preambles
- Philosophical discussions
- Redundant examples
- Meta-instructions about being AI

### Context Layering

```yaml
Base Layer (Immutable):
  - Core role
  - Fundamental constraints
  
Configuration Layer (Per-deployment):
  - Environment specifics
  - API endpoints
  - File paths

Dynamic Layer (Per-invocation):
  - User input
  - Previous results
  - Current state
```

## Prompt Patterns

### 1. Command Pattern
```markdown
ACTION: [verb]
TARGET: [specific object]
CONSTRAINTS: [list]
OUTPUT: [format]
```

### 2. Analysis Pattern
```markdown
ANALYZE: [target]
FOCUS: [specific aspects]
IGNORE: [out of scope]
REPORT: [structure]
```

### 3. Generation Pattern
```markdown
GENERATE: [artifact type]
BASED ON: [input/rules]
REQUIREMENTS: [list]
FORMAT: [specification]
```

## Anti-Patterns to Avoid

### 1. The Kitchen Sink
```markdown
❌ "You can also handle image processing, database queries, web scraping,
API calls, file manipulation, code generation, testing, deployment..."
```

### 2. The Philosopher
```markdown
❌ "As an AI, you should strive to be helpful, harmless, and honest,
considering the ethical implications of..."
```

### 3. The People Pleaser
```markdown
❌ "Always try to give the user what they want and be as helpful as possible
in any way you can..."
```

### 4. The Uncertain
```markdown
❌ "Maybe you could try to possibly attempt to perhaps..."
```

## Token Optimization Strategies

### 1. Reference Instead of Repeat
```markdown
# Define once
SECURITY_RULES:
- Validate all inputs
- Sanitize outputs  
- No arbitrary execution

# Reference later
Apply SECURITY_RULES to all operations
```

### 2. Implicit Through Structure
```markdown
# Instead of:
"First do X, then do Y, finally do Z"

# Use numbered list (implicit ordering):
1. X
2. Y
3. Z
```

### 3. Abbreviation Protocol
```markdown
# Define abbreviations
Abbrev:
- repo → repository
- config → configuration
- impl → implementation

# Use throughout
"Analyze repo config, validate impl"
```

## Testing Context Effectiveness

### Metrics
1. **Token Efficiency**: Output quality / prompt tokens
2. **Task Success Rate**: Successful completions / attempts
3. **Error Clarity**: Understandable errors / total errors
4. **Scope Adherence**: In-scope responses / total responses

### A/B Testing Framework
```yaml
Control: Current prompt
Variant: Modified prompt
Metrics: [efficiency, accuracy, speed]
Sample: 100 invocations
Decision: Statistical significance
```

## Version Control for Prompts

### Semantic Versioning
```
v1.0.0 - Major prompt restructure
v1.1.0 - Added new capability
v1.1.1 - Fixed ambiguous instruction
```

### Change Documentation
```markdown
## v1.1.0
### Added
- Explicit error handling for malformed JSON

### Changed  
- Simplified output format specification

### Removed
- Redundant examples in constraints section
```
