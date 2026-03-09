# Bad Code Patterns Examples

Examples of code that violates SOLID, KISS, and industry best practices.

⚠️ **DO NOT USE THESE PATTERNS** - These are examples of what to avoid!

---

## Violating Single Responsibility Principle

### ❌ BAD: God Object

```typescript
class UserManager {
  // Database operations
  async saveToDatabase(user: User) {
    const connection = await this.connectToMySQL();
    const query = `INSERT INTO users VALUES (${user.id}, '${user.email}')`;
    await connection.execute(query);
  }
  
  // Email operations
  async sendWelcomeEmail(user: User) {
    const smtp = this.setupSMTP();
    await smtp.send({
      to: user.email,
      subject: 'Welcome!',
      body: this.generateEmailBody(user)
    });
  }
  
  // Validation
  validateUser(user: User): boolean {
    if (!user.email.includes('@')) return false;
    if (user.age < 18) return false;
    if (!this.checkEmailDomain(user.email)) return false;
    return true;
  }
  
  // Reporting
  generateUserReport(userId: string): Report {
    const user = this.getUserById(userId);
    const stats = this.calculateStats(user);
    return this.formatReport(stats);
  }
  
  // Logging
  logActivity(userId: string, action: string) {
    const timestamp = new Date();
    this.writeToLog(`${timestamp}: User ${userId} ${action}`);
  }
  
  // Image processing
  compressAvatar(imageData: Buffer): Buffer {
    return this.imageCompressor.compress(imageData);
  }
  
  // ... 30 more methods
}
```

**Problems**:
- One class doing 6+ different things
- Changes to email affect database code
- Impossible to test in isolation
- Nightmare to maintain

---

## Violating Open/Closed Principle

### ❌ BAD: Type Switching

```typescript
class PaymentProcessor {
  processPayment(paymentType: string, amount: number): void {
    if (paymentType === 'credit_card') {
      // Credit card processing
      this.validateCreditCard();
      this.chargeCreditCard(amount);
      this.recordCreditCardTransaction();
    } else if (paymentType === 'paypal') {
      // PayPal processing
      this.validatePayPalAccount();
      this.chargePayPal(amount);
      this.recordPayPalTransaction();
    } else if (paymentType === 'crypto') {
      // Crypto processing
      this.validateWallet();
      this.transferCrypto(amount);
      this.recordCryptoTransaction();
    } else if (paymentType === 'bank_transfer') {
      // Bank transfer - NEW! Must modify this class
      this.validateBankAccount();
      this.initiateBankTransfer(amount);
      this.recordBankTransfer();
    }
    // Adding new payment method = modifying this class!
  }
}
```

**Problems**:
- Every new payment type requires modifying this class
- Cannot add new behavior without changing existing code
- Growing if/else chain
- High risk of breaking existing functionality

---

## Violating Liskov Substitution Principle

### ❌ BAD: Square/Rectangle Problem

```typescript
class Rectangle {
  constructor(protected width: number, protected height: number) {}
  
  setWidth(width: number): void {
    this.width = width;
  }
  
  setHeight(height: number): void {
    this.height = height;
  }
  
  getArea(): number {
    return this.width * this.height;
  }
}

class Square extends Rectangle {
  setWidth(width: number): void {
    // Violates LSP - changes behavior!
    this.width = width;
    this.height = width; // Side effect!
  }
  
  setHeight(height: number): void {
    // Violates LSP - changes behavior!
    this.width = height; // Side effect!
    this.height = height;
  }
}

// This breaks when using Square!
function testRectangle(rect: Rectangle) {
  rect.setWidth(5);
  rect.setHeight(10);
  console.log(rect.getArea()); // Expects 50
  // Square will return 100! Broken substitutability.
}
```

**Problems**:
- Square cannot substitute Rectangle
- Unexpected behavior changes
- Violates parent's contract

---

## Violating Interface Segregation Principle

### ❌ BAD: Bloated Interface

```typescript
interface IWorker {
  work(): void;
  eat(): void;
  sleep(): void;
  getSalary(): number;
  takeBreak(): void;
  attendMeeting(): void;
  writeCode(): void;
  designSystem(): void;
  testCode(): void;
  deployCode(): void;
  reviewCode(): void;
  documentCode(): void;
}

// Robot worker doesn't eat or sleep!
class RobotWorker implements IWorker {
  work(): void { /* robots work */ }
  
  eat(): void {
    throw new Error("Robots don't eat!"); // Forced to implement
  }
  
  sleep(): void {
    throw new Error("Robots don't sleep!"); // Forced to implement
  }
  
  getSalary(): number {
    throw new Error("Robots don't get salaries!"); // Forced to implement
  }
  
  // ... forced to implement 8 more methods
}
```

**Problems**:
- Clients forced to implement methods they don't use
- Throws NotImplementedException everywhere
- Interface is too broad

---

