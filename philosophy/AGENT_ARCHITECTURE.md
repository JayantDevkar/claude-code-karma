# Agent Architecture Philosophy

## Structural Principles

### 1. Stateless by Default
Agents should not rely on session state unless explicitly designed for resumability.

```yaml
# Good: Each invocation is independent
agent:
  input: file_path
  output: analysis_result
  state: none

# Exception: Research agents with explicit resume capability
agent:
  input: query
  output: findings
  state: agentId (for resumption)
```

### 2. Tool Selection Strategy

#### Minimal Tool Set
Only include tools that directly support the agent's single responsibility.

```yaml
# PDF Creator Agent - Minimal tools
tools:
  - file_system  # Read/write files
  - pdf_library  # PDF manipulation
  # NOT included: web_search, database, image_processing
```

#### Tool Hierarchy
1. **Primary Tools**: Essential for core function (1-2 max)
2. **Support Tools**: Enable primary function (1-2 max)
3. **Never Include**: "Just in case" tools

### 3. Model Selection Logic

#### Use Sonnet (Default) When:
- Task is well-defined
- Pattern matching suffices
- Speed is critical
- Token budget is constrained

#### Use OpusPlan When:
- Complex reasoning required
- Multi-step planning needed
- Quality > Speed
- Novel problem solving

### 4. Skill Composition

#### Skill Stacking Rules
```
Base Skills (Always):
├── error_handling
├── input_validation
└── output_formatting

Domain Skills (Selective):
├── file_type_specific
├── api_specific
└── format_specific

Never Mix:
├── frontend + backend in same agent
├── data_analysis + data_visualization
└── testing + implementation
```

## Communication Patterns

### Inter-Agent Protocol
Agents communicate through well-defined contracts:

```yaml
Input Contract:
  format: JSON/YAML
  schema: predefined
  validation: strict

Output Contract:
  format: structured
  errors: typed
  metadata: included
```

### Error Hierarchies
1. **Input Errors**: Return immediately with guidance
2. **Capability Errors**: Suggest appropriate agent
3. **Execution Errors**: Provide detailed context
4. **System Errors**: Fail gracefully with state preservation

## Resumability Design

### When to Enable Resumability
- Long-running tasks (>5 min)
- Research/exploration agents
- Multi-step workflows
- Expensive operations

### Resume Architecture
```
agent-{agentId}.jsonl structure:
├── checkpoint: stage_identifier
├── partial_results: accumulated_data
├── next_action: planned_operation
└── context: necessary_state
```

## Performance Optimization

### Token Economics
1. **Prompt Compression**: Remove redundancy, use references
2. **Context Pruning**: Only include relevant history
3. **Output Efficiency**: Structure over prose

### Execution Patterns
```
Fast Path (90% cases):
Input → Validation → Execution → Output

Slow Path (10% cases):
Input → Validation → Planning → Multi-step → Aggregation → Output
```

## Testing Philosophy

### Agent Testing Levels
1. **Unit**: Individual capability validation
2. **Integration**: Inter-agent communication
3. **End-to-End**: Complete workflow validation
4. **Edge Cases**: Boundary condition handling

### Test-Driven Agent Development
```bash
1. Define expected behavior (tests)
2. Implement minimal agent
3. Refine prompt/tools
4. Validate against tests
5. Document limitations
```
