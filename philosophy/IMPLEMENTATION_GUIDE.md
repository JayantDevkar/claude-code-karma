# Implementation Guide: From Philosophy to Practice

## Starting a New Agent

### Step 1: Define the Problem
```markdown
Problem: "We need to analyze Python code for security issues"

Questions to Answer:
1. What specific security issues? (SQL injection, XSS, etc.)
2. What's the input? (Single file, repository, package?)
3. What's the output? (Report format, severity levels?)
4. What's NOT in scope? (Performance, style, documentation?)
```

### Step 2: Design the Agent
```yaml
# agents/analyze-security-python.yaml

name: analyze-security-python
description: "Analyzes Python code for OWASP Top 10 vulnerabilities"

# Single responsibility clearly defined
responsibility: |
  Detect security vulnerabilities in Python code including:
  - SQL injection risks
  - XSS vulnerabilities  
  - Insecure deserialization
  - Hardcoded credentials
  
boundaries:
  includes:
    - Static analysis of .py files
    - Dependency vulnerability checking
    - Security anti-pattern detection
  
  excludes:
    - Code style issues
    - Performance problems
    - Documentation gaps
    - Runtime behavior analysis
```

### Step 3: Write Tests First
```python
# tests/test_analyze_security_python.py

def test_detects_sql_injection():
    code = """
    def get_user(user_id):
        query = f"SELECT * FROM users WHERE id = {user_id}"
        return db.execute(query)
    """
    
    result = agent.analyze(code)
    assert "sql_injection" in result.vulnerabilities
    assert result.severity == "HIGH"

def test_ignores_safe_parameterized_queries():
    code = """
    def get_user(user_id):
        query = "SELECT * FROM users WHERE id = ?"
        return db.execute(query, [user_id])
    """
    
    result = agent.analyze(code)
    assert "sql_injection" not in result.vulnerabilities

def test_stays_in_scope():
    code = """
    def poorlyNamedFunction():  # Bad style but not security issue
        return secure_hash(data)
    """
    
    result = agent.analyze(code)
    assert len(result.vulnerabilities) == 0
```

### Step 4: Create Minimal Prompt
```markdown
# prompts/analyze_security_python.md

## Role
Security analyzer for Python code.

## Objective
Identify OWASP Top 10 vulnerabilities in Python source code.

## Process
1. Parse code structure
2. Identify dangerous patterns:
   - String concatenation in queries
   - Eval/exec with user input
   - Pickle with untrusted data
   - Hardcoded secrets (API keys, passwords)
3. Classify severity (LOW/MEDIUM/HIGH/CRITICAL)
4. Generate actionable fixes

## Constraints
- Only analyze security issues
- Ignore style/performance/documentation
- Focus on exploitable vulnerabilities
- Provide concrete remediation

## Output Format
```json
{
  "vulnerabilities": [
    {
      "type": "sql_injection",
      "severity": "HIGH",
      "location": "line 42",
      "description": "Unsanitized user input in query",
      "fix": "Use parameterized queries"
    }
  ],
  "summary": {
    "critical": 0,
    "high": 1,
    "medium": 0,
    "low": 0
  }
}
```
```

### Step 5: Select Minimal Tools
```yaml
tools:
  primary:
    - code_parser      # Parse Python AST
    - pattern_matcher  # Detect vulnerable patterns
  
  # Note: No need for file_system, web_search, database, etc.
```

### Step 6: Implement Core Skills
```javascript
// skills/security_patterns.js

const VULNERABLE_PATTERNS = {
  sql_injection: {
    pattern: /f["'].*SELECT|INSERT|UPDATE|DELETE.*{.*}/,
    severity: 'HIGH',
    fix: 'Use parameterized queries with ? placeholders'
  },
  
  hardcoded_secret: {
    pattern: /api_key|password|secret.*=.*["'][\w]+["']/i,
    severity: 'MEDIUM',
    fix: 'Use environment variables or secret management service'
  },
  
  dangerous_eval: {
    pattern: /eval\(|exec\(/,
    severity: 'CRITICAL',
    fix: 'Avoid eval/exec, use ast.literal_eval for data'
  }
};

export function detectPatterns(code) {
  const vulnerabilities = [];
  
  for (const [type, config] of Object.entries(VULNERABLE_PATTERNS)) {
    if (config.pattern.test(code)) {
      vulnerabilities.push({
        type,
        severity: config.severity,
        fix: config.fix
      });
    }
  }
  
  return vulnerabilities;
}
```

## Real-World Examples

