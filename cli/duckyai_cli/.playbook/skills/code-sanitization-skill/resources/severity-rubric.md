# Severity Classification Rubric

This rubric helps classify code issues by severity to prioritize fixes effectively.

---

## Severity Levels

| Level | Time to Fix | Business Impact | User Impact | Technical Impact |
|-------|-------------|-----------------|-------------|------------------|
| CRITICAL | Immediate | High | Severe | Breaking |
| HIGH | 1-3 days | Medium-High | Moderate | Significant |
| MEDIUM | 1-2 weeks | Low-Medium | Minor | Noticeable |
| LOW | Backlog | Minimal | None | Negligible |

---

## CRITICAL Severity

**Fix Immediately** - Drop everything else

### Security Vulnerabilities

- SQL injection vulnerabilities
- XSS (Cross-Site Scripting) vulnerabilities
- Authentication bypass
- Hardcoded secrets/credentials in code
- Unencrypted sensitive data transmission
- Remote code execution risks
- Unsafe deserialization

**Example**:
```typescript
❌ CRITICAL
const query = `SELECT * FROM users WHERE id = ${userId}`;
// Direct SQL injection - fix immediately
```

### Data Integrity Risks

- Data loss scenarios
- Data corruption bugs
- Race conditions in financial transactions
- Missing transaction rollback
- Concurrent access without synchronization

**Example**:
```typescript
❌ CRITICAL
async function transferMoney(from, to, amount) {
  await debit(from, amount);  // If this succeeds...
  await credit(to, amount);   // ...but this fails, money is lost!
}
```

### System Stability

- Null pointer/reference crashes
- Infinite loops in production code
- Memory leaks in critical paths
- Unhandled exceptions that crash system
- Deadlock scenarios

**Example**:
```typescript
❌ CRITICAL
function processAll() {
  while (true) {  // Infinite loop!
    processNext();
  }
}
```

### Compliance Violations

- GDPR violations (improper data handling)
- PCI-DSS violations (credit card data)
- HIPAA violations (health data)
- Accessibility violations (WCAG)

---

## HIGH Severity

**Fix within 1-3 days** - Next sprint priority

### Major Design Flaws

- God Object (single class doing everything)
- Tight coupling preventing testing
- Hard-coded dependencies
- Circular dependencies
- No separation of concerns

**Example**:
```typescript
❌ HIGH
class UserManager {
  // 50+ methods, 2000+ lines
  // Handles: validation, database, email, logging, reporting
  // Violates Single Responsibility Principle
}
```

### SOLID Principle Violations (Major)

- Complete violation of Single Responsibility
- High-level modules depending on low-level details
- Subclasses that can't substitute parent
- Bloated interfaces forcing unused methods

### Error Handling Issues

- Empty catch blocks on critical operations
- Swallowing errors without logging
- No error handling on async operations
- Generic exception catching everywhere

**Example**:
```typescript
❌ HIGH
try {
  await processPayment(user, amount);
} catch (error) {
  // Silent failure on payment - user charged but no confirmation!
}
```

### Performance Problems (Proven)

- N+1 query problems
- Missing database indexes on high-traffic queries
- Inefficient algorithms (O(n²) when O(n) exists)
- Memory leaks with profiling evidence
- Synchronous blocking in async contexts

**Example**:
```typescript
❌ HIGH
async function loadUserData() {
  const users = await getUsers(); // 1 query
  for (const user of users) {
    user.posts = await getPosts(user.id); // N queries
  }
}
```

### Missing Critical Tests

- No tests for payment processing
- No tests for authentication/authorization
- Critical business logic untested
- No integration tests for key flows

---

## MEDIUM Severity

**Fix within 1-2 weeks** - Include in upcoming sprint

### Code Smells

- Functions over 50 lines
- Classes over 500 lines
- Cyclomatic complexity over 10
- Duplicated code blocks
- Deep nesting (5+ levels)

**Example**:
```typescript
❌ MEDIUM
function calculatePrice(item, user, config, seasonal) {
  if (user.isPremium) {
    if (seasonal.isActive) {
      if (item.category === 'electronics') {
        if (config.discountEnabled) {
          // 5 levels deep - hard to follow
        }
      }
    }
  }
}
```

### Minor SOLID Violations

- Single class with 2-3 responsibilities (not 10+)
- Some tight coupling but testable
- Minor interface bloat
- Occasional concrete dependency

### Poor Naming

- Unclear variable names
- Generic function names (doStuff, handle, process)
- Inconsistent naming patterns
- Misleading names

**Example**:
```typescript
❌ MEDIUM
function process(data, flag, x) {  // What does this do?
  const temp = x ? data.filter(f) : data;
  return temp.map(t => t.value);
}
```

### Missing Non-Critical Tests

- Happy path tested but edge cases missing
- Error conditions not tested
- Missing unit tests (integration tests exist)
- Low test coverage (<60%)

### Technical Debt

- Deprecated API usage (still works)
- Outdated dependencies (no security issues)
- TODO comments accumulating
- Workarounds that should be proper fixes

### Documentation Gaps

- Missing API documentation
- No README for module
- Complex logic without explanation
- Outdated comments

---

## LOW Severity

**Backlog / Nice to have** - Fix when time permits

### Style Inconsistencies

