# Code Quality Checklist

A comprehensive checklist for evaluating code quality across multiple dimensions.

---

## 1. Naming Conventions

### Variables & Constants

- [ ] Variables use meaningful, descriptive names
- [ ] Boolean variables start with is/has/can/should
- [ ] Constants use UPPER_SNAKE_CASE (language dependent)
- [ ] No single-letter names except loop counters
- [ ] No abbreviations unless widely understood
- [ ] Names reveal intent without needing comments

**Examples**:
```typescript
✅ const MAX_RETRY_ATTEMPTS = 3;
✅ const isUserAuthenticated = true;
✅ const hasValidEmail = checkEmail(user.email);

❌ const x = 3; // What is x?
❌ const flg = true; // What flag?
❌ const usrAuth = true; // Unnecessary abbreviation
```

### Functions & Methods

- [ ] Function names are verbs or verb phrases
- [ ] Names describe what the function does
- [ ] Names are unambiguous
- [ ] Consistent naming patterns across codebase
- [ ] Avoid generic names (doStuff, handleData, process)

**Examples**:
```typescript
✅ calculateTotalPrice()
✅ sendWelcomeEmail()
✅ validateUserInput()

❌ doWork()
❌ handle()
❌ process()
```

### Classes & Interfaces

- [ ] Class names are nouns or noun phrases
- [ ] Interface names describe contracts/capabilities
- [ ] No generic suffixes (Manager, Handler) unless necessary
- [ ] Names reflect single responsibility

**Examples**:
```typescript
✅ UserRepository
✅ PaymentProcessor
✅ EmailService
✅ interface Serializable { }

❌ DataManager
❌ UserHelper
❌ Utility
```

---

## 2. Function Design

### Size & Complexity

- [ ] Functions are under 50 lines
- [ ] Cyclomatic complexity < 10
- [ ] Maximum 3-4 parameters (use objects for more)
- [ ] Single level of abstraction per function
- [ ] No deeply nested logic (< 4 levels)

### Responsibility

- [ ] Each function does ONE thing
- [ ] Function name matches what it does
- [ ] No side effects unless obvious from name
- [ ] Pure functions when possible
- [ ] Clear input/output relationship

**Examples**:
```typescript
✅ function calculateDiscount(price: number, percentage: number): number
✅ function isValidEmail(email: string): boolean

❌ function processUser() {
  // validates, saves, emails, logs - too much!
}
```

### Return Values

- [ ] Consistent return types
- [ ] Avoid returning null when possible (use Optional/Maybe)
- [ ] Error conditions throw exceptions or return Result types
- [ ] Documented return value meaning

---

## 3. Error Handling

### Exception Handling

- [ ] Specific exceptions caught, not generic Exception
- [ ] Catch blocks are never empty
- [ ] Errors are logged with context
- [ ] Critical errors propagate appropriately
- [ ] User-friendly error messages

**Examples**:
```typescript
✅ 
try {
  await database.save(user);
} catch (error) {
  logger.error('Failed to save user', { userId: user.id, error });
  throw new DatabaseError('Unable to save user data', { cause: error });
}

❌
try {
  await database.save(user);
} catch (error) {
  // Silent failure
}
```

### Validation

- [ ] Input validation at boundaries
- [ ] Fail fast with clear error messages
- [ ] Validate preconditions
- [ ] Check for null/undefined
- [ ] Type safety enforced

---

## 4. Code Organization

### File Structure

- [ ] Related code grouped together
- [ ] Clear separation of concerns
- [ ] Consistent file organization
- [ ] Files under 500 lines
- [ ] One primary class/component per file

### Module Organization

- [ ] Clear module boundaries
- [ ] Minimal coupling between modules
- [ ] High cohesion within modules
- [ ] Public vs private members clearly defined
- [ ] Logical folder structure

**Structure Example**:
```
src/
  ├── domain/          # Business logic
  ├── infrastructure/  # External services
  ├── api/            # Controllers/Routes
  ├── services/       # Application services
  └── utils/          # Shared utilities
```

