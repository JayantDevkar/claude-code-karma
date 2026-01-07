# Testing & Validation Philosophy

## Testing as First-Class Concern

### Test-Driven Agent Development (TDAD)
```markdown
1. Define behavior expectations
2. Write test cases
3. Implement agent
4. Validate behavior
5. Refine until passing
```

## Testing Hierarchy

### Level 1: Prompt Validation
```yaml
Test: Prompt syntax and structure
Method: Static analysis
Frequency: Every change
Duration: <1 second

Checks:
  - Required sections present
  - No contradictions
  - Clear boundaries defined
  - Output format specified
```

### Level 2: Skill Unit Tests
```yaml
Test: Individual skill functionality
Method: Isolated execution
Frequency: Every skill change
Duration: <5 seconds per skill

Validates:
  - Input handling
  - Core logic
  - Output format
  - Error states
```

### Level 3: Agent Integration Tests
```yaml
Test: Complete agent flow
Method: End-to-end execution
Frequency: Before deployment
Duration: <30 seconds

Verifies:
  - Skill composition
  - Tool interaction
  - State management
  - Error propagation
```

### Level 4: System Validation
```yaml
Test: Multi-agent workflows
Method: Full system simulation
Frequency: Release candidate
Duration: <5 minutes

Confirms:
  - Agent interoperability
  - Resource management
  - Performance targets
  - Failure recovery
```

## Test Case Design

### Structure
```markdown
test_case:
  name: "descriptive_test_name"
  given: # Initial state
    input: "specific input"
    context: "any context"
  when: # Action
    agent: "agent-name"
    operation: "specific operation"
  then: # Expected outcome
    output: "expected output"
    state: "expected state"
```

### Categories

#### Happy Path Tests
Normal, expected usage:
```yaml
- Valid input → Expected output
- Standard workflow completion
- Typical use cases
```

#### Edge Case Tests
Boundary conditions:
```yaml
- Empty input
- Maximum size input
- Unusual but valid formats
- Resource limits
```

#### Error Tests
Failure scenarios:
```yaml
- Invalid input
- Missing dependencies
- Network failures
- Timeout conditions
```

#### Regression Tests
Previous bugs:
```yaml
- Document each fixed bug
- Create test to prevent recurrence
- Run on every change
```

## Validation Strategies

### 1. Output Validation
```python
def validate_output(result):
    assert result is not None
    assert isinstance(result, expected_type)
    assert result.format == specified_format
    assert all_required_fields_present(result)
    return True
```

### 2. Behavioral Validation
```python
def validate_behavior(agent, test_suite):
    for test in test_suite:
        result = agent.execute(test.input)
        assert result.matches(test.expected)
        assert agent.used_only_allowed_tools()
        assert execution_time < test.max_duration
```

### 3. Consistency Validation
```python
def validate_consistency(agent, input):
    results = [agent.execute(input) for _ in range(5)]
    assert all(r == results[0] for r in results)
```

## Performance Testing

### Metrics to Track
```yaml
latency:
  - P50: <500ms
  - P95: <2000ms
  - P99: <5000ms

throughput:
  - Requests/second: >10
  - Concurrent requests: >5

resource_usage:
  - Memory: <500MB
  - CPU: <80%
  - Token consumption: <1000/request
```

### Load Testing Pattern
```python
def load_test(agent, duration_seconds=60):
    start = time.now()
    request_count = 0
    errors = 0
    
    while time.now() - start < duration_seconds:
        try:
            agent.execute(generate_test_input())
            request_count += 1
        except Exception as e:
            errors += 1
            log_error(e)
    
    return {
        'rps': request_count / duration_seconds,
        'error_rate': errors / request_count
    }
```

## Continuous Validation

### Pre-commit Hooks
```bash
#!/bin/bash
# .git/hooks/pre-commit

# Validate prompt syntax
./scripts/validate_prompts.sh

# Run unit tests
./scripts/run_unit_tests.sh

# Check skill dependencies
./scripts/check_dependencies.sh
```

### CI/CD Pipeline
```yaml
stages:
  - lint:
      - Prompt structure validation
      - Skill naming conventions
      - Documentation completeness
  
  - test:
      - Unit tests
      - Integration tests
      - Performance benchmarks
  
  - deploy:
      - Smoke tests
      - Canary deployment
      - Full rollout
```

## Error Analysis Framework

### Error Classification
```yaml
Level 1 - Input Errors:
  - Malformed input
  - Missing required fields
  - Type mismatches

Level 2 - Processing Errors:
  - Skill failures
  - Tool unavailability
  - Timeout

Level 3 - System Errors:
  - Out of memory
  - Network failure
  - Service unavailable
```

### Error Recovery Testing
```python
def test_recovery(agent):
    # Test graceful degradation
    with mock_tool_failure('primary_tool'):
        result = agent.execute(input)
        assert result.used_fallback == True
    
    # Test error messaging
    with invalid_input():
        result = agent.execute(bad_input)
        assert result.error.is_descriptive()
        assert result.error.suggests_fix()
```

## Test Documentation

### Test Case Documentation
```markdown
## Test: Generate PDF from Markdown

**Purpose**: Verify markdown to PDF conversion

**Setup**:
- Input: Valid markdown file with tables and images
- Agent: pdf-generator
- Skills: [parse_markdown, render_pdf]

**Execution**:
1. Load test markdown file
2. Execute agent with default settings
3. Validate PDF output

**Expected Results**:
- PDF generated successfully
- All markdown elements preserved
- File size < 10MB

**Edge Cases**:
- Empty markdown file
- Markdown with invalid syntax
- Very large markdown file (>100MB)
```

## Monitoring & Observability

### Key Metrics to Monitor
```yaml
availability:
  - Uptime percentage
  - Error rates
  - Response times

usage:
  - Requests per agent
  - Skill utilization
  - Token consumption

quality:
  - Task completion rate
  - User-reported issues
  - Output accuracy
```

### Alerting Thresholds
```yaml
critical:
  - Error rate > 10%
  - Latency P99 > 10s
  - Memory usage > 90%

warning:
  - Error rate > 5%
  - Latency P95 > 5s
  - Token usage > 80% budget
```

## Testing Philosophy Summary

1. **Test Early**: Write tests before implementation
2. **Test Often**: Run tests on every change
3. **Test Realistically**: Use production-like data
4. **Test Comprehensively**: Cover happy paths and failures
5. **Test Continuously**: Automate all testing
6. **Test Transparently**: Document all test results
