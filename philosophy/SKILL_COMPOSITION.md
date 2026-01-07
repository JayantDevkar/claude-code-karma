# Skill Composition Philosophy

## Core Concepts

### Skills as Capabilities
Skills are atomic capabilities that agents compose to achieve their objectives.

```yaml
Skill Definition:
  - Single transformation or operation
  - Deterministic behavior
  - Composable with other skills
  - Self-contained logic
```

## Skill Categories

### 1. Foundation Skills
Every agent should have these:

```markdown
error_handling
├── Input validation
├── Error classification
└── Graceful degradation

output_formatting
├── Structure enforcement
├── Type consistency
└── Metadata inclusion
```

### 2. Domain Skills
Specific to agent's purpose:

```markdown
code_analysis
├── AST parsing
├── Pattern detection
└── Metric calculation

document_processing
├── Text extraction
├── Format conversion
└── Content structuring
```

### 3. Bridge Skills
Connect different domains:

```markdown
data_transformation
├── Format adapters
├── Schema mapping
└── Type conversion
```

## Composition Patterns

### 1. Pipeline Pattern
Skills execute in sequence:

```yaml
pdf_analyzer:
  pipeline:
    - extract_text
    - parse_structure  
    - analyze_content
    - generate_summary
```

### 2. Conditional Pattern
Skills selected based on input:

```yaml
file_processor:
  conditions:
    - if: file_type == "csv"
      use: csv_parser
    - if: file_type == "json"
      use: json_parser
    - else: text_parser
```

### 3. Parallel Pattern
Skills execute simultaneously:

```yaml
code_reviewer:
  parallel:
    - security_scan
    - style_check
    - performance_analysis
  merge: aggregate_results
```

## Skill Design Principles

### 1. Single Responsibility
Each skill does ONE thing well:

```markdown
✅ Good: parse_markdown_table
❌ Bad: handle_all_markdown
```

### 2. Predictable Interface
```typescript
interface Skill {
  input: DefinedSchema
  output: DefinedSchema
  errors: KnownErrorTypes[]
}
```

### 3. Stateless Execution
Skills don't maintain state between invocations:

```markdown
✅ parse(input) → output
❌ parse(input) → modifies_internal_state → output
```

## Skill Dependency Management

### Dependency Rules
1. **Max depth**: 3 levels
2. **Max breadth**: 5 skills per level
3. **Circular prevention**: No skill depends on itself

```yaml
skill_tree:
  generate_report:
    depends_on:
      - collect_data:
          depends_on:
            - read_source
            - validate_input
      - analyze_data:
          depends_on:
            - statistical_analysis
            - pattern_recognition
      - format_output
```

## Skill Testing Strategy

### Unit Testing
Each skill tested in isolation:

```python
def test_parse_json():
    input = '{"key": "value"}'
    expected = {"key": "value"}
    assert parse_json(input) == expected
```

### Integration Testing
Skills tested in combination:

```python
def test_pipeline():
    raw_data = load_test_file()
    result = extract_text(raw_data)
    result = parse_structure(result)
    assert validate_output(result)
```

## Skill Performance Metrics

### Efficiency Metrics
- **Execution time**: ms per operation
- **Memory usage**: MB consumed
- **Token consumption**: For LLM-based skills

### Quality Metrics
- **Accuracy**: Correct outputs / total outputs
- **Robustness**: Handled edge cases / total edge cases
- **Consistency**: Identical inputs → identical outputs

## Skill Evolution

### Versioning Strategy
```markdown
v1.0: Base functionality
v1.1: Performance optimization
v1.2: Additional input formats
v2.0: Algorithm change
```

### Deprecation Path
1. Mark deprecated in v1.8
2. Add warning in v1.9
3. Remove in v2.0
4. Provide migration guide

## Anti-Patterns

### 1. The Swiss Army Knife
```markdown
❌ Skill: do_everything
  - Parses files
  - Sends emails
  - Generates reports
  - Makes coffee
```

### 2. The Brittle Chain
```markdown
❌ Skills tightly coupled:
  - skill_a requires specific skill_b output format
  - skill_b can never change without breaking skill_a
```

### 3. The Hidden State
```markdown
❌ Skill modifies global state:
  - Writes to shared files
  - Modifies environment variables
  - Caches without invalidation
```

## Skill Library Organization

```
skills/
├── foundation/
│   ├── error_handling/
│   ├── validation/
│   └── formatting/
├── domain/
│   ├── code/
│   ├── document/
│   └── data/
├── bridge/
│   ├── converters/
│   └── adapters/
└── experimental/
    └── beta_features/
```

## Composition Examples

### Example 1: Code Documentation Generator
```yaml
agent: generate-documentation
skills:
  - parse_code_structure
  - extract_comments
  - analyze_signatures  
  - generate_markdown
  - validate_links
```

### Example 2: API Test Creator
```yaml
agent: create-api-tests
skills:
  - parse_openapi_spec
  - generate_test_cases
  - create_mock_data
  - format_test_suite
```