- Inconsistent indentation
- Mixed quote styles
- Inconsistent brace placement
- Formatting not matching linter

**Example**:
```typescript
❌ LOW
function foo() {
    const x = "test";  // 4 spaces
  const y = 'test';    // 2 spaces, different quotes
    }                  // Inconsistent brace
```

### Minor Optimizations

- Could use const instead of let
- Redundant else after return
- Could use array methods instead of loops
- Minor memory allocation improvements

**Example**:
```typescript
❌ LOW
function isEven(num) {
  if (num % 2 === 0) {
    return true;
  } else {  // Redundant else
    return false;
  }
}

✅ Better
function isEven(num) {
  return num % 2 === 0;
}
```

### Cosmetic Issues

- Extra whitespace
- Trailing commas inconsistency
- Comment formatting
- Import ordering

### Potential Future Concerns

- Code might be hard to extend (but no current need)
- Potential scalability concern (but not at current scale)
- Could be more DRY (but only 2 occurrences)

---

## Decision Matrix

Use this flowchart to classify issues:

```
Does it affect security or data integrity?
  └─ YES → CRITICAL

Is it in production and causing failures?
  └─ YES → CRITICAL

Does it violate major design principles?
  └─ YES → HIGH

Does it prevent testing or maintenance?
  └─ YES → HIGH

Is it a code smell or moderate duplication?
  └─ YES → MEDIUM

Is it missing tests for non-critical features?
  └─ YES → MEDIUM

Is it a style/formatting issue?
  └─ YES → LOW

Is it a potential future concern?
  └─ YES → LOW
```

---

## Impact Assessment

Consider these dimensions when classifying:

### 1. User Impact
- **CRITICAL**: Users cannot complete core functions, data loss
- **HIGH**: Degraded experience, workarounds needed
- **MEDIUM**: Minor inconvenience, cosmetic issues
- **LOW**: No user-facing impact

### 2. Business Impact
- **CRITICAL**: Revenue loss, legal liability, reputation damage
- **HIGH**: Delayed features, increased costs
- **MEDIUM**: Slightly slower development
- **LOW**: No business impact

### 3. Technical Impact
- **CRITICAL**: System crashes, data corruption
- **HIGH**: Cannot add features, testing impossible
- **MEDIUM**: Slower development, harder to understand
- **LOW**: Minor inefficiency

### 4. Frequency
- **CRITICAL**: Affects every request/user
- **HIGH**: Affects common workflows
- **MEDIUM**: Affects occasional scenarios
- **LOW**: Rare edge case

---

## Example Classifications

### Authentication Bypass
- **Severity**: CRITICAL
- **Reason**: Security vulnerability, all users affected
- **Action**: Fix immediately

### God Object with 2000 lines
- **Severity**: HIGH
- **Reason**: Major design flaw, prevents testing
- **Action**: Refactor in next sprint

### Duplicated 50-line code block
- **Severity**: MEDIUM
- **Reason**: Code smell, maintenance burden
- **Action**: Extract to shared function

### Using `let` instead of `const`
- **Severity**: LOW
- **Reason**: Style issue, no functional impact
- **Action**: Fix when touching code

### Magic number (timeout value)
- **Severity**: MEDIUM
- **Reason**: Hurts maintainability
- **Action**: Extract to constant

### Empty catch block on payment
- **Severity**: CRITICAL
- **Reason**: Silent failure on critical operation
- **Action**: Add error handling immediately

### Function with 7 parameters
- **Severity**: MEDIUM
- **Reason**: Code smell, hard to use
- **Action**: Refactor to use options object

### Missing JSDoc comment
- **Severity**: LOW (public API) or MEDIUM (complex logic)
- **Reason**: Context dependent
- **Action**: Add when time permits

---

## Contextual Adjustments

Severity can change based on context:

### Startup vs Enterprise
- **Startup**: Security still CRITICAL, but some MEDIUM issues can wait
- **Enterprise**: Even LOW issues matter for compliance

### Prototype vs Production
- **Prototype**: Focus on CRITICAL and HIGH only
- **Production**: All severities matter, plan fixes

### Regulated Industry
- **Healthcare/Finance**: Security and compliance issues elevated
- **Non-regulated**: More flexibility on MEDIUM/LOW

### Team Size
- **Small team**: Focus on CRITICAL/HIGH, defer LOW
- **Large team**: Can address all severities in parallel

---

## Severity Escalation

Issues can escalate in severity:

- **LOW → MEDIUM**: When technical debt accumulates
- **MEDIUM → HIGH**: When blocking new features
- **HIGH → CRITICAL**: When found in production affecting users

---

## Reporting Template

When reporting issues, include:

```markdown
## Issue: [Brief Description]

**Severity**: CRITICAL | HIGH | MEDIUM | LOW

**Category**: Security | Design | Performance | Style

**Impact**:
- User Impact: [Description]
- Business Impact: [Description]
- Technical Impact: [Description]

**Location**: [File:Line]

**Current Behavior**: [What's wrong]

**Recommended Fix**: [How to fix]

**Estimated Effort**: [Hours/Days]

**Priority Rank**: [1-10]
```

---

## Remember

- Severity is a guide, not an absolute rule
- Context matters - adjust based on your situation
- When in doubt, classify higher and reassess
- Security issues are always CRITICAL or HIGH
- Fix root causes, not symptoms