## Violating Dependency Inversion Principle

### ❌ BAD: Hard-Coded Dependencies

```typescript
class UserService {
  async createUser(userData: any) {
    // Hard-coded dependency!
    const db = new MySQLDatabase('localhost', 'root', 'password123');
    await db.connect();
    await db.insert('users', userData);
    
    // Hard-coded dependency!
    const emailer = new SMTPEmailer('smtp.gmail.com', 587);
    await emailer.send(userData.email, 'Welcome!');
    
    // Hard-coded dependency!
    const logger = new FileLogger('/var/log/app.log');
    logger.log(`User created: ${userData.id}`);
  }
}
```

**Problems**:
- Cannot test without real database
- Cannot swap implementations
- High-level module depends on low-level details
- Configuration hard-coded

---

## Violating KISS Principle

### ❌ BAD: Over-Engineering

```typescript
// Over-complicated for a simple task
abstract class AbstractDataTransformationStrategyFactory {
  abstract createStrategy(): IDataTransformationStrategy;
}

interface IDataTransformationStrategy {
  transform(data: any): any;
}

class ConcreteDataTransformationStrategyFactoryImpl 
  extends AbstractDataTransformationStrategyFactory {
  
  createStrategy(): IDataTransformationStrategy {
    return new UserDataTransformationStrategyImpl();
  }
}

class UserDataTransformationStrategyImpl 
  implements IDataTransformationStrategy {
  
  transform(data: any): any {
    return { fullName: `${data.firstName} ${data.lastName}` };
  }
}

// Usage requires 50 lines of boilerplate
const factory = new ConcreteDataTransformationStrategyFactoryImpl();
const strategy = factory.createStrategy();
const result = strategy.transform(user);

// Should have been:
const fullName = `${user.firstName} ${user.lastName}`;
```

**Problems**:
- Unnecessary abstractions
- Over-engineered for simple task
- 50+ lines for one-line transformation
- Hard to understand

---

## Bad Error Handling

### ❌ BAD: Swallowing Errors

```typescript
async function processPayment(userId: string, amount: number) {
  try {
    await chargeUser(userId, amount);
  } catch (error) {
    // Silent failure - user charged but no error shown!
  }
  
  try {
    await sendReceipt(userId);
  } catch (error) {
    console.log('Oops'); // User has no idea what happened
  }
  
  try {
    await updateInventory();
  } catch (error) {
    // Just log and continue? Inventory now wrong!
    logger.error(error);
  }
}
```

**Problems**:
- Silent failures on critical operations
- User has no feedback
- Data inconsistency
- Impossible to debug

---

## Bad Function Design

### ❌ BAD: Doing Too Much

```typescript
function processOrder(
  orderId: string,
  userId: string,
  items: Item[],
  paymentMethod: string,
  shippingAddress: Address,
  billingAddress: Address,
  giftWrap: boolean,
  giftMessage: string,
  promoCode: string,
  affiliateId: string
) {
  // 200 lines doing:
  // - Validate order
  // - Check inventory
  // - Calculate pricing
  // - Apply discounts
  // - Process payment
  // - Update inventory
  // - Send confirmation email
  // - Update analytics
  // - Process affiliate commission
  // - Schedule shipping
  // - Generate invoice
  // - Log everything
  
  // ... massive function
}
```

**Problems**:
- Function does 12+ different things
- 10 parameters (unmanageable)
- 200+ lines (scrolling required)
- Impossible to test properly
- Violates SRP

---

## Magic Numbers and Strings

### ❌ BAD: Unexplained Literals

```typescript
function processUser(user: any) {
  if (user.status === 3) {  // What is 3?
    setTimeout(() => {
      sendEmail(user.email, "noreply@company.com");  // Why this email?
    }, 86400000);  // What is this number?
    
    if (user.score > 500) {  // Why 500?
      user.level = 2;  // What does 2 mean?
    }
  }
}
```

**Problems**:
- No explanation of what values mean
- Changes require finding all occurrences
- Error-prone
- Hard to maintain

---

## Copy-Paste Programming

### ❌ BAD: Duplicated Code

```typescript
function processUserOrder(order: Order) {
  if (!order.items || order.items.length === 0) {
    throw new Error("No items in order");
  }
  if (!order.userId) {
    throw new Error("No user ID");
  }
  const total = order.items.reduce((sum, item) => sum + item.price, 0);
  const tax = total * 0.08;
  const shipping = 5.99;
  return total + tax + shipping;
}

function processGuestOrder(order: Order) {
  if (!order.items || order.items.length === 0) {  // Duplicated!
    throw new Error("No items in order");
  }
  if (!order.guestEmail) {  // Slightly different
    throw new Error("No guest email");
  }
  const total = order.items.reduce((sum, item) => sum + item.price, 0);  // Duplicated!
  const tax = total * 0.08;  // Duplicated!
  const shipping = 5.99;  // Duplicated!
  return total + tax + shipping;  // Duplicated!
}

function processAdminOrder(order: Order) {
  // Same code again for admin...
}
```