### Example 1: Document Processor
```yaml
# Focused single-purpose agent
name: extract-text-pdf
description: "Extracts plain text from PDF documents"

# Clear boundaries
not_this_agent:
  - OCR for scanned PDFs → use: ocr-pdf
  - PDF generation → use: create-pdf  
  - Format conversion → use: convert-document

tools:
  - pdf_parser  # Only tool needed

prompt: |
  Extract text from PDF preserving structure.
  Output: Plain text with paragraph breaks.
  Ignore: Images, formatting, metadata.
```

### Example 2: API Test Generator
```yaml
name: generate-api-tests
description: "Creates test suites from OpenAPI specifications"

# Composition of focused skills
skills:
  - parse_openapi_spec
  - generate_test_cases
  - create_mock_responses
  - format_test_code

# Minimal tool set
tools:
  - yaml_parser     # Read OpenAPI spec
  - code_generator  # Create test code

# Resumable for large APIs
resumable: true
checkpoint_on: each_endpoint
```

### Example 3: Code Reviewer Pipeline
```yaml
# Multiple specialized agents working together
pipeline:
  - agent: analyze-security-python
    output: security_report
    
  - agent: check-style-python  
    output: style_report
    
  - agent: calculate-complexity
    output: complexity_metrics
    
  - agent: generate-review-summary
    inputs: [security_report, style_report, complexity_metrics]
    output: final_review
```

## Common Implementation Pitfalls

### Pitfall 1: Scope Creep
```yaml
# ❌ BAD: Agent doing too much
name: python-helper
responsibilities:
  - Analyze security
  - Fix style issues
  - Generate documentation
  - Run tests
  - Deploy code
  
# ✅ GOOD: Focused agents
agents:
  - analyze-security-python
  - format-code-python
  - generate-docs-python
  - run-tests-python
  - deploy-python-app
```

### Pitfall 2: Over-Engineering
```yaml
# ❌ BAD: Complex for simple task
name: hello-world-printer
tools: [database, cache, queue, monitoring, analytics]
prompt: |
  ... 500 lines of instructions ...

# ✅ GOOD: Simple for simple task  
name: print-greeting
tools: []
prompt: "Output: 'Hello, World!'"
```

### Pitfall 3: Poor Error Handling
```python
# ❌ BAD: Silent failures
def process(input):
    try:
        return transform(input)
    except:
        return None  # Lost error context

# ✅ GOOD: Informative errors
def process(input):
    try:
        return transform(input)
    except ValidationError as e:
        return {
            'error': 'Invalid input format',
            'details': str(e),
            'suggestion': 'Check input matches schema'
        }
```

## Measuring Success

### Agent Quality Metrics
```python
def calculate_agent_score(agent):
    scores = {
        'focus': rate_single_responsibility(agent),      # 0-100
        'efficiency': measure_token_usage(agent),        # 0-100  
        'reliability': calculate_success_rate(agent),    # 0-100
        'speed': measure_response_time(agent),          # 0-100
        'test_coverage': get_test_coverage(agent)       # 0-100
    }
    
    return {
        'total': sum(scores.values()) / len(scores),
        'breakdown': scores,
        'grade': get_grade(scores['total'])  # A, B, C, D, F
    }
```

### Success Indicators
```yaml
Green Flags:
  - Name immediately conveys function
  - Rejects out-of-scope requests
  - Consistent output format
  - Fast response times (<1s)
  - High test coverage (>90%)
  - Other agents depend on it
  
Red Flags:
  - Vague or generic name
  - Tries to do everything
  - Inconsistent outputs
  - Slow responses (>5s)
  - No tests
  - No other agent uses it
```

## Evolution Strategy

### Version 1.0: MVP
```yaml
Focus: Core functionality only
Features: Minimum viable capability
Testing: Happy path coverage
Performance: Functional but not optimized
```

### Version 1.1: Hardening
```yaml
Focus: Error handling and edge cases
Features: No new features
Testing: Edge case coverage
Performance: Basic optimizations
```

### Version 2.0: Enhancement
```yaml
Focus: New capabilities
Features: Additional use cases
Testing: Full regression suite
Performance: Optimized for scale
```

## Summary

1. **Start small** - MVP first, enhance later
2. **Test everything** - Behavior drives implementation  
3. **Maintain boundaries** - Resist scope creep
4. **Optimize tokens** - Every word has a cost
5. **Document clearly** - Others will use your agent
6. **Monitor continuously** - Track performance in production
7. **Iterate deliberately** - Plan versions, don't randomly add features
