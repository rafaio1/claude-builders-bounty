# Sherlock Security Finding Template

## Protocol: [Name]
## Audit Contest: [Link]
## Finding Category: [Access Control / Accounting / Oracle / Governance / Other]

### Severity Justification
- **Base Severity:** [Critical/High/Medium/Low]
- **Escalation Reason:** [Why initial rating may underestimate impact]
- **Funds Directly at Risk:** [$X or % of TVL]

### Technical Description
[Precise explanation of the vulnerability mechanism]

### Attack Scenario
1. Attacker does [action]
2. Protocol state becomes [vulnerable state]
3. Result: [financial loss or system failure]

### Code Reference
```solidity
// Exact lines showing the bug
// File: contracts/X.sol Lines: Y-Z
```

### Validation Evidence
- [Test case link or hash]
- [Fork simulation tx hash]
- [Mathematical proof if applicable]

### Mitigation Complexity
- [Trivial / Moderate / Requires Governance / Impossible without upgrade]

### Duplicate Check
- Searched contest submissions: [Yes/No]
- Similar findings found: [List or None]
- Unique contribution: [What makes this distinct]

---
*Template generated: 2026-08-26T03:10:22Z*
*Compliance: Sherlock Escalation Policy*
*Requirement: All PoCs must be non-destructive and use test environments*