### Dependencies

- [ ] Dependencies flow in one direction
- [ ] No circular dependencies
- [ ] Minimal dependencies per module
- [ ] External dependencies isolated
- [ ] Dependency injection used appropriately

---

## 5. Comments & Documentation

### When to Comment

- [ ] Complex algorithms explained
- [ ] Non-obvious business rules documented
- [ ] Public APIs documented
- [ ] Workarounds or hacks justified
- [ ] TODO/FIXME tracked properly

### What NOT to Comment

- [ ] Self-explanatory code not over-commented
- [ ] No commented-out code (use version control)
- [ ] No obvious comments ("increment i")
- [ ] No misleading or outdated comments

**Examples**:
```typescript
✅ 
// Using binary search because dataset can be millions of records
// Time complexity: O(log n)
function findUser(id: number): User { }

✅
/**
 * Calculates compound interest using A = P(1 + r/n)^(nt)
 * @param principal - Initial investment
 * @param rate - Annual interest rate (decimal)
 * @param years - Investment period
 * @returns Final amount
 */
function calculateCompoundInterest(principal: number, rate: number, years: number): number

❌
// Increment i
i++;

❌
// const oldCode = doSomething(); // Don't commit commented code!
```

---

## 6. Testing

### Test Coverage

- [ ] Critical paths have tests
- [ ] Edge cases covered
- [ ] Error conditions tested
- [ ] Happy path tested
- [ ] Test coverage > 80% for business logic

### Test Quality

- [ ] Tests are independent
- [ ] Tests are repeatable
- [ ] Tests are fast
- [ ] One assertion per test (generally)
- [ ] Tests document behavior

**Test Structure**:
```typescript
✅
describe('UserService', () => {
  describe('createUser', () => {
    it('should create user with valid data', async () => {
      // Arrange
      const userData = { email: 'test@example.com', name: 'Test' };
      
      // Act
      const user = await userService.createUser(userData);
      
      // Assert
      expect(user.id).toBeDefined();
      expect(user.email).toBe(userData.email);
    });

    it('should throw error when email is invalid', async () => {
      const userData = { email: 'invalid', name: 'Test' };
      
      await expect(userService.createUser(userData))
        .rejects.toThrow('Invalid email');
    });
  });
});
```

---

## 7. Performance Considerations

### Algorithmic Efficiency

- [ ] Appropriate data structures chosen
- [ ] No unnecessary loops
- [ ] Avoid N+1 queries
- [ ] Complexity is reasonable for use case
- [ ] Caching used appropriately

### Resource Management

- [ ] Connections properly closed
- [ ] Memory leaks prevented
- [ ] File handles released
- [ ] Event listeners cleaned up
- [ ] Large objects disposed

**Examples**:
```typescript
✅
async function processUsers() {
  // Good: Single query
  const users = await db.query('SELECT * FROM users');
  return users.map(processUser);
}

❌
async function processUsers() {
  // Bad: N+1 queries
  const userIds = await db.query('SELECT id FROM users');
  return Promise.all(userIds.map(id => 
    db.query('SELECT * FROM users WHERE id = ?', [id])
  ));
}
```

---

## 8. Security Best Practices

### Input Validation

- [ ] All user input sanitized
- [ ] SQL injection prevented (parameterized queries)
- [ ] XSS prevented (output encoding)
- [ ] CSRF protection in place
- [ ] File upload validation

### Authentication & Authorization

- [ ] No hardcoded credentials
- [ ] Passwords properly hashed (bcrypt, argon2)
- [ ] Secure session management
- [ ] Authorization checks on all endpoints
- [ ] Principle of least privilege

### Data Protection

- [ ] Sensitive data encrypted at rest
- [ ] Sensitive data encrypted in transit (HTTPS)
- [ ] No logging of passwords/tokens
- [ ] PII handled according to regulations
- [ ] Secure random number generation

