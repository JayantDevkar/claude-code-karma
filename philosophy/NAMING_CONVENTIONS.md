# Naming Conventions: Agents & Skills

## Agent Naming

### Format: `{action}-{target}`
- **action**: Single verb describing primary operation
- **target**: Specific domain or object type

### Examples
✅ **Good Names**
- `analyze-repository`
- `generate-tests`
- `refactor-typescript`
- `validate-schema`
- `search-documentation`

❌ **Avoid**
- `helper` (too vague)
- `code-assistant-pro` (marketing speak)
- `do-everything` (violates single responsibility)
- `AI-buddy` (not descriptive)

## Skill Naming

### Format: `{domain}_{operation}`
- Use underscores for skills (vs hyphens for agents)
- Keep to 2-3 words maximum

### Categories
```
data_extraction
code_generation  
file_manipulation
api_integration
validation_logic
```

## Description Rules

### Agent Descriptions
Start with action verb, specify domain:
- ✅ "Analyzes Python codebases for security vulnerabilities"
- ❌ "A helpful tool for various code tasks"

### Skill Descriptions
State the transformation or operation:
- ✅ "Converts markdown tables to CSV format"
- ❌ "Works with data"

## Prompt Naming

### File Convention
```
prompts/
├── agent_{name}_system.md
├── agent_{name}_context.md
└── skill_{name}_instruction.md
```

## Reserved Prefixes
- `test-`: Development/testing agents only
- `legacy-`: Deprecated but maintained
- `experimental-`: Not production ready
- `core-`: Foundation agents that others depend on

## Anti-Patterns to Avoid
1. **Anthropomorphizing**: No human names (Bob, Alice)
2. **Version Numbers**: Use git tags, not `agent-v2`
3. **Company/Project Names**: Keep generic for reusability
4. **Cute Names**: No `ninja`, `wizard`, `rockstar`
