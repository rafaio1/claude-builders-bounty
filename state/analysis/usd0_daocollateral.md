> For the complete documentation index, see [llms.txt](https://tech.usual.money/llms.txt). Markdown versions of documentation pages are available by appending `.md` to page URLs; this page is available as [Markdown](https://tech.usual.money/smart-contracts/protocol-contracts/usd0/usd0-daocollateral.md).

# USD0 DaoCollateral

## High-Level Overview

The DaoCollateral contract is a crucial component of the USD0 stablecoin ecosystem, designed to manage the collateralization, minting, and redemption of USD0 tokens. It ensures that the circulating supply of USD0 is always fully backed by Real World Assets (RWA) collateral, providing transparency and security for USD0 holders. The contract facilitates the swapping of RWA tokens for USD0, redemption of USD0 for RWA tokens, and implements an intent-based matching system for efficient, non-custodial trading.

### Contract Summary

#### Inherited Contracts

* `Initializable` (OZ): Allows the contract to be initialized in an upgradeable pattern.
* `ReentrancyGuardUpgradeable` (OZ): Prevents reentrant attacks on sensitive functions.
* `PausableUpgradeable` (OZ): Enables pausing of contract functionality by authorized accounts.
* `NoncesUpgradeable` (OZ): Manages nonces for user operations.
* `EIP712Upgradeable` (OZ): Implements EIP-712 for structured data hashing and signing.

## Functionality Breakdown

#### Key Functionalities

1. **Minting and redeeming USD0:**

At its core, the contract accrues RWAs (USYC) by routing trades accordingly. When a user sends RWA, the daoCollateral contract mints the equivalent amount of USD0 stablecoins, and vice versa, allowing users to exchange their USD0 stablecoins for RWAs, represented as USYC tokens, at the current exchange rate.

* **Swap:** Facilitates the conversion of Real World Assets (RWAs), represented as USYC tokens, into the DAO's stablecoin (USD0). Upon initiating this function, users exchange their USYC tokens for USD0 stablecoins directly.
* **Redeem:** Allows users to redeem their USD0 stablecoins against a fee. By invoking this function, users exchange their USD0 stablecoins for RWAs, represented as USYC tokens, at the current exchange rate.

The system is also able to route Swapper Engine trades on their behalf against a different token pair (USDC/USD0), by accumulating the underlying RWAs and minting USD0 to route user's intents. This mechanism, inspired by CowSwap, allows RWA providers to retain their tokens until the trade is executed, allowing for *non-custodial, gas-less, just-in-time,* RWA liquidity providers.

2. **Intent-Based Matching System (Three-Way Trade Example):**

The Intent-Based Matching System is facilitated by the daoCollateral contract, in this example three parties are involved: a USDC provider, an RWA provider, and the daoCollateral contract itself. Here’s how it works step-by-step:

* **USDC Provider**: A user who holds USDC initiates a trade by providing USDC to the Swapper engine. In return, this user receives USD0.
* **RWA Provider**: Another user who holds Real World Assets (RWAs), such as USYC, wants to exchange these assets for USDC. This user submits their intent to trade RWAs for USDC to the daoCollateral contract.
* **daoCollateral Contract**: The daoCollateral contract plays a crucial intermediary role in this three-way trade. It accumulates the RWAs from the RWA provider. The contract mints new USD0 tokens equivalent to the value of the received RWAs. The contract then completes the trade by providing the newly minted USD0 to the Swapper engine, which matches the initial USDC provider’s trade. Finally, the daoCollateral contract gives the USDC from the USDC provider to the RWA provider.

#### 3. Role-Based Access Control

The contract implements a role-based access control system for sensitive operations:

* DEFAULT\_ADMIN\_ROLE: Has the highest level of access, including the ability to unpause the contract and perform critical administrative tasks.
* INTENT\_MATCHING\_ROLE: Required to execute intent-based swaps, ensuring that only authorized entities can match and process intents.
* NONCE\_THRESHOLD\_SETTER\_ROLE: Allows setting of nonce thresholds, which is crucial for the intent-based system's security.
* PAUSING\_CONTRACTS\_ROLE: Grants the ability to pause specific contract functionalities in case of emergencies. These roles ensure that different levels of access are properly managed and that sensitive operations are restricted to authorized entities, enhancing the overall security and governance of the contract.

### Functions Description

#### Public/External Functions

* `initialize`: Sets up the contract with initial parameters.
* `swap`: Allows users to swap RWA tokens for USD0.
* `swapWithPermit`: Similar to `swap` but uses permit for approval.
* `redeem`: Enables users to redeem USD0 for RWA tokens.
* `redeemDao`: Special redemption function for DAO operations. Only callable by DEFAULT\_ADMIN\_ROLE.
* `swapRWAtoStbc`: Facilitates swapping RWA to stablecoins through the SwapperEngine.
* `swapRWAtoStbcIntent`: Executes swaps based on signed intents. Only callable by INTENT\_MATCHING\_ROLE.
* `activateCBR`: Activates the Counter Bank Run mechanism. Only callable by DEFAULT\_ADMIN\_ROLE.
* `deactivateCBR`: Deactivates the Counter Bank Run mechanism. Only callable by DEFAULT\_ADMIN\_ROLE.
* `setRedeemFee`: Sets the fee for redemption operations. Only callable by DEFAULT\_ADMIN\_ROLE.
* `setNonceThreshold`: Set the lower bound for the intent nonce to be considered consumed. Only callable by NONCE\_THRESHOLD\_SETTER\_ROLE.
* `pauseRedeem`, `pause`, `pauseSwap`: Pausing functions for specific operations. Only callable by PAUSING\_CONTRACTS\_ROLE.
* `unpause`, `unpauseRedeem`, `unpauseSwap` : Global unpausing functions.

### Constants

* CONTRACT\_REGISTRY\_ACCESS: Address of the registry access contract.
* CONTRACT\_TOKEN\_MAPPING: Address of the token mapping contract.
* CONTRACT\_ORACLE: Address of the oracle contract.
* CONTRACT\_TREASURY: Address of the treasury contract.
* CONTRACT\_USD0: Address of the USD0 token contract.
* CONTRACT\_SWAPPER\_ENGINE: Address of the SwapperEngine contract.
* DEFAULT\_ADMIN\_ROLE: Role identifier for the default admin.
* INTENT\_MATCHING\_ROLE: Role identifier for intent matching operations.
* NONCE\_THRESHOLD\_SETTER\_ROLE: Role identifier for setting nonce thresholds.
* PAUSING\_CONTRACTS\_ROLE: Role identifier for pausing contract operations.
* MAX\_REDEEM\_FEE: Maximum allowed redemption fee.
* SCALAR\_ONE: Scalar value representing 1 in the contract's decimal system.
* SCALAR\_TEN\_KWEI: Scalar value representing 10,000 in the contract's decimal system.
* INTENT\_TYPE\_HASH: Type hash for EIP-712 structured data signing of intents.

### Key Components

* **Oracle Integration**: Uses an oracle to fetch real-time price data for RWA tokens.
* **SwapperEngine**: Interacts with the SwapperEngine contract for executing trades.
* **Token Mapping**: Manages the mapping of supported RWA tokens.
* **Access Control**: Implements role-based access control for administrative functions.

### Safeguards Implementation

* **Pausability**: Allows pausing of critical functions in emergencies.
* **Reentrancy Protection**: Uses OpenZeppelin's ReentrancyGuard to prevent reentrancy attacks.
* **Access Control**: Restricts sensitive operations to authorized roles.
* **Intent Validation**: Implements checks for intent-based swaps.
