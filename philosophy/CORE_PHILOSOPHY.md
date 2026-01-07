# Core Philosophy: Claude Code Agent Development

## Fundamental Principles

### 1. Single Responsibility
Each agent performs **one domain** exceptionally well. Multi-purpose agents dilute effectiveness.

### 2. Explicit Over Implicit
- Clear naming that describes action: `pdf-analyzer` not `doc-helper`
- Defined boundaries: what the agent does AND doesn't do
- Transparent tool selection: each tool has a specific purpose

### 3. Composition Over Complexity
Build complex workflows by combining simple, specialized agents rather than creating monolithic super-agents.

### 4. Context as Code
Treat prompts and descriptions as critical software components:
- Version control all agent definitions
- Test agent responses systematically
- Refactor prompts like you would refactor code

### 5. Fail Fast, Fail Clear
Agents should:
- Recognize their limitations immediately
- Communicate boundaries explicitly
- Suggest the appropriate specialized agent when out of scope

## Design Constraints

### Minimalism Rules
- **Less is More**: Start with minimum viable agent
- **No Feature Creep**: Resist adding "just one more" capability
- **Tool Austerity**: Use the fewest tools that solve the problem completely

### Performance First
- Optimize for token efficiency in prompts
- Choose `opusplan` only when complexity demands it
- Design for resumability from day one

## Success Metrics
An agent is successful when:
1. Its name alone tells you what it does
2. It refuses tasks outside its expertise
3. It completes its specialized task in minimal iterations
4. Other agents can reliably depend on its output
