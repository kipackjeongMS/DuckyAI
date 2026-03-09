# Code Anti-Patterns Catalog

## What are Anti-Patterns?

Anti-patterns are common solutions to recurring problems that are ineffective and counterproductive. They represent what NOT to do.

---

## Organizational Anti-Patterns

### 1. God Object / God Class

**Description**: A class that knows too much or does too much.

**Symptoms**:
- Class has 1000+ lines
- Class name contains "Manager", "Controller", "Handler", "Utility", "Helper"
- Class has 20+ methods
- Every other class depends on it
- Difficult to test in isolation

**Example**:
```typescript
class UserManager {
  validateUser() { }
  saveUserToDatabase() { }
  sendWelcomeEmail() { }
  generateUserReport() { }
  logUserActivity() { }
  compressUserAvatar() { }
  calculateUserStatistics() { }
  // ... 50 more methods
}
```

**Impact**: CRITICAL
- Violates Single Responsibility Principle
- High coupling, low cohesion
- Extremely difficult to maintain
- Impossible to test properly

**Fix**:
```typescript
class UserValidator { }
class UserRepository { }
class EmailService { }
class UserReportGenerator { }
class ActivityLogger { }
class ImageProcessor { }
class StatisticsCalculator { }
```

---

### 2. Spaghetti Code

**Description**: Code with complex and tangled control flow, often with GOTO-like logic or excessive interdependencies.

**Symptoms**:
- Difficult to follow execution flow
- No clear separation of concerns
- Global state everywhere
- Functions call each other in circular patterns
- Cannot understand code without reading entire system

**Example**:
```javascript
function processData(data) {
  var result;
  if (data.type == 'A') {
    result = handleTypeA(data);
    if (result.status) {
      updateGlobalState(result);
      if (globalState.ready) {
        processDataAgain(modifyData(data));
      }
    }
  } else {
    // ... nested maze continues
  }
}
```

**Impact**: HIGH
- Unmaintainable
- Bugs cascade through system
- Cannot refactor safely

**Fix**:
- Apply Single Responsibility Principle
- Use clear, linear flow
- Eliminate global state
- Break into small, focused functions

---

### 3. Lava Flow

**Description**: Dead code and obsolete features left in the codebase because removal is risky.

**Symptoms**:
- Comments like "Don't touch this, not sure what it does"
- Unused imports/dependencies
- Feature flags that never get removed
- Functions that are never called
- "Legacy" modules that are frozen

**Example**:
```typescript
// Legacy user system - DO NOT MODIFY
// We think this is still used somewhere but not sure
class OldUserService {
  // Last modified: 2015
}
```

**Impact**: MEDIUM
- Increases cognitive load
- Wastes compilation/build time
- False sense of purpose
- Fear-based development

**Fix**:
- Use static analysis to find dead code
- Write tests before removal
- Remove incrementally with feature flags
- Version control is your safety net

---

### 4. Copy-Paste Programming

**Description**: Duplicating code instead of creating reusable abstractions.

**Symptoms**:
- Same code block appears in multiple places
- Bug fixes require changes in 10+ locations
- Inconsistent behavior in "same" functionality
- Comments like "same as above but for X"

**Example**:
```typescript
function processUserOrder(order) {
  if (!order.items || order.items.length === 0) {
    throw new Error("No items");
  }
  // ... 50 lines of processing
}

function processAdminOrder(order) {
  if (!order.items || order.items.length === 0) {
    throw new Error("No items");
  }
  // ... same 50 lines of processing
}
```

**Impact**: HIGH
- Violates DRY principle
- Maintenance nightmare
- Inconsistent bug fixes

**Fix**:
```typescript
function validateOrder(order) {
  if (!order.items || order.items.length === 0) {
    throw new Error("No items");
  }
}

function processOrderCore(order) {
  validateOrder(order);
  // ... processing logic once
}
```

---

### 5. Magic Numbers and Strings

**Description**: Using literal values directly in code without explanation.

**Symptoms**:
- Hardcoded numbers/strings scattered everywhere
- No explanation of what values mean
- Same value appears multiple times
- Changes require finding all occurrences

**Example**:
```typescript
if (user.status === 3) { // What is 3?
  sendEmail(user.email, "noreply@example.com"); // Why this email?
  setTimeout(processUser, 86400000); // What is this delay?
}
```

**Impact**: MEDIUM
- Hard to understand
- Error-prone when changing values
- No single source of truth

**Fix**:
```typescript
const UserStatus = {
  ACTIVE: 3,
  SUSPENDED: 2,
  DELETED: 1
};

const EMAIL_CONFIG = {
  NOREPLY: "noreply@example.com"
};

const TIME_CONSTANTS = {
  ONE_DAY_MS: 24 * 60 * 60 * 1000
};

if (user.status === UserStatus.ACTIVE) {
  sendEmail(user.email, EMAIL_CONFIG.NOREPLY);
  setTimeout(processUser, TIME_CONSTANTS.ONE_DAY_MS);
}
```

