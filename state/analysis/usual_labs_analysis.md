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
> For the complete documentation index, see [llms.txt](https://tech.usual.money/llms.txt). Markdown versions of documentation pages are available by appending `.md` to page URLs; this page is available as [Markdown](https://tech.usual.money/smart-contracts/protocol-contracts/usd0/usd0-swapper-engine.md).

# USD0 Swapper Engine

## High-Level Overview

The **`SwapperEngine`** contract is a smart contract designed to facilitate the swapping of *USDC* tokens for *USD0* tokens using an order matching mechanism. The contract allows users to create orders specifying the amount of *USDC* they wish to swap, and other users can fill these orders by providing *USD0* tokens in return. The contract aims to provide a direct token swapping solution without the need for intermediary liquidity pools.

The main objective of the **SwapperEngine** contract is to enable efficient and low-slippage token swaps between users. The contract relies on oracle-based pricing to determine swap prices, which helps minimize slippage. However, liquidity within the contract depends on the availability of active orders, and users may need to wait for new orders to be created if no matching orders are available.

It is important to note that the contract's mechanism can be utilized to facilitate a vampire attack, **RWA → USD0 → USDC → $$$ → RWA →** to churn *USDC* into USD0 by transparently staking treasury bonds to mint *USD0* swapping that *USD0* for *USDC* and cycling back into RWA ready to mint more *USD0* limited only by *USDC* order book depth.

Flow USDC Depositors:

{% @mermaid/diagram content="sequenceDiagram
autonumber
participant A as Alice
participant SW as SwapperContract
A->>SW: Deposit USDC & create order
SW->>A: Receive USD0 when order filled
" fullWidth="true" %}

Flow RWA Provider:

{% @mermaid/diagram content="sequenceDiagram
autonumber
participant A as Alice
participant R as Robert
participant SW as SwapperContract
participant DC as DaoCollateralContract
R->>UI: Sign spending approval of RWA
R->>DC: Send transactions w/ Alice offerIds
R->>DC: TransferFrom(R,DC)  RWA
DC->>DC: USD0 minting
DC->>SW: call provideUSD0ReceiveUSDC
note left of DC: transfer USD0 from DC to Alice
SW->>R: Transfer USDC
SW->>A: Transfer USD0
critical Partially filled order (not enough USDC to fulfill request)
option
SW->>DC: Return unmatched amount USD0 amount to redeem
DC->>R: Send back remaining RWA unmatched
end
" fullWidth="false" %}

### Contract Summary

The contract provides the following main functions:

* **depositUSDC**: Allows users to create a new order by depositing *USDC*.
* **withdrawUSDC**: Allows users to cancel an order and withdraw their deposited *USDC*.
* **provideUsd0ReceiveUSDC**: Allows users to fill orders by providing *USD0* and receiving *USDC* in return.

The contract also includes utility functions such as getOrder, getUsd0WadEquivalent, and getUsdcWadPrice to retrieve order details and perform price calculations. The swapperEngine has no option to define a maxUSDCPrice for buyers and seller's don't have the option to define a minimumUSDCPrice, instead the prices are provided by an USDC oracle, which also has measures against a potential USDC depeg. USD0's price is considered to be $1 == 1USD0 due to the numerous mechanisms in place to prevent a depeg, like reserves, CBR mechanism, arbitrage etc.

### Inherited Contracts

* **Initializable** (OZ): Used to provide a safe and controlled way to initialize the contract's state variables. It ensures that the contract's initializer function can only be called once, preventing accidental or malicious reinitialization.
* **ReentrancyGuardUpgradeable** (OZ): Used to protect against reentrancy attacks. It provides a modifier that can be applied to functions to prevent them from being called recursively or from being called from other functions that are also protected by the same guard.
* **PausableUpgradeable (OZ)**: Allows contract functionality to be paused by authorized accounts (`PAUSING_CONTRACTS_ROLE` to pause the contract and `DEFAULT_ADMIN_ROLE` to un-pause).

## Functionality Breakdown

The SwapperEngine contract's primary purpose is to facilitate the swapping of *USDC* tokens for *USD0* tokens using an order matching mechanism. The contract's functionality can be broken down into the following key components:

1. **Order Creation**:
   * Users can create new orders by calling the **depositUSDC** function and specifying the amount of *USDC* they wish to swap.
   * The contract transfers the specified amount of *USDC* tokens from the user to itself and creates a new order with the deposited amount and the user's address as the requester.
   * The order is assigned a unique order ID and stored in the contract's orders mapping.
2. **Order Cancellation**:
   * Users who have created an order can cancel it by calling the **withdrawUSDC** function and specifying the order ID.
   * The contract verifies that the caller is the requester of the order and that the order is active.
   * If the conditions are met, the contract deactivates the order, sets its token amount to zero, and transfers the deposited *USDC* tokens back to the requester.
3. **Order Matching**:
   * Users can fill existing orders by specifying the recipient address, the amount of *USDC* to take (or the amount of USD0 to give), an array of order IDs to match against, and whether partial matching is allowed.
   * The contract verifies that the caller has sufficient *USD0* balance and allowance to cover the required amount based on the current *USDC* Price Calculation obtained from the oracle.
   * The contract iterates through the provided order IDs and attempts to match the requested *USDC* amount against active orders.
   * If partial matching is allowed and there is not enough *USDC* in the orders to fulfil the entire request, the contract will partially fill orders until the requested amount is met or all orders are exhausted.
   * For each matched order, the contract transfers the corresponding *USD0* tokens from the caller to the order requester and transfers the *USDC* tokens from itself to the specified recipient.
   * If partial matching is not allowed and the requested *USDC* amount cannot be fully matched, the contract reverts the transaction.
4. **Price Calculation**:
   * The contract relies on an external oracle contract to obtain the current price of *USDC* tokens in WAD format (18 decimals).
   * The getUsdcWadPrice function is used to retrieve the current *USDC* price from the oracle.
   * The getUsd0WadEquivalent function is used to calculate the equivalent amount of *USD0* tokens for a given amount of *USDC* tokens based on the current price.

### Security Analysis

#### Method: provideUsd0ReceiveUSDC

This method allows users to provide *USD0* tokens and receive *USDC* tokens by matching against existing orders. It matches the requested *USDC* amount to the provided *USD0* tokens against the specified orders, transfers the corresponding *USDC* tokens to the recipient, and updates the order states accordingly.

```rust
1 function _provideUsd0ReceiveUSDC( ... ) internal returns (uint256 unmatchedUsdcAmount, uint256 totalUsd0Provided) {
2    if (amountUsdcToTakeInNativeDecimals == 0) { revert AmountIsZero() }
3    if (orderIdsToTake.length == 0) { revert NoOrdersIdsProvided() }
4    SwapperEngineStorageV0 storage $ = _swapperEngineStorageV0();
5    uint256 usdcWadPrice = _getUsdcWadPrice();
6    uint256 totalUsdcTaken = 0;

```

1. The function is protected against reentrancy attacks by using the nonReentrant modifier, ensuring that the function cannot be called recursively or from other functions that are also protected by the same guard.
2. Validates that the amount of *USDC* to take is greater than zero.
3. Validates that at least one order ID is provided for matching.
4. Retrieves the contract's storage using the correct storage pattern.
5. Retrieves the current price of *USDC* in WAD format (18 decimals) from an oracle, ensuring that the price used for calculations is up-to-date and accurate.
6. Initializes the total amount of *USDC* taken to zero.

```rust
 8  for (uint256 i; i < orderIdsToTake.length && totalUsdcTaken < amountUsdcToTakeInNativeDecimals;) {
 9      uint256 orderId = orderIdsToTake[i];
10      UsdcOrder storage order = $.orders[orderId];
11      if (order.active) {
12          uint256 remainingAmountToTake = amountUsdcToTakeInNativeDecimals - totalUsdcTaken;
13          uint256 amountOfUsdcFromOrder = order.tokenAmount > remainingAmountToTake ? remainingAmountToTake : order.tokenAmount;
14          order.tokenAmount -= amountOfUsdcFromOrder;
15          totalUsdcTaken += amountOfUsdcFromOrder;
16          if (order.tokenAmount == 0) { order.active = false };
17          uint256 usd0Amount = _getUsd0WadEquivalent(amountOfUsdcFromOrder, usdcWadPrice);
18          totalUsd0Provided += usd0Amount;
19          $.usd0.safeTransferFrom(msg.sender, order.requester, usd0Amount);
20          $.usdcToken.safeTransfer(recipient, amountOfUsdcFromOrder);
21          emit OrderMatched(order.requester, msg.sender, orderId, amountOfUsdcFromOrder);
22      }
23      unchecked { ++i }
24  }
25  if (!partialMatchingAllowed && totalUsdcTaken != amountUsdcToTakeInNativeDecimals || totalUsdcTaken == 0) { revert AmountTooLow() }
26  return ((amountUsdcToTakeInNativeDecimals - totalUsdcTaken), totalUsd0Provided);
...
```

10. Retrieves the order details for the current order ID.
11. Checks if the order is active before processing. 12-13. If the order is active, calculates the amount of USDC to take from the current order based on the remaining amount to take and the order's available balance. 14-15. Updates the order's token amount and the total USDC taken.
12. Marks the order as inactive if its token amount reaches zero.
13. Calculates the equivalent USD0 amount for the USDC taken from the order using the \_getUsd0WadEquivalent function and the current USDC price.
14. Updates the total USD0 provided with the calculated amount.
15. Transfers the USD0 tokens from the sender to the order requester.
16. Transfers the USDC tokens from the contract to the recipient.
17. Emits an OrderMatched event with the relevant details.
18. Increments the loop counter using an unchecked block for gas optimization.
19. Reverts the transaction if partial matching is not allowed and the total USDC taken does not match the requested amount or if no USDC was taken.
20. Returns the remaining amount of USDC that was not taken and the total USD0 provided.

#### Method: getUsd0WadEquivalent

This method calculates the USD0 equivalent amount in WAD format (18 decimals) for a given USDC token amount. It converts the USDC token amount from its native decimal representation (6 decimals) to WAD format and then calculates the equivalent USD0 amount based on the provided USDC price in WAD format.

```rust
1  function _getUsd0WadEquivalent(uint256 usdcTokenAmountInNativeDecimals, uint256 usdcWadPrice) private view returns (uint256 usd0WadEquivalent) {
2      SwapperEngineStorageV0 storage $ = _swapperEngineStorageV0();
3      uint8 decimals = IERC20Metadata(address($.usdcToken)).decimals();
4      uint256 usdcWad = usdcTokenAmountInNativeDecimals.tokenAmountToWad(decimals);
5      usd0WadEquivalent = usdcWad.wadAmountByPrice(usdcWadPrice);
6  }
```

2. Retrieves the contract's storage using the correct storage pattern.
3. Retrieves the decimal places of the USDC token using the decimals() function from the IERC20Metadata interface.
4. Converts the usdcTokenAmountInNativeDecimals to WAD format (18 decimals) using the tokenAmountToWad function, which takes into account the token's native decimals.
5. Calculates the equivalent amount of USD0 tokens in WAD format by multiplying the usdcWad amount with the usdcWadPrice using the wadAmountByPrice function.

#### Method: depositUSDC

This method allows users to deposit USDC tokens and create a new order. It transfers the specified amount of USDC tokens from the caller to the contract and creates a new order with the deposited amount and the caller as the requester.

```rust
1  function depositUSDC(uint256 amountToDeposit) external nonReentrant {
2      SwapperEngineStorageV0 storage $ = _swapperEngineStorageV0();
3      if (amountToDeposit < $.minimumUSDCAmountProvided) { revert AmountTooLow();}
4      uint256 orderId = $.nextOrderId++;
5      $.orders[orderId] = UsdcOrder({requester: msg.sender, tokenAmount: amountToDeposit, active: true});
6      $.usdcToken.safeTransferFrom(msg.sender, address(this), amountToDeposit);
7      emit Deposit(msg.sender, orderId, amountToDeposit);
8  }
```

1. The function is protected against reentrancy attacks by using the nonReentrant modifier, ensuring that the function cannot be called recursively or from other functions that are also protected by the same guard.
2. Retrieves the contract's storage using the correct storage pattern.
3. Validates that the amount of USDC to deposit is greater than or equal to the minimum required amount specified in the contract's storage. This prevents any attempts to deposit amounts below the minimum threshold.
4. Sets the value of orderId to the current value of $.nextOrderId then increments by 1. Since it is initialized as 1, the first orderId will be one and so on.
5. Creates a new UsdcOrder struct in storage using the order ID as key. The struct is set up correctly to contain: the requester's address (msg.sender), the deposited token amount (amountToDeposit), and sets the active flag to true.
6. Transfers the specified amount of USDC tokens from the caller (msg.sender) to the contract (address(this)) using the safeTransferFrom function to ensure that the transfer is successful and the contract receives the deposited tokens. If the transfer fails, the function will revert.
7. Emits a Deposit event, providing the order ID and the deposited amount for the subgraph.

#### Method: withdrawUSDC

This method allows the requester of an order to withdraw their deposited USDC tokens and cancel the order. It deactivates the specified order, sets its token amount to zero, and transfers the deposited USDC tokens back to the requester.

```rust
 1  function withdrawUSDC(uint256 orderToCancel) external nonReentrant {
 2      SwapperEngineStorageV0 storage $ = _swapperEngineStorageV0();
 3      UsdcOrder storage order = $.orders[orderToCancel];
 4      if (!order.active) { revert OrderNotActive() }
 5      if (order.requester != msg.sender) { revert NotRequester() }
 6      uint256 amountToWithdraw = order.tokenAmount;
 7      order.active = false;
 8      order.tokenAmount = 0;
 9      $.usdcToken.safeTransfer(msg.sender, amountToWithdraw);
10      emit Withdraw(msg.sender, orderToCancel, amountToWithdraw);
11  }
```

1. The function is protected against reentrancy attacks by using the nonReentrant modifier, ensuring that the function cannot be called recursively or from other functions that are also protected by the same guard.
2. Retrieves the contract's storage using the correct storage pattern.
3. Retrieves the UsdcOrder struct as storage so it will be modified.
4. Checks if the order is active using the active flag. If the order is not active or does not exist, the function will revert with an appropriate error message. This prevents any attempts to withdraw from invalid or canceled orders.
5. Verifies that the caller (msg.sender) is the requester of the order. This ensures that only the original requester can cancel their own order and withdraw the deposited tokens.
6. Retrieves the token amount associated with the order and assigns it to the amountToWithdraw variable.
7. Sets the active flag of the order to false in storage.
8. Sets the tokenAmount of the order to zero in storage.
9. Transfers the amountToWithdraw of USDC tokens from the contract back to the requester (msg.sender) using the safeTransfer function. This ensures that the transfer is successful and the requester receives their tokens. If the transfer fails, the function will revert.
10. Emits a Withdraw event, providing the orderToCancel ID and the amountToWithdraw for the subgraph

### Method swapUsd0

This method allows users to provide *USD0* tokens and receive *USDC* tokens by matching against existing orders. It matches the specified amount of *USD0* tokens against the specified orders, transfers the corresponding *USDC* tokens to the recipient, and updates the order states accordingly.

```rust
 1  function swapUsd0(address recipient, uint256 amountUsd0ToProvideInWad, uint256[] memory orderIdsToTake, bool partialMatchingAllowed) external nonReentrant returns (uint256) {
 2      uint256 usdcWadPrice = _getUsdcWadPrice();
 3      (, uint256 totalUsd0Provided) = _provideUsd0ReceiveUSDC(
 4        recipient, _getUsdcAmountFromUsd0WadEquivalent(amountUsd0ToProvideInWad, usdcWadPrice), orderIdsToTake, partialMatchingAllowed
 5      );
 6      return amountUsd0ToProvideInWad - totalUsd0Provided;
 7  }
```

1. The function is protected against reentrancy attacks by using the nonReentrant modifier, ensuring that the function cannot be called recursively or from other functions that are also protected by the same guard.
2. Retrieves the current USDC price in WAD format using the getUsdcWadPrice() function. 3-5. Calculates the equivalent amount of USDC to take in native decimals based on the provided amountUsd0ToProvideInWad and the current usdcWadPrice using the \_getUsdcAmountFromUsd0WadEquivalent function. Then calls the \_provideUsd0ReceiveUSDC function to perform the actual swap, passing the recipient, amountUsdcToTakeInNativeDecimals, orderIdsToTake, and partialMatchingAllowed parameters. The function returns the total amount of usd0 provided.
3. Returns the sum of unmatchedUsd0 in wad format including dust, representing the total amount of USD0 that was not matched or was left as dust.
> For the complete documentation index, see [llms.txt](https://tech.usual.money/llms.txt). Markdown versions of documentation pages are available by appending `.md` to page URLs; this page is available as [Markdown](https://tech.usual.money/smart-contracts/token-contracts/usd0.md).

# USD0

## High-Level Overview

The USD0 contract is designed to manage Usuals Stablecoin, the USD0 ERC20 Token, implementing functionalities for minting, burning, and transfer operations while incorporating blacklist checks to restrict these operations to authorized addresses.&#x20;

The total USD0 supply is collateralized with at minimum 1:1 in USD Real World Assets ( read more [here](https://gitbook.usual.money/usual-mechanisms/liquid-deposit-token-ldt/usd0-rwa-stablecoin/why-usd0))

## Contract Summary

USD0 is an ERC-20 compliant token that integrates additional security and access control features to enhance its governance and usability. It inherits functionalities from ERC20PausableUpgradable and ERC20PermitUpgradeable to support permit-based approvals and pausability.

### Minting USD0

Users can swap their Real World Assets via the [USD0 DaoCollateral](/smart-contracts/protocol-contracts/usd0/usd0-daocollateral.md) to mint an equivalent USD amount of USD0. Alternatively, they can deposit USDC into the [USD0 Swapper Engine](/smart-contracts/protocol-contracts/usd0/usd0-swapper-engine.md) for a RWA Provider to exchange their RWA to USD0.&#x20;

Additionally, as part of the accumulating yield of our underlying Real World Assets, the Usual DAO can mint additional USD0 for any excess collateral above 100% + 21 days of yield.

### Redeeming USD0

Users can swap any USD0 back to the underlying Real World Assets at any time via the [USD0 DaoCollateral](/smart-contracts/protocol-contracts/usd0/usd0-daocollateral.md) contract, burning the USD0 in the process. In order to prevent sandwich oracle attacks on yield, the Usual DAO Treasury charges a redemption fee of`0.10%`

### Regulatory Compliance

The contract includes a blacklist feature to ensure regulatory compliance. Sanctioned addresses are prevented from interacting with the contract, and kept up to date. \
\
Usual is enforcing the OFAC Sanctions List: <https://sanctionslist.ofac.treas.gov/Home/SdnList>

As well as the FAFT: <https://www.fatf-gafi.org/en/home.html>

### Collateralization Enforcement

Minting of USD0 is only possible if the Usual DAO Treasury equals or exceeds the USD Backing Ratio of 1:1 in Real World Assets versus the USD0 totalSupply()

## Functionality Breakdown

#### Key Functionalities

* **Minting**: Tokens can be minted to an address, subject to role checks.
* **Burning**: Tokens can be burned from an address, also subject to role checks.
* **Transfers**: Only not blacklisted addresses can send or receive tokens.

### Functions Description

#### Public/External Functions

* **pause()**: Pauses all token transfer operations; callable only by the `PAUSING_CONTRACTS_ROLE`.
* **unpause()**: Resumes all token transfer operations; also callable only by the `DEFAULT_ADMIN_ROLE`.
* **transfer(address to, uint256 amount)**: Transfers tokens to a non-blacklisted address.
* **transferFrom(address sender, address to, uint256 amount)**: Transfers tokens from one non-blacklisted address to another.
* **mint(address to, uint256 amount)**: Mints tokens to a non-blacklisted address if the caller has the `USD0_MINT` role.
* **burn(uint256 amount)** and **burnFrom(address account, uint256 amount)**: Burns tokens from an address, requiring the `USD0_BURN` role.
* **blacklist(address account)** and **unBlacklist(address account)**: Those functions allows the admin to blacklist or remove from blacklist malicious users from using this token. Only callable by the BLACKLIST\_ROLE.

<br>

###


# Contract Addresses (Mainnet)
- USD0: 0x73A15FeD60Bf67631dC6cd7Bc5B6e8da8190aCF5
- bUSD0: 0x35D8949372D46B7a3D5A56006AE77B215fc69bC0
- DaoCollateral: 0xde6e1F680C4816446C8D515989E2358636A38b04
- SwapperEngine: 0xB969B0d14F7682bAF37ba7c364b351B830a812B2
- ClassicalOracle: 0xb97e163cE6A8296F36112b042891CFe1E23C35BF
- RegistryAccess: 0x0D374775E962c3608B8F0A4b8B10567DF739bb56
- TokenMapping: 0x43882C864a406D55411b8C166bCA604709fDF624

# Next Steps
1. Fetch verified source code via Etherscan V2 API (requires key) or alternative indexer
2. Map invariants for DaoCollateral swap/redeem logic
3. Analyze SwapperEngine order matching for rounding/slippage exploits
4. Review ClassicalOracle price feed validation for staleness bypass
5. Generate Foundry PoC for any viable Critical finding