**Problems**:
- Same code in multiple places
- Bug fixes need to be applied everywhere
- Inconsistent behavior when one copy changes

---

## Callback Hell

### ❌ BAD: Deeply Nested Callbacks

```javascript
function getUserData(userId, callback) {
  database.findUser(userId, function(err, user) {
    if (err) {
      callback(err);
    } else {
      database.getUserPosts(user.id, function(err, posts) {
        if (err) {
          callback(err);
        } else {
          database.getUserComments(user.id, function(err, comments) {
            if (err) {
              callback(err);
            } else {
              api.getExternalData(user.id, function(err, external) {
                if (err) {
                  callback(err);
                } else {
                  callback(null, {
                    user,
                    posts,
                    comments,
                    external
                  });
                }
              });
            }
          });
        }
      });
    }
  });
}
```

**Problems**:
- Pyramid of doom
- Error handling duplicated
- Hard to follow flow
- Difficult to refactor

---

## Security Vulnerabilities

### ❌ BAD: SQL Injection

```typescript
async function getUser(email: string) {
  // CRITICAL SECURITY VULNERABILITY!
  const query = `SELECT * FROM users WHERE email = '${email}'`;
  return await db.query(query);
  // Attacker can inject: email = "' OR '1'='1"
}
```

### ❌ BAD: Hardcoded Secrets

```typescript
const config = {
  database: {
    host: 'prod-db.company.com',
    user: 'admin',
    password: 'SuperSecret123',  // SECURITY BREACH!
    port: 3306
  },
  apiKeys: {
    stripe: 'sk_live_abc123xyz',  // EXPOSED!
    aws: 'AKIA123456789',  // IN VERSION CONTROL!
  }
};
```

**Problems**:
- Credentials exposed in code
- In version control history forever
- Cannot rotate secrets
- Compliance violations

---

## Poor Naming

### ❌ BAD: Unclear Names

```typescript
function doIt(x: any, y: any, z: boolean) {
  const temp = x.filter(item => item.val > y);
  const res = z ? temp.map(t => t.id) : temp;
  return res;
}

class Manager {
  handleStuff(data: any) {
    // What does this manage? What stuff?
  }
}

const flg = true;  // What flag?
const usr = getUsr();  // Why abbreviate?
const d = new Date();  // Single letter
```

**Problems**:
- No idea what code does without reading it
- Generic names provide no information
- Unnecessary abbreviations

---

## God Function

### ❌ BAD: Function That Does Everything

```typescript
async function handleUserRegistration(req: any, res: any) {
  // 500+ lines doing:
  
  // Parse request
  const data = req.body;
  
  // Validate (50 lines)
  if (!data.email) { /* ... */ }
  // ... 40 more validations
  
  // Check duplicates (30 lines)
  const existing = await db.query(/* ... */);
  if (existing) { /* ... */ }
  
  // Create user (40 lines)
  const userId = generateId();
  const hashedPw = await hash(data.password);
  // ...
  
  // Send email (60 lines)
  const emailTemplate = fs.readFileSync(/* ... */);
  const smtp = createSMTP(/* ... */);
  // ...
  
  // Update analytics (50 lines)
  await analytics.track(/* ... */);
  // ...
  
  // Create trial subscription (70 lines)
  const stripe = require('stripe')(/* ... */);
  // ...
  
  // Send welcome SMS (40 lines)
  const twilio = require('twilio')(/* ... */);
  // ...
  
  // Log everything (30 lines)
  logger.info(/* massive object */);
  
  // Return response (20 lines)
  res.json({ /* ... */ });
}
```

**Problems**:
- 500+ lines in one function
- Does 8+ different things
- Impossible to test
- Cannot reuse parts
- Nightmare to maintain

---

## Testing Anti-Patterns

### ❌ BAD: Testing Implementation Details

```typescript
describe('UserService', () => {
  it('should use the correct internal cache structure', () => {
    const service = new UserService();
    service.addUser({ id: '1', name: 'John' });
    
    // Testing internal implementation!
    expect(service.internalCache.size).toBe(1);
    expect(service.internalCache.get('1')).toBeDefined();
    expect(service.cacheMetadata.lastUpdated).toBeDefined();
  });
});
```

**Problems**:
- Tests know too much about internals
- Cannot refactor without breaking tests
- Tests don't test behavior, test structure

---

## Remember: These are BAD Patterns!

All of these examples demonstrate:
- ❌ Multiple responsibilities
- ❌ Hard-coded dependencies
- ❌ No error handling
- ❌ Over-complicated solutions
- ❌ Security vulnerabilities
- ❌ Unclear code
- ❌ Tight coupling
- ❌ Difficult to test

**Always refer to the good-patterns.md file for how to do it correctly!**
