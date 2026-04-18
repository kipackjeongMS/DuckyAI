# Good Code Patterns Examples

Examples of well-written code following SOLID, KISS, and industry best practices.

---

## Single Responsibility Principle (SRP)

### Example: User Management

**Good - Each class has one responsibility**:

```typescript
// Handles ONLY user data persistence
class UserRepository {
  async save(user: User): Promise<void> {
    await this.db.insert('users', user);
  }
  
  async findById(id: string): Promise<User | null> {
    return await this.db.findOne('users', { id });
  }
}

// Handles ONLY user validation
class UserValidator {
  validate(user: User): ValidationResult {
    const errors: string[] = [];
    
    if (!this.isValidEmail(user.email)) {
      errors.push('Invalid email format');
    }
    
    if (user.age < 18) {
      errors.push('User must be 18 or older');
    }
    
    return { isValid: errors.length === 0, errors };
  }
  
  private isValidEmail(email: string): boolean {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }
}

// Handles ONLY welcome email
class WelcomeEmailService {
  async send(user: User): Promise<void> {
    await this.emailClient.send({
      to: user.email,
      subject: 'Welcome!',
      body: this.buildWelcomeMessage(user)
    });
  }
  
  private buildWelcomeMessage(user: User): string {
    return `Welcome ${user.name}! Thanks for joining us.`;
  }
}

// Orchestrates the workflow
class UserRegistrationService {
  constructor(
    private validator: UserValidator,
    private repository: UserRepository,
    private emailService: WelcomeEmailService
  ) {}
  
  async register(user: User): Promise<void> {
    const validation = this.validator.validate(user);
    if (!validation.isValid) {
      throw new ValidationError(validation.errors);
    }
    
    await this.repository.save(user);
    await this.emailService.send(user);
  }
}
```

**Why this is good**:
- Each class can be tested independently
- Changes to email don't affect database code
- Easy to swap implementations
- Clear, focused responsibilities

---

## Open/Closed Principle (OCP)

### Example: Payment Processing

**Good - Open for extension, closed for modification**:

```typescript
// Abstract payment interface
interface PaymentMethod {
  process(amount: number): Promise<PaymentResult>;
  validate(): boolean;
}

// Concrete implementations
class CreditCardPayment implements PaymentMethod {
  constructor(private cardNumber: string, private cvv: string) {}
  
  validate(): boolean {
    return this.cardNumber.length === 16 && this.cvv.length === 3;
  }
  
  async process(amount: number): Promise<PaymentResult> {
    // Credit card processing logic
    return { success: true, transactionId: 'cc-123' };
  }
}

class PayPalPayment implements PaymentMethod {
  constructor(private email: string) {}
  
  validate(): boolean {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.email);
  }
  
  async process(amount: number): Promise<PaymentResult> {
    // PayPal processing logic
    return { success: true, transactionId: 'pp-456' };
  }
}

class CryptoPayment implements PaymentMethod {
  constructor(private walletAddress: string) {}
  
  validate(): boolean {
    return this.walletAddress.startsWith('0x');
  }
  
  async process(amount: number): Promise<PaymentResult> {
    // Crypto processing logic
    return { success: true, transactionId: 'crypto-789' };
  }
}

// Payment processor - NEVER needs modification when adding new payment methods
class PaymentProcessor {
  async processPayment(
    paymentMethod: PaymentMethod,
    amount: number
  ): Promise<PaymentResult> {
    if (!paymentMethod.validate()) {
      throw new Error('Invalid payment method');
    }
    
    return await paymentMethod.process(amount);
  }
}

// Usage - adding new payment method requires ZERO changes to existing code
const processor = new PaymentProcessor();
await processor.processPayment(new CreditCardPayment('1234...', '123'), 100);
await processor.processPayment(new PayPalPayment('user@example.com'), 100);
await processor.processPayment(new CryptoPayment('0x123...'), 100);
```

**Why this is good**:
- Add new payment methods without changing PaymentProcessor
- Each payment method is independently testable
- No risk of breaking existing functionality when extending

---

## Dependency Inversion Principle (DIP)

### Example: Notification System

**Good - Depend on abstractions, not concretions**:

```typescript
// Abstraction
interface NotificationSender {
  send(recipient: string, message: string): Promise<void>;
}

// Low-level implementations
class EmailSender implements NotificationSender {
  async send(recipient: string, message: string): Promise<void> {
    // SMTP email sending
    console.log(`Email to ${recipient}: ${message}`);
  }
}

class SmsSender implements NotificationSender {
  async send(recipient: string, message: string): Promise<void> {
    // SMS API call
    console.log(`SMS to ${recipient}: ${message}`);
  }
}

class PushNotificationSender implements NotificationSender {
  async send(recipient: string, message: string): Promise<void> {
    // Push notification service
    console.log(`Push to ${recipient}: ${message}`);
  }
}

// High-level module depends on abstraction
class NotificationService {
  constructor(private sender: NotificationSender) {}
  
  async notifyUser(userId: string, message: string): Promise<void> {
    const user = await this.getUserContact(userId);
    await this.sender.send(user.contact, message);
  }
  
  private async getUserContact(userId: string): Promise<{ contact: string }> {
    return { contact: 'user@example.com' };
  }
}

// Dependency injection - easily swap implementations
const emailNotifier = new NotificationService(new EmailSender());
const smsNotifier = new NotificationService(new SmsSender());
const pushNotifier = new NotificationService(new PushNotificationSender());

// For testing, inject a mock
class MockSender implements NotificationSender {
  public sentMessages: Array<{ recipient: string; message: string }> = [];
  
  async send(recipient: string, message: string): Promise<void> {
    this.sentMessages.push({ recipient, message });
  }
}

const testNotifier = new NotificationService(new MockSender());
```