**Security Checklist**:
```typescript
✅
// Parameterized query
const user = await db.query(
  'SELECT * FROM users WHERE email = ?', 
  [userInput]
);

✅
// Password hashing
const hashedPassword = await bcrypt.hash(password, 10);

❌
// SQL injection vulnerability
const user = await db.query(
  `SELECT * FROM users WHERE email = '${userInput}'`
);

❌
// Storing plain text password
const user = { email, password }; // NEVER DO THIS
```

---

## 9. Code Consistency

### Style Consistency

- [ ] Consistent indentation (tabs vs spaces)
- [ ] Consistent brace placement
- [ ] Consistent naming conventions
- [ ] Linter rules followed
- [ ] Formatter applied

### Pattern Consistency

- [ ] Similar problems solved similarly
- [ ] Consistent error handling approach
- [ ] Consistent logging patterns
- [ ] Consistent async patterns
- [ ] Consistent data validation

---

## 10. Maintainability

### Readability

- [ ] Code reads like prose
- [ ] Logic flows naturally
- [ ] No "clever" code
- [ ] Obvious is better than obscure
- [ ] New developers can understand quickly

### Extensibility

- [ ] Easy to add new features
- [ ] Open/Closed Principle followed
- [ ] Abstraction points well-chosen
- [ ] No premature optimization
- [ ] Refactoring is safe (with tests)

### Technical Debt

- [ ] No known bugs ignored
- [ ] TODOs tracked and scheduled
- [ ] Deprecated code marked and removed
- [ ] Dependencies up to date
- [ ] Architecture documented

---

## 11. Language-Specific Best Practices

### TypeScript/JavaScript

- [ ] Strict mode enabled
- [ ] Type safety enforced
- [ ] No `any` types (use `unknown` instead)
- [ ] Async/await over callbacks
- [ ] Const by default, let when needed, no var

### Python

- [ ] PEP 8 style guide followed
- [ ] Type hints used
- [ ] Virtual environments used
- [ ] List/dict comprehensions not overly complex
- [ ] Context managers for resources

### Java/C#

- [ ] Access modifiers appropriate
- [ ] Interfaces over concrete classes
- [ ] Try-with-resources for AutoCloseable
- [ ] Generics used appropriately
- [ ] Null safety patterns (Optional, nullable types)

---

## 12. Version Control

### Commit Quality

- [ ] Atomic commits (one logical change)
- [ ] Descriptive commit messages
- [ ] No secrets in commits
- [ ] No generated files committed
- [ ] Branch strategy followed

### Code Review

- [ ] Pull requests are focused
- [ ] PR descriptions explain changes
- [ ] Tests included with changes
- [ ] Breaking changes documented
- [ ] Reviewer feedback addressed

---

## Quick Quality Score

Rate each category 0-10, average for overall score:

| Category | Score |
|----------|-------|
| Naming | /10 |
| Function Design | /10 |
| Error Handling | /10 |
| Organization | /10 |
| Documentation | /10 |
| Testing | /10 |
| Performance | /10 |
| Security | /10 |
| Consistency | /10 |
| Maintainability | /10 |
| **TOTAL** | **/100** |

---

## Priority Levels

When issues are found, fix in this order:

1. **CRITICAL**: Security vulnerabilities, data corruption risks
2. **HIGH**: SOLID violations, major bugs, no error handling
3. **MEDIUM**: Code smells, missing tests, poor naming
4. **LOW**: Style inconsistencies, minor optimizations

---

## Automated Tools

Complement this manual checklist with:

- **Linters**: ESLint, Pylint, RuboCop, Checkstyle
- **Formatters**: Prettier, Black, gofmt
- **Security**: Snyk, Dependabot, SonarQube
- **Coverage**: Jest, pytest-cov, JaCoCo
- **Static Analysis**: SonarQube, CodeClimate, Codacy

---

Remember: This checklist is a guide, not a strict rulebook. Apply pragmatically based on project needs, team experience, and time constraints.
