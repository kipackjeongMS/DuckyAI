# SOLID Principles Reference Guide

## Overview

SOLID is an acronym for five design principles that make software designs more understandable, flexible, and maintainable.

---

## S - Single Responsibility Principle (SRP)

**Definition**: A class should have one, and only one, reason to change. Each class should have a single, well-defined responsibility.

### How to Identify Violations

- Class has multiple unrelated methods
- Class name contains "And", "Manager", "Handler" (often god objects)
- Changes to one feature require modifying the class for unrelated reasons
- Class has high coupling with many other classes

### Red Flags

```
❌ Class has methods for: validation, database access, business logic, logging, formatting
❌ Class name: UserManagerAndValidator
❌ Class changes when: UI changes, database changes, business rules change
```

### Questions to Ask

1. What is this class's primary responsibility?
2. How many different actors could request changes to this class?
3. Can you describe what the class does in one sentence without using "and"?

### Fix Strategy

- Extract separate classes for each responsibility
- Create focused classes with clear, single purposes
- Use composition to combine behaviors

---

## O - Open/Closed Principle (OCP)

**Definition**: Software entities should be open for extension but closed for modification. You should be able to add new functionality without changing existing code.

### How to Identify Violations

- Every new feature requires modifying existing classes
- Large if/else or switch statements checking types
- Code doesn't use inheritance or interfaces for polymorphism
- Hard-coded implementations instead of abstract dependencies

### Red Flags

```
❌ Adding new payment type requires editing PaymentProcessor class
❌ Giant switch statement on type checking
❌ No use of interfaces or abstract classes
❌ Concrete class dependencies everywhere
```

### Questions to Ask

1. Can I add new behavior without modifying existing code?
2. Are there switch/if-else chains that grow with new features?
3. Am I using abstraction to support variation?

### Fix Strategy

- Use interfaces or abstract classes to define contracts
- Apply Strategy pattern for varying behaviors
- Use dependency injection for flexibility
- Prefer composition over modification

---

## L - Liskov Substitution Principle (LSP)

**Definition**: Derived classes must be substitutable for their base classes. If S is a subtype of T, then objects of type T can be replaced with objects of type S without breaking the program.

### How to Identify Violations

- Subclass throws exceptions for base class methods
- Subclass removes functionality from parent
- Subclass requires type checking before use
- Subclass behavior contradicts parent's contract

### Red Flags

```
❌ Subclass throws NotImplementedException
❌ Override returns null when parent contract says non-null
❌ Code checks: if (bird instanceof Penguin) { /* can't fly */ }
❌ Subclass strengthens preconditions or weakens postconditions
```

### Classic Example: Rectangle/Square Problem

A Square that inherits from Rectangle violates LSP because:
- Setting width should also set height for Square
- Code expecting Rectangle behavior breaks with Square

### Questions to Ask

1. Can the subclass truly replace the parent in all contexts?
2. Does the subclass maintain the parent's behavioral contract?
3. Would code break if you swapped subclass for parent?

### Fix Strategy

- Favor composition over inheritance when behavior differs
- Use interfaces to define contracts instead of inheritance
- Don't inherit just to reuse code; inherit to substitute

---

## I - Interface Segregation Principle (ISP)

**Definition**: No client should be forced to depend on methods it doesn't use. Prefer many small, specific interfaces over one large, general interface.

### How to Identify Violations

- Interface has many methods, clients only use a few
- Implementing classes throw NotImplementedException
- Interface name is generic (IService, IManager)
- Clients are coupled to methods they don't need

### Red Flags

```
❌ Interface has 15+ methods
❌ Implementations leave methods empty or throw exceptions
❌ Interface mixes different concerns (database + logging + validation)
❌ Changes to interface affect clients that don't use changed methods
```

### Questions to Ask

1. Does every client use every method in this interface?
2. Can I split this interface into smaller, focused contracts?
3. Are implementations forced to provide empty methods?

### Fix Strategy

- Split large interfaces into role-specific interfaces
- Create focused interfaces per client need
- Use interface inheritance if needed to compose contracts
- Apply Interface Segregation before implementing

---

## D - Dependency Inversion Principle (DIP)

**Definition**: High-level modules should not depend on low-level modules. Both should depend on abstractions. Abstractions should not depend on details; details should depend on abstractions.

### How to Identify Violations

- High-level code directly instantiates low-level classes
- Business logic depends on infrastructure details
- No use of dependency injection
- Concrete dependencies instead of interfaces

### Red Flags

```
❌ UserService creates new MySQLRepository() directly
❌ Business logic contains database connection strings
❌ Controller instantiates EmailService with SMTP details
❌ Testing requires real database connections
```

### Questions to Ask

1. Do high-level classes instantiate low-level classes directly?
2. Can I swap implementations without changing high-level code?
3. Are dependencies injected or created internally?

### Fix Strategy

- Depend on interfaces, not concrete implementations
- Use dependency injection (constructor, property, method)
- Let frameworks or composition root create dependencies
- Invert the dependency flow through abstractions

---

## Practical Application Guide

### When Reviewing Code

1. **Read the class name**: Does it imply multiple responsibilities?
2. **Count reasons to change**: More than one = SRP violation
3. **Check for type switching**: Suggests OCP violation
4. **Verify substitutability**: Can subclasses really replace parents?
5. **Review interfaces**: Are they bloated with unused methods?
6. **Trace dependencies**: Are abstractions used or concrete classes?

### Priority Order

When multiple violations exist, fix in this order:

1. **Dependency Inversion** - Establishes abstractions
2. **Single Responsibility** - Clarifies purpose
3. **Interface Segregation** - Defines focused contracts
4. **Open/Closed** - Enables extension
5. **Liskov Substitution** - Ensures correct inheritance

### Common Patterns That Help

- **Strategy Pattern**: OCP, DIP
- **Factory Pattern**: OCP, DIP
- **Adapter Pattern**: LSP, ISP
- **Composite Pattern**: OCP, LSP
- **Dependency Injection**: DIP

---

## Language-Specific Notes

### TypeScript/JavaScript
- Use interfaces and abstract classes
- Leverage dependency injection frameworks (NestJS, InversifyJS)
- Apply ISP with focused TypeScript interfaces

### Python
- Use ABC (Abstract Base Classes) for contracts
- Apply duck typing carefully while respecting contracts
- Use type hints to document dependencies

### Java/C#
- Strong type system enforces contracts well
- Built-in interface support
- Excellent DI framework support

### Go
- Interfaces are implicit (structural typing)
- Small, focused interfaces are idiomatic
- Use composition over inheritance

---

## Quick Decision Tree

```
Does the class have multiple reasons to change?
  └─ Yes → SRP violation → Extract classes

Can you add features without modifying code?
  └─ No → OCP violation → Add abstractions

Can subclass substitute parent everywhere?
  └─ No → LSP violation → Reconsider inheritance

Do clients use all interface methods?
  └─ No → ISP violation → Split interface

Does high-level depend on low-level details?
  └─ Yes → DIP violation → Inject dependencies
```

---

## Remember

SOLID principles are **guidelines, not laws**. Apply them pragmatically:
- Small projects may not need full SOLID compliance
- Over-engineering is also a problem
- Balance principles with simplicity (KISS)
- Consider team experience and project constraints