**Why this is good**:
- High-level logic doesn't depend on implementation details
- Easy to test with mocks
- Can swap implementations without changing business logic
- Follows dependency injection pattern

---

## KISS Principle

### Example: Data Transformation

**Good - Simple and readable**:

```typescript
interface User {
  firstName: string;
  lastName: string;
  email: string;
  age: number;
}

interface UserDTO {
  fullName: string;
  contact: string;
  isAdult: boolean;
}

// Clear, simple transformation
function transformUserToDTO(user: User): UserDTO {
  return {
    fullName: `${user.firstName} ${user.lastName}`,
    contact: user.email,
    isAdult: user.age >= 18
  };
}

// Simple filtering
function getAdultUsers(users: User[]): User[] {
  return users.filter(user => user.age >= 18);
}

// Simple aggregation
function getAverageAge(users: User[]): number {
  if (users.length === 0) return 0;
  
  const totalAge = users.reduce((sum, user) => sum + user.age, 0);
  return totalAge / users.length;
}
```

**Compare to over-engineered version (DON'T DO THIS)**:

```typescript
// ❌ Over-complicated, trying to be too clever
class UserTransformationStrategy {
  private transformers: Map<string, Function> = new Map();
  
  registerTransformer(key: string, transformer: Function) {
    this.transformers.set(key, transformer);
  }
  
  transform(user: User): any {
    return Array.from(this.transformers.entries()).reduce(
      (acc, [key, transformer]) => ({
        ...acc,
        [key]: transformer(user)
      }), 
      {}
    );
  }
}
// This is overkill for a simple transformation!
```

---

## Proper Error Handling

### Example: User Service

**Good - Comprehensive error handling**:

```typescript
class UserService {
  constructor(
    private repository: UserRepository,
    private logger: Logger
  ) {}
  
  async createUser(userData: CreateUserRequest): Promise<User> {
    try {
      // Validate input
      this.validateUserData(userData);
      
      // Check for existing user
      const existing = await this.repository.findByEmail(userData.email);
      if (existing) {
        throw new UserAlreadyExistsError(
          `User with email ${userData.email} already exists`
        );
      }
      
      // Create user
      const user = await this.repository.save({
        id: generateId(),
        ...userData,
        createdAt: new Date()
      });
      
      this.logger.info('User created successfully', { userId: user.id });
      return user;
      
    } catch (error) {
      // Log error with context
      this.logger.error('Failed to create user', {
        email: userData.email,
        error: error.message,
        stack: error.stack
      });
      
      // Re-throw or wrap in domain-specific error
      if (error instanceof UserAlreadyExistsError) {
        throw error;
      }
      
      throw new UserCreationError(
        'Failed to create user',
        { cause: error }
      );
    }
  }
  
  private validateUserData(data: CreateUserRequest): void {
    if (!data.email) {
      throw new ValidationError('Email is required');
    }
    
    if (!this.isValidEmail(data.email)) {
      throw new ValidationError('Invalid email format');
    }
    
    if (!data.firstName || !data.lastName) {
      throw new ValidationError('First and last name are required');
    }
  }
  
  private isValidEmail(email: string): boolean {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }
}

// Custom error classes for better error handling
class UserCreationError extends Error {
  constructor(message: string, public context?: any) {
    super(message);
    this.name = 'UserCreationError';
  }
}

class UserAlreadyExistsError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'UserAlreadyExistsError';
  }
}

class ValidationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ValidationError';
  }
}
```

**Why this is good**:
- Specific error types for different scenarios
- Errors are logged with context
- Validation fails fast
- Error messages are clear and actionable

---

## Clean Function Design

### Example: Order Processing

**Good - Small, focused functions**:

```typescript
interface Order {
  items: OrderItem[];
  customerId: string;
  shippingAddress: Address;
}

interface OrderItem {
  productId: string;
  quantity: number;
  price: number;
}

class OrderProcessor {
  async processOrder(order: Order): Promise<ProcessedOrder> {
    this.validateOrder(order);
    
    const total = this.calculateTotal(order);
    const tax = this.calculateTax(total, order.shippingAddress);
    const shipping = this.calculateShipping(order);
    
    const finalTotal = total + tax + shipping;
    
    return {
      orderId: generateId(),
      subtotal: total,
      tax,
      shipping,
      total: finalTotal,
      processedAt: new Date()
    };
  }
  
  private validateOrder(order: Order): void {
    if (!order.items || order.items.length === 0) {
      throw new Error('Order must contain at least one item');
    }
    
    if (!order.customerId) {
      throw new Error('Customer ID is required');
    }
    
    if (!order.shippingAddress) {
      throw new Error('Shipping address is required');
    }
  }
  
  private calculateTotal(order: Order): number {
    return order.items.reduce(
      (sum, item) => sum + (item.price * item.quantity),
      0
    );
  }
  
  private calculateTax(subtotal: number, address: Address): number {
    const TAX_RATE = 0.08; // 8%
    return subtotal * TAX_RATE;
  }
  
  private calculateShipping(order: Order): number {
    const SHIPPING_BASE = 5.99;
    const SHIPPING_PER_ITEM = 1.50;
    
    const itemCount = order.items.reduce(
      (sum, item) => sum + item.quantity,
      0
    );
    
    return SHIPPING_BASE + (itemCount * SHIPPING_PER_ITEM);
  }
}
```

**Why this is good**:
- Each function does one thing
- Functions are short and readable
- Easy to test each calculation independently
- Clear naming shows intent
- No magic numbers - constants are named

---

## Resource Management

### Example: Database Operations

**Good - Proper cleanup and error handling**:

```typescript
class DatabaseService {
  async executeQuery<T>(
    query: string,
    params: any[]
  ): Promise<T[]> {
    const connection = await this.pool.getConnection();
    
    try {
      const result = await connection.query(query, params);
      return result.rows;
    } catch (error) {
      this.logger.error('Query failed', { query, error });
      throw new DatabaseError('Failed to execute query', { cause: error });
    } finally {
      // ALWAYS release connection
      connection.release();
    }
  }
  
  async withTransaction<T>(
    callback: (connection: Connection) => Promise<T>
  ): Promise<T> {
    const connection = await this.pool.getConnection();
    
    try {
      await connection.beginTransaction();
      const result = await callback(connection);
      await connection.commit();
      return result;
    } catch (error) {
      await connection.rollback();
      throw error;
    } finally {
      connection.release();
    }
  }
}

// Usage
const result = await dbService.withTransaction(async (conn) => {
  await conn.query('INSERT INTO users...', [userData]);
  await conn.query('INSERT INTO profiles...', [profileData]);
  return { success: true };
});
```

**Why this is good**:
- Resources are always cleaned up (finally block)
- Transactions properly rolled back on error
- Clear error propagation
- Reusable transaction pattern

---

## Testing Best Practices

### Example: Well-Structured Tests

**Good - Clear, comprehensive tests**:

```typescript
describe('UserService', () => {
  let userService: UserService;
  let mockRepository: jest.Mocked<UserRepository>;
  let mockLogger: jest.Mocked<Logger>;
  
  beforeEach(() => {
    mockRepository = {
      save: jest.fn(),
      findByEmail: jest.fn()
    } as any;
    
    mockLogger = {
      info: jest.fn(),
      error: jest.fn()
    } as any;
    
    userService = new UserService(mockRepository, mockLogger);
  });
  
  describe('createUser', () => {
    const validUserData = {
      email: 'test@example.com',
      firstName: 'John',
      lastName: 'Doe'
    };
    
    it('should create user with valid data', async () => {
      // Arrange
      mockRepository.findByEmail.mockResolvedValue(null);
      mockRepository.save.mockResolvedValue({
        id: '123',
        ...validUserData,
        createdAt: new Date()
      });
      
      // Act
      const result = await userService.createUser(validUserData);
      
      // Assert
      expect(result.id).toBeDefined();
      expect(result.email).toBe(validUserData.email);
      expect(mockRepository.save).toHaveBeenCalledTimes(1);
      expect(mockLogger.info).toHaveBeenCalled();
    });
    
    it('should throw error when user already exists', async () => {
      // Arrange
      mockRepository.findByEmail.mockResolvedValue({
        id: '456',
        ...validUserData
      } as any);
      
      // Act & Assert
      await expect(userService.createUser(validUserData))
        .rejects
        .toThrow(UserAlreadyExistsError);
    });
    
    it('should throw validation error when email is missing', async () => {
      // Arrange
      const invalidData = { ...validUserData, email: '' };
      
      // Act & Assert
      await expect(userService.createUser(invalidData))
        .rejects
        .toThrow(ValidationError);
    });
  });
});
```

**Why this is good**:
- Tests are independent and isolated
- Clear Arrange-Act-Assert structure
- Tests document expected behavior
- Good coverage of happy path and error cases
- Descriptive test names

---

## Remember

These examples show:
- ✅ Clear, focused responsibilities
- ✅ Dependency injection
- ✅ Proper error handling
- ✅ Simple, readable code
- ✅ Well-structured tests
- ✅ Resource cleanup
- ✅ Meaningful names

Use these patterns as templates for your own code!
