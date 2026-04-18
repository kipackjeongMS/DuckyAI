---
name: code-sanitization
description: Comprehensive code review and sanitization following SOLID, KISS, and industry-standard coding principles. Identifies flaws, bad practices, and suggests improvements with severity classification.
license: MIT
---

# Code Sanitization Skill

This skill performs deep code analysis to identify flaws, violations of coding principles, and areas for improvement. It follows industry-standard principles including SOLID, KISS, and general best practices.

## When to Use This Skill

- Before pull request reviews
- During refactoring sessions
- When code quality concerns are raised
- For technical debt assessment
- As part of code audit processes
- When onboarding new team members to existing codebases

## Analysis Workflow

Follow this systematic approach for code sanitization:

### 1. Initial Code Assessment

First, understand the code's purpose and context:
- Identify the programming language and framework
- Determine the code's responsibility and scope
- Note any existing documentation or comments
- Check for test coverage

### 2. SOLID Principles Review

Review each SOLID principle systematically. Reference `resources/solid-principles.md` for detailed guidelines.

**Check for violations:**
- **S**ingle Responsibility: Does each class/module have one reason to change?
- **O**pen/Closed: Is code open for extension but closed for modification?
- **L**iskov Substitution: Can derived classes substitute their base classes?
- **I**nterface Segregation: Are interfaces focused and not forcing unused methods?
- **D**ependency Inversion: Does code depend on abstractions, not concretions?

### 3. KISS Principle Review

Evaluate code simplicity using `resources/kiss-principles.md`:
- Identify overly complex logic
- Find unnecessary abstractions
- Spot over-engineering
- Check for clear, readable code

### 4. Anti-Pattern Detection

Cross-reference code against `resources/anti-patterns.md`:
- God Object / God Class
- Spaghetti Code
- Cargo Cult Programming
- Magic Numbers/Strings
- Copy-Paste Programming
- Premature Optimization
- Hard-Coded Dependencies

### 5. Quality Checklist Review

Run through `resources/quality-checklist.md` to ensure:
- Naming conventions
- Error handling
- Code organization
- Performance considerations
- Security practices
- Testing requirements

### 6. Severity Classification

Classify each finding using `resources/severity-rubric.md`:
- **CRITICAL**: Security vulnerabilities, data loss risks, breaking changes
- **HIGH**: Major SOLID violations, significant technical debt, poor error handling
- **MEDIUM**: Code smells, minor principle violations, readability issues
- **LOW**: Style inconsistencies, naming suggestions, optimization opportunities

## Output Format

Structure your analysis as follows:

```markdown
# Code Sanitization Report

## Summary
- Total Issues Found: [count]
- Critical: [count] | High: [count] | Medium: [count] | Low: [count]
- Overall Code Quality Score: [score/10]

## Critical Issues
[List critical severity issues with line numbers and explanations]

## High Priority Issues
[SOLID violations, major code smells]

## Medium Priority Issues
[Readability, minor violations]

## Low Priority Issues
[Style, minor improvements]

## Recommendations
1. [Prioritized action items]
2. [Refactoring suggestions]
3. [Best practice implementations]

## Positive Observations
[What the code does well]
```

## Cross-Reference Examples

When explaining violations, reference:
- `examples/good-patterns.md` - Show correct implementations
- `examples/bad-patterns.md` - Show what to avoid

## Language-Specific Considerations

Adapt principles to the language context:
- **Strongly typed languages** (Java, C#, TypeScript): Emphasize interface segregation, type safety
- **Dynamically typed languages** (Python, JavaScript): Focus on clear naming, documentation
- **Functional languages** (Haskell, Scala): Emphasize immutability, pure functions
- **System languages** (C++, Rust): Include memory safety, resource management

## Best Practices

1. **Be Constructive**: Frame feedback as improvement opportunities, not criticism
2. **Provide Context**: Explain WHY something is a problem, not just WHAT
3. **Show Solutions**: Include code examples of better approaches
4. **Prioritize**: Focus on high-impact issues first
5. **Balance**: Acknowledge good patterns alongside problems
6. **Be Pragmatic**: Consider project constraints and timelines

## Integration with Other Tools

This skill works well with:
- Static analysis tools (ESLint, SonarQube, Pylint)
- Security scanners (Snyk, Dependabot)
- Test coverage tools
- Performance profilers

## Example Invocation

```
/code-sanitization analyze src/UserService.ts
```

or simply describe the analysis in natural language and the agent will discover this skill automatically:

```
"Review this code for SOLID violations and suggest improvements"
"Check this codebase for code smells and anti-patterns"
"Sanitize this file following industry best practices"
```

## Resources Reference

All detailed guidelines are available in the `resources/` directory:
- `solid-principles.md` - Complete SOLID principles guide
- `kiss-principles.md` - KISS principle applications
- `anti-patterns.md` - Common anti-patterns catalog
- `quality-checklist.md` - Code quality verification
- `severity-rubric.md` - Issue severity classification

All code examples are in the `examples/` directory.
