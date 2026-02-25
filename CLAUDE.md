# Development Team Configuration

## Team Structure

### Team Lead (Architect)
- **Model**: Claude Opus 4.6 (`opus`)
- **Role**: Project planning, architecture design, task distribution
- **Responsibilities**:
  - Create detailed implementation plans
  - Break down tasks into actionable items
  - Review and approve architectural decisions
  - NO code writing - planning only

### Developers (Coders)
- **Model**: Claude Sonnet 4.6 (`sonnet`)
- **Role**: Code implementation
- **Responsibilities**:
  - Write code based on plans from Team Lead
  - Implement features and fix bugs
  - Write tests
  - Follow coding standards

---

## Workflow

### 1. Planning Phase (Team Lead - Opus)
When starting a new feature or project:
```
Use Task tool with:
- subagent_type: "Plan"
- model: "opus"
```

### 2. Implementation Phase (Developers - Sonnet)
When implementing code:
```
Use Task tool with:
- subagent_type: "general-purpose" or "Bash"
- model: "sonnet"
```

---

## Usage Examples

### Start a new project planning
```
Task(
  description: "Plan feature implementation",
  prompt: "Create detailed implementation plan for [feature]",
  subagent_type: "Plan",
  model: "opus"
)
```

### Implement code based on plan
```
Task(
  description: "Implement feature",
  prompt: "Implement [feature] following the plan",
  subagent_type: "general-purpose",
  model: "sonnet"
)
```

---

## Coding Standards

- Follow existing project conventions
- Write clean, readable code
- Include appropriate error handling
- Add comments for complex logic only
- Write tests for new features

## Git Workflow

- Create feature branches for new work
- Write meaningful commit messages
- Request review before merging to main
