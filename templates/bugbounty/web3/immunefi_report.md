# Immunefi Bug Bounty Report Template

## Vulnerability Title
[Specific vulnerability type] in [Protocol/Contract Name] - [Impact Summary]

## Severity Assessment
- **CVSS Score:** [X.X]
- **Immunefi Severity:** [Critical/High/Medium/Low]
- **Asset Type:** Smart Contract / Blockchain / Web Application
- **Estimated Funds at Risk:** [$X,XXX,XXX]

## Affected Asset
- **Contract Address:** [0x...]
- **Chain:** [Ethereum/Polygon/Arbitrum/etc.]
- **Repository:** [GitHub URL]
- **Commit Hash:** [abc123...]

## Executive Summary
[2-3 sentence description of the vulnerability and its potential impact on protocol funds or users]

## Pre-conditions
- [Required state/condition for exploit]
- [User role/permissions needed]
- [External dependencies or oracle states]

## Proof of Concept
### Step-by-Step Reproduction
1. [Exact step with code/command]
2. [Next step]
3. [Continue until impact demonstrated]

### Exploit Code
```solidity
// Minimal reproducible exploit contract or script
// MUST use testnet/fork only - never mainnet
```

### Expected vs Actual Behavior
- **Expected:** [What should happen]
- **Actual:** [What actually happens]
- **Impact:** [Quantified loss or state corruption]

## Impact Analysis
- **Direct Financial Loss:** [$X if exploited]
- **User Funds at Risk:** [Yes/No - amount]
- **Protocol Solvency:** [Affected/Unaffected]
- **Recovery Path:** [Possible/Impossible without governance]

## Remediation Recommendation
[Specific fix with code snippet if applicable]

## Disclosure Timeline
- **Discovery Date:** [YYYY-MM-DD]
- **Report Submitted:** [YYYY-MM-DD HH:MM UTC]
- **Platform:** Immunefi
- **Researcher Account:** [Username]

## Evidence Attachments
- [ ] Transaction hash (testnet/fork)
- [ ] Screenshots of vulnerable state
- [ ] Gas analysis (if relevant)
- [ ] Audit trail of reproduction steps

---
*Template generated: 2026-08-26T03:10:22Z*
*Compliance: Immunefi Responsible Disclosure Policy*
*Sanitization: All addresses/keys must be testnet or placeholder values*