---

## Design Anti-Patterns

### 6. Premature Optimization

**Description**: Optimizing code before knowing if it's necessary.

**Symptoms**:
- Complex code for theoretical performance gains
- Optimizing code that runs rarely
- Sacrificing readability for speed without benchmarks
- Implementing caching without measuring need

**Example**:
```typescript
// Over-optimized for a function called once per hour
const memoizedCache = new Map();
function calculateUserScore(userId) {
  if (memoizedCache.has(userId)) {
    return memoizedCache.get(userId);
  }
  // ... complex caching logic for no reason
}
```

**Impact**: MEDIUM
- Violates KISS principle
- Code is harder to maintain
- Actual bottlenecks remain unfixed

**Fix**:
1. Write simple, correct code first
2. Profile to find actual bottlenecks
3. Optimize only proven hot paths
4. Measure before and after

---

### 7. Cargo Cult Programming

**Description**: Using patterns, practices, or code without understanding why.

**Symptoms**:
- "We always do it this way"
- Copy-pasting patterns from tutorials
- Using frameworks/libraries without understanding
- Blindly following best practices

**Example**:
```typescript
// Using Singleton pattern because "it's a best practice"
// without understanding if it's needed
class DatabaseConnection {
  private static instance: DatabaseConnection;
  
  private constructor() { }
  
  static getInstance() {
    if (!DatabaseConnection.instance) {
      DatabaseConnection.instance = new DatabaseConnection();
    }
    return DatabaseConnection.instance;
  }
}
// Actually just needed a regular dependency injection
```

**Impact**: MEDIUM
- Over-engineering
- Inappropriate patterns
- Technical debt accumulation

**Fix**:
- Understand WHY before using patterns
- Question "best practices" in your context
- Start simple, add patterns when needed

---

### 8. Golden Hammer

**Description**: Using the same solution/technology for every problem.

**Symptoms**:
- "Let's use microservices for everything"
- "This needs blockchain"
- Using same design pattern regardless of problem
- Forcing familiar tool for inappropriate tasks

**Example**:
```typescript
// Using Redis for everything, even config files
const config = await redis.get('app-config');
const userPreferences = await redis.get('user-prefs');
const staticContent = await redis.get('static-html');
// When file system or environment variables would work better
```

**Impact**: MEDIUM
- Inappropriate solutions
- Overcomplicated architecture
- Poor performance

**Fix**:
- Evaluate each problem independently
- Learn multiple tools/patterns
- Choose right tool for the job

---

## Implementation Anti-Patterns

### 9. Hard-Coded Dependencies

**Description**: Creating dependencies directly instead of injecting them.

**Symptoms**:
- `new` keyword everywhere
- Cannot test without real dependencies
- Tightly coupled components
- Cannot swap implementations

**Example**:
```typescript
class UserService {
  private db = new MySQLDatabase(); // Hard-coded!
  private emailer = new SMTPEmailer(); // Hard-coded!
  
  async createUser(user: User) {
    await this.db.save(user);
    await this.emailer.send(user.email, "Welcome");
  }
}
```

**Impact**: HIGH
- Violates Dependency Inversion Principle
- Impossible to test in isolation
- Cannot change implementations

**Fix**:
```typescript
interface Database {
  save(user: User): Promise<void>;
}

interface Emailer {
  send(to: string, message: string): Promise<void>;
}

class UserService {
  constructor(
    private db: Database,
    private emailer: Emailer
  ) { }
  
  async createUser(user: User) {
    await this.db.save(user);
    await this.emailer.send(user.email, "Welcome");
  }
}
```

---

### 10. Error Swallowing

**Description**: Catching errors and doing nothing with them.

**Symptoms**:
- Empty catch blocks
- Catching generic Exception
- Logging errors but not handling
- Try-catch around everything "just in case"

**Example**:
```typescript
try {
  await criticalDatabaseOperation();
} catch (error) {
  // Silent failure - user has no idea something broke
}

try {
  await sendPayment();
} catch (error) {
  console.log("Oops"); // Payment failed, but we just log?
}
```

**Impact**: CRITICAL
- Silent failures
- Data corruption
- Impossible to debug
- User frustration

**Fix**:
```typescript
try {
  await criticalDatabaseOperation();
} catch (error) {
  logger.error("Database operation failed", { error, context });
  throw new DatabaseError("Failed to save user data", { cause: error });
}

try {
  await sendPayment();
} catch (error) {
  await rollbackTransaction();
  notifyAdmin(error);
  throw new PaymentError("Payment processing failed", { cause: error });
}
```

