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
