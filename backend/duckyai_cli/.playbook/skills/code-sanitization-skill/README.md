# Code Sanitization Skill

A comprehensive GitHub Copilot skill for automated code review and sanitization following SOLID principles, KISS methodology, and industry-standard coding practices.

## Overview

This skill enables AI agents to perform deep code analysis, identifying flaws, anti-patterns, and areas for improvement across your codebase.

## Installation

### For Repository-Level (Team Use)

Copy the entire `code-sanitization` folder to your repository:

```bash
.github/skills/code-sanitization/
```

or

```bash
.claude/skills/code-sanitization/
```

### For Personal Use (All Projects)

Copy to your home directory:

```bash
~/.copilot/skills/code-sanitization/
```

or

```bash
~/.claude/skills/code-sanitization/
```

## Structure

```
code-sanitization/
├── SKILL.md                          # Main skill definition
├── resources/
│   ├── solid-principles.md          # Complete SOLID guide
│   ├── kiss-principles.md           # KISS principle applications
│   ├── anti-patterns.md             # Anti-patterns catalog
│   ├── quality-checklist.md         # Code quality checklist
│   └── severity-rubric.md           # Issue severity classification
└── examples/
    ├── good-patterns.md             # Examples of good code
    └── bad-patterns.md              # Examples of bad code (what to avoid)
```

## Usage

### Automatic Discovery

The agent will automatically invoke this skill when you mention:
- "Review this code for issues"
- "Check for SOLID violations"
- "Sanitize this codebase"
- "Find code smells and anti-patterns"
- "Analyze code quality"

### Manual Invocation

You can also explicitly call the skill:

```
/code-sanitization analyze src/UserService.ts
```

## Features

### Comprehensive Analysis
- **SOLID Principles**: Detects violations of all five SOLID principles
- **KISS Methodology**: Identifies over-engineering and unnecessary complexity
- **Anti-Patterns**: Recognizes 15+ common anti-patterns (God Object, Spaghetti Code, etc.)
- **Code Quality**: Validates against industry best practices
- **Severity Classification**: Prioritizes issues from CRITICAL to LOW

### Detailed Reporting
- Issue categorization by severity
- Line-by-line analysis with context
- Actionable recommendations
- Code examples (good vs. bad)
- Overall quality score

### Language Support
Adapts to:
- TypeScript/JavaScript
- Python
- Java/C#
- Go
- And more...

## What the Skill Analyzes

### SOLID Violations
- ✓ Single Responsibility breaches
- ✓ Open/Closed principle issues
- ✓ Liskov Substitution problems
- ✓ Interface Segregation violations
- ✓ Dependency Inversion failures

### KISS Violations
- ✓ Over-engineering
- ✓ Premature optimization
- ✓ Unnecessary abstractions
- ✓ Complex logic that could be simple
- ✓ Clever code vs. clear code

### Anti-Patterns
- ✓ God Object/God Class
- ✓ Spaghetti Code
- ✓ Copy-Paste Programming
- ✓ Magic Numbers/Strings
- ✓ Hard-Coded Dependencies
- ✓ Error Swallowing
- ✓ SQL Injection risks
- ✓ And more...

### Code Quality
- ✓ Naming conventions
- ✓ Function design
- ✓ Error handling
- ✓ Code organization
- ✓ Security practices
- ✓ Testing coverage
- ✓ Performance considerations

## Example Output

```markdown
# Code Sanitization Report

## Summary
- Total Issues Found: 12
- Critical: 1 | High: 3 | Medium: 5 | Low: 3
- Overall Code Quality Score: 6.5/10

## Critical Issues

### 1. SQL Injection Vulnerability (Line 45)
**Severity**: CRITICAL
**Category**: Security

The code constructs SQL queries using string interpolation, which is vulnerable to SQL injection attacks.

**Current Code**:
```typescript
const query = `SELECT * FROM users WHERE email = '${userEmail}'`;
```

**Recommended Fix**:
```typescript
const query = 'SELECT * FROM users WHERE email = ?';
await db.query(query, [userEmail]);
```

## High Priority Issues

### 2. God Object - UserManager Class (Lines 10-500)
**Severity**: HIGH
**Category**: SOLID (SRP Violation)

The UserManager class has 25+ methods handling database, email, validation, logging, and reporting. This violates the Single Responsibility Principle.

**Recommended Fix**: Split into focused classes:
- UserRepository (database)
- UserValidator (validation)
- EmailService (email)
- ActivityLogger (logging)

...
```

## Configuration

The skill uses progressive loading, so it only loads detailed resources when needed. This keeps your context window efficient.

## Best Practices

1. **Run Early**: Use during development, not just before deployment
2. **Fix High-Priority First**: Focus on CRITICAL and HIGH severity issues
3. **Iterate**: Don't try to fix everything at once
4. **Learn**: Use the good/bad examples to understand patterns
5. **Customize**: Adapt severity levels to your project needs

## Resources Included

### Reference Materials
- **solid-principles.md**: 2500+ words covering all SOLID principles with examples
- **kiss-principles.md**: Complete guide to simplicity in code
- **anti-patterns.md**: Catalog of 15+ anti-patterns with fixes
- **quality-checklist.md**: Comprehensive quality assessment checklist
- **severity-rubric.md**: Classification framework for prioritizing fixes

### Code Examples
- **good-patterns.md**: Examples of well-written code
- **bad-patterns.md**: Examples of what NOT to do

## Integration

Works seamlessly with:
- GitHub Copilot CLI
- VS Code Copilot
- GitHub Copilot coding agent
- Static analysis tools
- Code review workflows

## Customization

You can customize the skill by:
1. Editing severity thresholds in `severity-rubric.md`
2. Adding language-specific patterns
3. Including company-specific coding standards
4. Adjusting the analysis workflow in `SKILL.md`

## License

MIT

## Support

For issues or questions:
1. Check the resource files in `resources/`
2. Review example patterns in `examples/`
3. Consult the main `SKILL.md` for workflow details

## Version

1.0.0 - Initial Release

## Author

Created for comprehensive code quality analysis following industry standards.