---

### 11. Callback Hell / Pyramid of Doom

**Description**: Deeply nested callbacks making code unreadable.

**Symptoms**:
- Code indented 6+ levels
- Closing braces form a pyramid
- Hard to follow execution flow
- Error handling duplicated at each level

**Example**:
```javascript
getData(function(a) {
  getMoreData(a, function(b) {
    getMoreData(b, function(c) {
      getMoreData(c, function(d) {
        getMoreData(d, function(e) {
          // Finally do something
        });
      });
    });
  });
});
```

**Impact**: HIGH
- Unreadable code
- Error handling nightmare
- Cannot test properly

**Fix**:
```javascript
// Use async/await
const a = await getData();
const b = await getMoreData(a);
const c = await getMoreData(b);
const d = await getMoreData(c);
const e = await getMoreData(d);
// Do something

// Or use Promise chaining
getData()
  .then(getMoreData)
  .then(getMoreData)
  .then(getMoreData)
  .then(getMoreData)
  .catch(handleError);
```

---

### 12. Poltergeist / Big Ball of Mud

**Description**: Classes that have very limited roles and lifecycle, often used to invoke other components.

**Symptoms**:
- Classes with only one or two methods
- Classes that exist just to call other classes
- Unnecessary indirection layers
- Classes with no state

**Example**:
```typescript
class UserCreatorHelper {
  create(user: User) {
    return new UserService().createUser(user);
  }
}
// This class adds no value, just indirection
```

**Impact**: LOW to MEDIUM
- Unnecessary complexity
- Harder to navigate code
- False sense of separation

**Fix**:
- Remove unnecessary wrapper
- Use functions instead of classes
- Only create abstractions when they add value

---

## Testing Anti-Patterns

### 13. Testing Implementation Details

**Description**: Tests that know too much about how code works internally.

**Example**:
```typescript
// Bad: Testing internal state
expect(service.internalCache.size).toBe(5);
expect(service.privateMethod()).toBe(true);

// Good: Testing behavior
const result = await service.getUsers();
expect(result.length).toBe(5);
```

**Impact**: HIGH
- Brittle tests that break with refactoring
- Cannot change implementation

---

### 14. Test Code Duplication

**Description**: Repeating setup/teardown code in every test.

**Fix**:
- Use beforeEach/beforeAll hooks
- Create test helpers
- Use factory functions for test data

---

## Security Anti-Patterns

### 15. SQL Injection Vulnerability

**Description**: Building SQL queries with string concatenation.

**Example**:
```typescript
// CRITICAL VULNERABILITY
const query = `SELECT * FROM users WHERE email = '${userInput}'`;
```

**Impact**: CRITICAL
- Data breach risk
- Data loss risk
- System compromise

**Fix**:
```typescript
const query = 'SELECT * FROM users WHERE email = ?';
await db.query(query, [userInput]);
```

---

### 16. Hardcoded Secrets

**Description**: Storing passwords, API keys, tokens in source code.

**Example**:
```typescript
const API_KEY = "sk_live_abc123"; // CRITICAL SECURITY ISSUE
const DB_PASSWORD = "admin123";
```

**Impact**: CRITICAL
- Credentials in version control
- Exposed in compiled code
- Cannot rotate secrets

**Fix**:
```typescript
const API_KEY = process.env.API_KEY;
const DB_PASSWORD = process.env.DB_PASSWORD;
```

---

## Detection Checklist

When reviewing code, look for:

- [ ] Classes with >500 lines
- [ ] Functions with >50 lines
- [ ] Nesting depth >4 levels
- [ ] Duplicate code blocks
- [ ] Hard-coded values
- [ ] Empty catch blocks
- [ ] Classes ending in "Manager", "Helper", "Utility"
- [ ] Direct instantiation of dependencies
- [ ] Complex conditional logic
- [ ] Missing error handling
- [ ] Unclear variable names
- [ ] No tests

---

## Priority Matrix

| Anti-Pattern | Severity | Effort to Fix | Priority |
|--------------|----------|---------------|----------|
| SQL Injection | CRITICAL | LOW | FIX NOW |
| Hardcoded Secrets | CRITICAL | LOW | FIX NOW |
| Error Swallowing | CRITICAL | MEDIUM | HIGH |
| God Object | HIGH | HIGH | HIGH |
| Hard-Coded Dependencies | HIGH | MEDIUM | HIGH |
| Spaghetti Code | HIGH | HIGH | MEDIUM |
| Copy-Paste Programming | MEDIUM | LOW | MEDIUM |
| Magic Numbers | MEDIUM | LOW | MEDIUM |
| Premature Optimization | MEDIUM | MEDIUM | LOW |
| Poltergeist | LOW | LOW | LOW |
