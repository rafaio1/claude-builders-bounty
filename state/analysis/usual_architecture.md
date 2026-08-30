> For the complete documentation index, see [llms.txt](https://tech.usual.money/llms.txt). Markdown versions of documentation pages are available by appending `.md` to page URLs; this page is available as [Markdown](https://tech.usual.money/overview/architecture.md).

# Architecture

{% hint style="info" %}
This architecture describes the V1 state of the USD0, ETH0 and USUAL protocol. Further updates will be commenced with new feature releases.
{% endhint %}

<figure><img src="/files/o9l1HKl5oNgY8FCvGfrG" alt=""><figcaption><p>V1 Architecture</p></figcaption></figure>

{% hint style="info" %}
This architecture describes the V1 state of the ETH0. Further updates will be commenced soon.
{% endhint %}

<figure><img src="/files/RiadAF4DjMzXwMW2jqWK" alt=""><figcaption><p>ETH0 V1 Architecture</p></figcaption></figure>

{% hint style="info" %}
This architecture describes the V1 state of the EUR0. Further updates will be commenced soon.
{% endhint %}

<figure><img src="/files/WiRMKKZ3jCHdzteBfily" alt="EUR0 V1 Architecture"><figcaption><p>EUR0 V1 Architecture</p></figcaption></figure>

The Usual protocol contracts are specifically engineered to handle complex operations such as asset swaps between Real World Assets (RWAs) and stablecoins, lifecycle management of the USD0 stablecoin, structured financial product issuance, efficient asset exchange without traditional liquidity pools, and accurate asset pricing for reliable transaction execution.

Usual's smart contracts follow the [transparent proxy pattern](https://docs.openzeppelin.com/contracts/4.x/api/proxy#TransparentUpgradeableProxy) to allow the Usual DAO to upgrade the protocol contracts, to expand its functionalities and have the possibility to remedy any unexpected issues. Our current on-chain Collateral RWA consists of [Hashnote's USYC](https://usyc.hashnote.com/).

## **Core Contracts**

### [**DaoCollateral**](/smart-contracts/protocol-contracts/usd0/usd0-daocollateral.md)

The `daoCollateral.sol` contract is essential in swapping real-world assets (RWAs) . It enables users to swap RWAs for the USD0 stablecoin and vice versa, and serves as a key node for converting these assets into more liquid forms like USDC.

* **Key Functionalities:**
  * **Swap and Redeem Mechanisms**: Facilitate the conversion between RWAs and Usual's stablecoin (USD0), as well as swapping into USDC for enhanced liquidity in conjunction with the SwapperEngine.

### [**USD0**](/smart-contracts/token-contracts/usd0.md)

The primary Stablecoin of Usual, a liquid and transferable ERC-20 token that can be staked or locked to receive rewards. It is backed by cash equivalents like tokenized money market funds.

* **Key Functionalities:**
  * **Controlled Minting and Burning**: Manages the stablecoin supply to match backing assets, essential for value stability.

### [**bUSD0 (formerly USD0++)**](#usd0-1)

The `USD0PP contract` is tailored for bond management, replicating traditional fixed end-date bonds. It allows for the issuance, management, and redemption of bUSD0 (formerly USD0++), a 4 year bond emitting off-chain yield (only during the pre-launch, on-chain afterwards)

* **Key Functionalities:**
  * **Bond Lifecycle Management**: Facilitates the minting and unwrapping of bond tokens, offering fixed-income securities in blockchain format.
  * **Emergency Withdrawal Mechanisms**: Provides options for asset withdrawal in critical situations, reinforcing trust and security for investors.
  * **Automated Parity Mechanisms**: Provides options for the Usual DAO to maintain parity of USD0<->bUSD0 (formerly USD0++) on secondary markets if deemed necessary.
  * **Floor-price redemption:** Provides an early-redemption option to redeem bUSD0 (formerly USD0++) before the bond maturity date for the floor price.

### [**SwapperEngine**](/smart-contracts/protocol-contracts/usd0/usd0-swapper-engine.md)

The SwapperEngine contract ensures efficient token swaps between USDC and USD0 through an order matching system, avoiding traditional liquidity pools for direct no-fee, low-slippage exchanges.

* **Key Functionalities:**
  * **Efficient Order Matching**: Allows for precise order placement and fulfillment, minimizing costs and slippage.

### [**ClassicalOracle**](/smart-contracts/utility-contracts/usd0/usd0-classicaloracle.md)

Essential for the ecosystem's functionality, the ClassicalOracle contract sources accurate pricing information to inform asset valuations , ensuring all financial operations are based on reliable market data.

* **Key Functionalities:**
  * **Robust Data Sources**: Aggregates and evaluate prices from pricefeeds to diminish risks related to price manipulation.
  * **Stablecoin Monitoring**: Implements checks to maintain stablecoin pegs, crucial for the ecosystem's financial stability.

### [**USUAL**](/smart-contracts/token-contracts/usualx.md)

The `USUAL` contract implements the governance token of the Usual Protocol, incorporating security features and role-based access control. $USUAL is a ERC-20 compliant token designed with pausability and permit functionalities, allowing for enhanced governance mechanisms and secure token operations.

* **Key Functionalities:**
  * **Role-Based Token Operations**: Implements strict access control for critical functions like minting, burning, and blacklist management through dedicated roles (USUAL\_MINT, USUAL\_BURN, BLACKLIST\_ROLE).

### [**USUAL\***](/overview/features/usual-1.md)

The `Usual*` contract implements the Early Contributor Token of the Usual Protocol, incorporating security features and role-based access control. $USUAL is a ERC-20 compliant token designed with pausability and permit functionalities, allowing for enhanced governance mechanisms and secure token operations. The totalSupply is capped and no further mints of `USUAL*` are possible. All Usual\* is initially locked into the [UsualSP contract](/smart-contracts/protocol-contracts/usual/usual-vested-allocation-staking.md) as part of the allocation/ vested mechanic.

* **Key Functionalities:**
  * **Role-Based Token Operations**:
    * Strict access control for critical functions through dedicated roles (USUALS\_BURN, BLACKLIST\_ROLE)
    * Special one-time deployment privileges for the USUALSP contract via stakeAll()

### [**Distribution Module Contract**](/smart-contracts/protocol-contracts/usual/usual-distribution.md)

The `DistributionModule` contract manages the daily distribution of Usual tokens across on-chain vaults (UsualX and UsualS) and off-chain user allocations. It implements a sophisticated distribution system with challenge mechanisms and merkle-proof validation to ensure fair and secure token allocation.

* **Key Functionalities:**
  * **Daily Token Distribution**:
    * Calculates and distributes new token emissions
    * Manages off-chain distribution allocations through a merkle-proof system
    * Scales distribution based on time elapsed since last distribution
  * **Security Mechanisms**:
    * Challengeable queue system for off-chain distributions
    * 7-day challenge period for distribution validation
    * Role-based access control for critical operations
  * **Distribution Features**:
    * Configurable bucket allocation percentages
    * Real-time emission calculations based on protocol parameters
    * Automated distribution tracking and validation system

### [Yield Module Contract](/smart-contracts/protocol-contracts/usual/usual-distribution/yield-module.md)

The `YieldModule` contract manages the collection, accumulation, and distribution of yield generated from Real World Assets (RWAs) backing the protocol's stablecoins. It serves as the central hub for yield processing and implements sophisticated mechanisms to ensure fair and efficient yield distribution across protocol participants.

* **Key Functionalities:**
  * **Yield Collection & Processing**:
    * Aggregates yield from multiple RWA sources backing USD0
    * Calculates blended interest rates from various RWA (Real World Asset) sources
    * Tracks interest rates for different assets via oracles or manual input
    * Calculates weighted average interest rates based on asset values in treasuries
    * Manages treasury addresses where assets are held
    * Provides a P90 interest rate for protocol calculations
* **Security Mechanisms:**
  * **Access Control:**
    * Role-based permissions for yield collection and calculation operations
  * **Yield Validation:**
    * Data freshness (checks if oracle data is within maxDataAge)
    * Feed interface validity (checks if Chainlink feed returns valid data)
    * Interest rate bounds (ensures rates don't exceed basis point limits)

This module works in conjunction with the Distribution Module to ensure that both newly minted tokens and accumulated yields are distributed fairly and efficiently across the protocol ecosystem.

### [ETH0](/overview/features/eth0.md)

`ETH0` is an Ethereum-pegged synthetic ERC-20 compliant token fully collateralized by wstETH.

* **Key Functionalities:**
  * **Controlled Minting and Burning**: Manages the ETH0 supply to match backing asset (wstETH), essential for value stability.
  * **Controlled Supply Management**:

    Mint Cap: Has a configurable mint cap to prevent excessive issuance
  * **Role-Based Token Operations**:
    * Strict access control for critical functions through dedicated roles (ETH0\_MINT, ETH0\_BURN, BLACKLIST\_ROLE)
    * Emergency stop though dedicated role (PAUSING\_CONTRACTS\_ROLE, UNPAUSING\_CONTRACTS\_ROLE)

### [ETH0 DaoCollateral](/smart-contracts/protocol-contracts/eth0/eth0-daocollateral.md)

`ETH0 DaoCollateral` contract is a core component of ETH0 that manages collateralization, minting, and redemption of ETH0 tokens. It ensures ETH0 is fully backed by collateral and provides secure mechanisms for token swapping and redemption with emergency safeguards.

* **Key Functionalities:**
  * **Swap and Redeem Mechanisms**: Facilitate the conversion between wstETH and Usual's ETH (ETH0).
  * **Role-Based Token Operations**: Segregated roles for admin, pausing, unpausing, and DAO operations
  * **Fee Management** Adjustable redemption fees (max 25%) for protocol sustainability and automated fee distribution to yield treasury
* **Security Mechanisms:**
  * **Counter Bank Run (CBR)**: Emergency mechanism that reduces collateral returns during market stress
  * **Pausability**: Granular pausing of swap/redeem operations and global contract pausing

### [EUR0](/smart-contracts/token-contracts/eur0.md)

`EUR0` is an Ethereum-pegged synthetic ERC-20 compliant token fully collateralized by EUTBL.

* **Key Functionalities:**
  * **Controlled Minting and Burning**: Manages the EUR0 supply to match backing asset (EUTBL), essential for value stability.
  * **Role-Based Token Operations**:
    * Strict access control for critical functions through dedicated roles (EUR0\_MINT, EUR0\_BURN, BLACKLIST\_ROLE)
    * Emergency stop though dedicated role (PAUSING\_CONTRACTS\_ROLE, UNPAUSING\_CONTRACTS\_ROLE)

### [EUR0 DaoCollateral](/smart-contracts/protocol-contracts/eur0/eur0-daocollateral.md)

`EUR0 DaoCollateral` contract is a core component of EUR0 that manages collateralization, minting, and redemption of EUR0 tokens. It ensures EUR0 is fully backed by collateral and provides secure mechanisms for token swapping and redemption with emergency safeguards.

* **Key Functionalities:**
  * **Swap and Redeem Mechanisms**: Facilitate the conversion between EUTBL and Usual's EUR (EUR0).
  * **Role-Based Token Operations**: Segregated roles for admin, pausing, unpausing, and DAO operations
  * **Fee Management** Adjustable redemption fees (max 25%) for protocol sustainability and automated fee distribution to yield treasury
* **Security Mechanisms:**
  * **Counter Bank Run (CBR)**: Emergency mechanism that reduces collateral returns during market stress
  * **Pausability**: Granular pausing of swap/redeem operations and global contract pausing

### [EUR0 SwapperEngine](/smart-contracts/protocol-contracts/eur0/eur0-swapperengine.md)

The SwapperEngine contract ensures efficient token swaps between EURC and EUR0 through an order matching system, avoiding traditional liquidity pools for direct no-fee, low-slippage exchanges.

* **Key Functionalities:**
  * **Efficient Order Matching**: Allows for precise order placement and fulfillment, minimizing costs and slippage.

### [USUALX Lockup](/smart-contracts/protocol-contracts/usual/usualx-lockup-contract.md)

The `UsualXLockup` contract allows users to lock their **UsualX** tokens for predetermined durations (1, 3, 6, or 12 months). It's designed primarily for governance participation and reward earning mechanisms, providing a secure and flexible token locking infrastructure with comprehensive position management capabilities.

* **Key Functionalities:**
  * **Locking Operations**
    * **Position Creation**: Users can create new lock positions with specified amounts and durations
    * **Intra-day Top-ups**: Enhance existing positions within the same UTC calendar day as creation
    * **Position Release**: Withdraw tokens after lock expiration
    * **Combined Operations**: Release expired positions and immediately create new ones
* **Security Mechanisms:**
  * **Role-based Permissions**: Different roles for pausing, unpausing, duration management, and forced unlocking
  * **Reentrancy Protection**: Guards against reentrancy attacks on all state-changing functions
  * **Pausable Operations:** Emergency halt capabilities for contract operations
* **Administrative Features**
  * **Lock Duration Management**: Configure which lock durations are available
  * **Batch Processing**: Efficient handling of multiple position unlock operation
  * **Balance Tracking**: Total locked amount per user
