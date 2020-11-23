# Farmer Snapshot

## Abstract

This is a working repo for distributing 2.48 million USDC and USDT sent back by the hacker.
The work is based on previous distribution effort on "Your Eminence".

## Distribution details

The snapshot block chosen to be one block before the first attack: `11129473`.
We determine the amount that is lost by querying the difference between `underlyingBalanceWithInvestment()` of the Snapshot block and the one block after the attack. The end blocks for USDC is `11129500` and for USDT, it is `11129515`.

To create an accurate snapshot that is fair to all the users, we have reviewed the affected vaults and all the relative parts. This includes USDT/USDC new vaults, old vaults (the vault before the migration), the Uniswap USDT-fUSDT(old)/USDC-fUSDC(old) pairs, and their respective reward pools. 

On high level, we are converting all these holdings into the new vault shares, then use it to calculate how much a user has suffered from the attack. Here comes the detail.

A user could hold the following:
1. New vault shares in wallet
2. New vault shares staked in reward pools
3. Old vault shares in wallet
4. Old vault shares staked in reward pools
5. Uniswap LP tokens in wallet
6. Uniswap LP tokens staked in reward pools

As stakes in reward pools are 1 to 1 with the underlying asset, we aggregate their balance together to get user's holding of each token:
1. New vault shares
2. Old vault shares
3. Uniswap LP tokens (Old vault share / stable asset)

As an Uniswap pair token holds both the stable assets and the old vault shares, we calculate how many old vault shares does one Uniswap pair token hold at the given snapshot. This is calculated by:

* `(The number of old vault shares owned by 1 Uniswap LP Token) = oldVault.balanceOf(UniswapLPContract.address) / UniswapLPContract.totalSupply()`

Thus, user's holding of old vault share by those Uniswap LP token is:

* `(User's old vault shares by holding LP token) = UniswapLPContract.balanceOf(User) * (The number of old vault shares owned by 1 Uniswap LP Token)`

This is then aggregated with (2) the old vault shares. These shares then needs to be converted into the new vault shares, the conversion rate can be calculated by:

```
remainingLegacyShares = oldVault.totalSupply() - oldVault.balanceOf(newPool.address)
unmigratedNewShares = newVault.balanceOf(newPool.address) - newPool.totalSupply();
conversionRate = unmigratedNewShares / remainingLegacyShares
```

With the conversion rate, we can calculate the equivalent amount of new vault shares that the user holds via old vault shares and LP tokens and aggregate with (1). 
From the difference between the snapshot block and the block after the attack, we could calculate how much the protocol and each user suffered from the attack.

At this point we have the info for each user: the user lost `t` USDT & `c` USDC. We treat USDT and USDC as 1:1. 
The protocol lost `tLost` USDT and `cLost` USDC. The hacker sent back `tBack` USDT and `cBack` USDC. 
  
* `userRatio = (t+c)/(tLost+cLost)`

then the user should be able to claim:

* `tBack * userRatio` USDT, `cBack * userRatio` USDC, and `(tLost + cLost - tBack - cBack) * userRatio * 10^12` IOU.
  
10^12 is coming from converting 6 decimals to 18 decimals. (The IOU will be 18 decimals whereas both USDT and USDC are 6 decimals)