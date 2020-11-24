import json
import os
import requests
import math
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from functools import partial, wraps
from itertools import zip_longest
from pathlib import Path

import toml
from brownie import MerkleDistributor, Wei, accounts, interface, rpc, web3
from eth_abi import decode_single, encode_single
from eth_abi.packed import encode_abi_packed
from eth_utils import encode_hex
from toolz import valfilter, valmap
from tqdm import tqdm, trange
from click import secho

# USDC
FUSDC_TOTAL_DISTRIBUTION = 1761898396474 # cBack - https://etherscan.io/tx/0x25119cd54a4562aa427d9770af383512f9cb5e8e4d17232ad96b69dc293a3510#eventlog
FUSDC_LOST = 18541866517227 # Difference of underlyingBalanceWithInvestment on SNAPSHOT_BLOCK and USDC_END_BLOCK
FUSDC_BEFORE_HACK_EXPECTED_SHARE_PRICE = 980007
FUSDC_BEFORE_HACK_EXPECTED_UNDERLYING = 125037466425427 #underlyingBalanceWithInvestment on SNAPSHOT_BLOCK
FUSDC_AFTER_HACK_EXPECTED_SHARE_PRICE = 834681
FUSDC_AFTER_HACK_EXPECTED_UNDERLYING = 106495599908200 #underlyingBalanceWithInvestment on USDC_END_BLOCK
FUSDC_TOKEN_ADDRESS = '0xf0358e8c3CD5Fa238a29301d0bEa3D63A17bEdBE'
FUSDC_VAULT_ADDRESS = '0xf0358e8c3CD5Fa238a29301d0bEa3D63A17bEdBE'
FUSDC_REWARD_POOL_ADDRESS = '0x4F7c28cCb0F1Dbd1388209C67eEc234273C878Bd'
FUSDC_OLD_REWARD_POOL_ADDRESS = '0xE1f9A3EE001a2EcC906E8de637DBf20BB2d44633'
FUSDC_OLD_VAULT_ADDRESS = '0xc3F7ffb5d5869B3ade9448D094d81B0521e8326f'
FUSDC_LP_ADDRESS = '0x4161Fa43eaA1Ac3882aeeD12C5FC05249e533e67'
FUSDC_LP_POOL_ADDRESS = '0x43286F57cf5981a5db56828dF91a46CfAb983E58'


# USDT
FUSDT_TOTAL_DISTRIBUTION = 718914048541 # tBack - https://etherscan.io/tx/0x25119cd54a4562aa427d9770af383512f9cb5e8e4d17232ad96b69dc293a3510#eventlog
FUSDT_LOST = 14877563161132 # Difference of underlyingBalanceWithInvestment on SNAPSHOT_BLOCK and USDT_END_BLOCK (FUSDT_BEFORE_HACK_EXPECTED_UNDERLYING - FUSDT_AFTER_HACK_EXPECTED_UNDERLYING)
FUSDT_BEFORE_HACK_EXPECTED_SHARE_PRICE = 978874
FUSDT_BEFORE_HACK_EXPECTED_UNDERLYING = 108630659968404 #underlyingBalanceWithInvestment on SNAPSHOT_BLOCK
FUSDT_AFTER_HACK_EXPECTED_SHARE_PRICE = 844812
FUSDT_AFTER_HACK_EXPECTED_UNDERLYING = 93753096807272 #underlyingBalanceWithInvestment on USDT_END_BLOCK
FUSDT_TOKEN_ADDRESS = '0x053c80eA73Dc6941F518a68E2FC52Ac45BDE7c9C'
FUSDT_VAULT_ADDRESS = '0x053c80eA73Dc6941F518a68E2FC52Ac45BDE7c9C'
FUSDT_REWARD_POOL_ADDRESS = '0x6ac4a7AB91E6fD098E13B7d347c6d4d1494994a2'
FUSDT_OLD_VAULT_ADDRESS = '0xc7EE21406BB581e741FBb8B21f213188433D9f2F'
FUSDT_OLD_REWARD_POOL_ADDRESS = '0x5bd997039FFF16F653EF15D1428F2C791519f58d'
FUSDT_LP_ADDRESS = '0x713f62ccf8545Ff1Df19E5d7Ab94887cFaf95677'
FUSDT_LP_POOL_ADDRESS = '0x316De40F36da4C54AFf11C1D83081555Cca41270'

FYCRV_VAULT_ADDRESS = '0xF2B223Eb3d2B382Ead8D85f3c1b7eF87c1D35f3A'

# General
DEPLOYER_ADDRESS = '0x61C59b3c032B9c1b17B830694C52E84f9c47e23D'
USDC_ADDRESS = '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48'
USDT_ADDRESS = '0xdac17f958d2ee523a2206206994597c13d831ec7'
ZERO_ADDRESS = '0x0000000000000000000000000000000000000000'
BURN_ADDRESS = '0x000000000000000000000000000000000000dEaD'
TOTAL_RETURNED_AMOUNT = FUSDT_TOTAL_DISTRIBUTION + FUSDC_TOTAL_DISTRIBUTION
TOTAL_LOST_AMOUNT = FUSDC_LOST + FUSDT_LOST
IOU_AMOUNT = TOTAL_LOST_AMOUNT - TOTAL_RETURNED_AMOUNT
START_BLOCK_FUSDC = 11086843 # https://etherscan.io/tx/0xacd0a8e96cd869e0cc7eb5b96c125e665b58275dfdb58edf33792b6cfff78bca
START_BLOCK_FUSDT = 11086850 # https://etherscan.io/tx/0x7bafa93b78f26adb245446f90d7625da6d980a8f8f1566d99a6dd36b6e10e981
START_BLOCK_FUSDC_REWARDS = 11087161 # https://etherscan.io/tx/0x6d09a52066c085e69a9563269bcdb77fc51c77522f1fdea009defc4a1330c655
START_BLOCK_FUSDT_REWARDS = 11087165 # https://etherscan.io/tx/0x5584d15a40c8ba7d155efc034ed76e49e3a8e380bac631d239b2fb06fb36e467
START_BLOCK_FUSDC_OLD = 10770105 # https://etherscan.io/tx/0xa11f1fefdb74c79a720ec6f22e058fa108122bc7a3340e55d1342c49fabe490d
START_BLOCK_FUSDT_OLD = 10770108 # https://etherscan.io/tx/0x47cd99ee0f3b96621da0b8095cb4c7688eba9dbd9734ad920980ea1a8860ccd7
START_BLOCK_FUSDC_REWARDS_OLD = 10770214 # https://etherscan.io/tx/0xcd30031437e20b15ee822fbb030fe95f9eb9d231efcfabc18dd27b0ce2110df2
START_BLOCK_FUSDT_REWARDS_OLD = 10770216 # https://etherscan.io/tx/0x652df9027c55e5f31b57f201499954bdb5e6cbe08c5427ab648525fab3b451a4
START_BLOCK_LP_POOL_USDC = 10796744 # https://etherscan.io/tx/0xc6f4d5733a01eb40559991022fb804c5260382d1fd1fe246bda48b9f8b340c0c
START_BLOCK_LP_POOL_USDT = 10817080 # https://etherscan.io/tx/0xa4200282b2d6e80171555dc9be2b3c79abdc01447860ccd26243c2d42215622f
START_BLOCKS = [ START_BLOCK_FUSDC, START_BLOCK_FUSDT, START_BLOCK_FUSDC_REWARDS, START_BLOCK_FUSDT_REWARDS ]
START_BLOCKS_OLD = [ START_BLOCK_FUSDC_OLD, START_BLOCK_FUSDT_OLD, START_BLOCK_FUSDC_REWARDS_OLD, START_BLOCK_FUSDT_REWARDS_OLD ]
START_BLOCKS_LP_POOLS = [ START_BLOCK_LP_POOL_USDC, START_BLOCK_LP_POOL_USDT ]
START_BLOCK = min(START_BLOCKS) # 11086843
START_BLOCK_OLD = min(START_BLOCKS_OLD) # 10770105
START_BLOCK_LP_POOL = min(START_BLOCKS_LP_POOLS) # 10796744
SNAPSHOT_BLOCK = 11129473
END_BLOCK = 11129515
USDC_END_BLOCK = 11129500 # block after the last usdc attack https://etherscan.io/tx/0x3a06ef1cfd88d98be61a82c469c8c411417f92c5a9577446078874a72d71680f
USDT_END_BLOCK = 11129515 # block after the last usdt attack https://etherscan.io/tx/0x9d093325272701d63fdafb0af2d89c7e23eaf18be1a51c580d9bce89987a2dc1
FVAULT = interface.FVault(FUSDC_VAULT_ADDRESS)
UNISWAP_PAIR = interface.UniswapPair(FUSDC_LP_ADDRESS) # Same interface for FUSDT
FREWARD_POOL = interface.FRewardPool(FUSDC_REWARD_POOL_ADDRESS) # Same interface for FUSDT reward pool
FUSDC_LOST_RATIO = Fraction(FUSDC_BEFORE_HACK_EXPECTED_UNDERLYING - FUSDC_AFTER_HACK_EXPECTED_UNDERLYING, FUSDC_BEFORE_HACK_EXPECTED_UNDERLYING)
FUSDT_LOST_RATIO = Fraction(FUSDT_BEFORE_HACK_EXPECTED_UNDERLYING - FUSDT_AFTER_HACK_EXPECTED_UNDERLYING, FUSDT_BEFORE_HACK_EXPECTED_UNDERLYING)
FUSDC_REWARD_POOL_CONTRACT = web3.eth.contract(FUSDC_REWARD_POOL_ADDRESS, abi=FREWARD_POOL.abi)
FUSDT_REWARD_POOL_CONTRACT = web3.eth.contract(FUSDT_REWARD_POOL_ADDRESS, abi=FREWARD_POOL.abi)
FUSDC_OLD_REWARD_POOL_CONTRACT = web3.eth.contract(FUSDC_OLD_REWARD_POOL_ADDRESS, abi=FREWARD_POOL.abi)
FUSDT_OLD_REWARD_POOL_CONTRACT = web3.eth.contract(FUSDT_OLD_REWARD_POOL_ADDRESS, abi=FREWARD_POOL.abi)
FUSDC_LP_CONTRACT = web3.eth.contract(FUSDC_LP_ADDRESS, abi=UNISWAP_PAIR.abi)
FUSDT_LP_CONTRACT = web3.eth.contract(FUSDT_LP_ADDRESS, abi=UNISWAP_PAIR.abi)
FUSDC_LP_POOL_CONTRACT = web3.eth.contract(FUSDC_LP_POOL_ADDRESS, abi=UNISWAP_PAIR.abi)
FUSDT_LP_POOL_CONTRACT = web3.eth.contract(FUSDT_LP_POOL_ADDRESS, abi=UNISWAP_PAIR.abi)
FYCRV_VAULT_CONTRACT = web3.eth.contract(FYCRV_VAULT_ADDRESS, abi=FVAULT.abi)
FUSDC_VAULT_CONTRACT = web3.eth.contract(FUSDC_VAULT_ADDRESS, abi=FVAULT.abi)
FUSDT_VAULT_CONTRACT = web3.eth.contract(FUSDT_VAULT_ADDRESS, abi=FVAULT.abi)
FUSDC_OLD_VAULT_CONTRACT = web3.eth.contract(FUSDC_OLD_VAULT_ADDRESS, abi=FVAULT.abi)
FUSDT_OLD_VAULT_CONTRACT = web3.eth.contract(FUSDT_OLD_VAULT_ADDRESS, abi=FVAULT.abi)

FUSDC_TOTAL_SUPPLY_AT_SNAPSHOT = FUSDC_VAULT_CONTRACT.functions.totalSupply().call({}, SNAPSHOT_BLOCK) 
FUSDT_TOTAL_SUPPLY_AT_SNAPSHOT = FUSDT_VAULT_CONTRACT.functions.totalSupply().call({}, SNAPSHOT_BLOCK)
FUSDC_REWARD_POOL_TOTAL_SUPPLY_AT_SNAPSHOT = FUSDC_REWARD_POOL_CONTRACT.functions.totalSupply().call({}, SNAPSHOT_BLOCK)
FUSDT_REWARD_POOL_TOTAL_SUPPLY_AT_SNAPSHOT = FUSDT_REWARD_POOL_CONTRACT.functions.totalSupply().call({}, SNAPSHOT_BLOCK)
FUSDC_LP_TOTAL_SUPPLY_AT_SNAPSHOT = FUSDC_LP_CONTRACT.functions.totalSupply().call({}, SNAPSHOT_BLOCK)
FUSDT_LP_TOTAL_SUPPLY_AT_SNAPSHOT = FUSDT_LP_CONTRACT.functions.totalSupply().call({}, SNAPSHOT_BLOCK)
FUSDC_OLD_REWARD_POOL_TOTAL_SUPPLY_AT_SNAPSHOT = FUSDC_OLD_REWARD_POOL_CONTRACT.functions.totalSupply().call({}, SNAPSHOT_BLOCK)
FUSDT_OLD_REWARD_POOL_TOTAL_SUPPLY_AT_SNAPSHOT = FUSDT_OLD_REWARD_POOL_CONTRACT.functions.totalSupply().call({}, SNAPSHOT_BLOCK)
FUSDC_OLD_VAULT_TOTAL_SUPPLY_AT_SNAPSHOT = FUSDC_OLD_VAULT_CONTRACT.functions.totalSupply().call({}, SNAPSHOT_BLOCK)
FUSDT_OLD_VAULT_TOTAL_SUPPLY_AT_SNAPSHOT = FUSDT_OLD_VAULT_CONTRACT.functions.totalSupply().call({}, SNAPSHOT_BLOCK)
# FUSDC_OLD_MIGRATED = FUSDC_OLD_VAULT_CONTRACT.functions.balanceOf(FUSDC_REWARD_POOL_ADDRESS).call({}, SNAPSHOT_BLOCK)
# FUSDT_OLD_MIGRATED = FUSDT_OLD_VAULT_CONTRACT.functions.balanceOf(FUSDT_REWARD_POOL_ADDRESS).call({}, SNAPSHOT_BLOCK)
# FUSDT_LP_POOL_TOTAL_SUPPLY = FUSDT_LP_POOL_CONTRACT.functions.totalSupply().call({}, SNAPSHOT_BLOCK)
# FUSDC_LP_POOL_TOTAL_SUPPLY = FUSDC_LP_POOL_CONTRACT.functions.totalSupply().call({}, SNAPSHOT_BLOCK)
# ETHERSCAN_API_KEY = 'GEQXZDY67RZ4QHNU1A57QVPNDV3RP1RYH4'
# FUSDC_REWARD_POOL_TRANSACTIONS = requests.get(f'https://api.etherscan.io/api?module=account&action=txlist&address={FUSDC_REWARD_POOL_ADDRESS}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}').json()['result']
# FUSDT_REWARD_POOL_TRANSACTIONS = requests.get(f'https://api.etherscan.io/api?module=account&action=txlist&address={FUSDT_REWARD_POOL_ADDRESS}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}').json()['result']
# FUSDC_OLD_REWARD_POOL_TRANSACTIONS = requests.get(f'https://api.etherscan.io/api?module=account&action=txlist&address={FUSDC_OLD_REWARD_POOL_ADDRESS}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}').json()['result']
# FUSDC_OLD_REWARD_POOL_TRANSACTIONS_INTERNAL = requests.get(f'https://api.etherscan.io/api?module=account&action=txlistinternal&address={FUSDC_OLD_REWARD_POOL_ADDRESS}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}').json()['result']
# FUSDT_OLD_REWARD_POOL_TRANSACTIONS = requests.get(f'https://api.etherscan.io/api?module=account&action=txlist&address={FUSDT_OLD_REWARD_POOL_ADDRESS}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}').json()['result']
# FUSDC_LP_TRANSACTIONS = requests.get(f'https://api.etherscan.io/api?module=account&action=tokentx&contractaddress={FUSDC_LP_ADDRESS}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}').json()['result']
# FUSDT_LP_TRANSACTIONS = requests.get(f'https://api.etherscan.io/api?module=account&action=tokentx&contractaddress={FUSDT_LP_ADDRESS}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}').json()['result']
# FUSDC_LP_POOL_TRANSACTIONS = requests.get(f'https://api.etherscan.io/api?module=account&action=txlist&address={FUSDC_LP_POOL_ADDRESS}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}').json()['result']
# FUSDC_LP_POOL_TRANSACTIONS_TOKENS = requests.get(f'https://api.etherscan.io/api?module=account&action=tokentx&address={FUSDC_LP_POOL_ADDRESS}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}').json()['result']
# FUSDT_LP_POOL_TRANSACTIONS_TOKENS = requests.get(f'https://api.etherscan.io/api?module=account&action=tokentx&address={FUSDT_LP_POOL_ADDRESS}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}').json()['result']
# FUSDT_LP_POOL_TRANSACTIONS = requests.get(f'https://api.etherscan.io/api?module=account&action=txlist&address={FUSDT_LP_POOL_ADDRESS}&startblock=0&endblock=99999999&sort=asc&apikey={ETHERSCAN_API_KEY}').json()['result']
# USDC = interface.ERC20(USDC_ADDRESS)
# USDT = interface.ERC20(USDT_ADDRESS)

VAULTS = {
    'fUSDT': FUSDT_VAULT_ADDRESS,
    'fUSDC': FUSDC_VAULT_ADDRESS
}

VAULTS_OLD = {
    'fUSDT': FUSDT_OLD_VAULT_ADDRESS,
    'fUSDC': FUSDC_OLD_VAULT_ADDRESS
}

REWARD_POOLS = {
    'fUSDT': FUSDT_REWARD_POOL_ADDRESS,
    'fUSDC': FUSDC_REWARD_POOL_ADDRESS
}

LP_TOKENS = {
    'fUSDC': FUSDC_LP_ADDRESS,
    'fUSDT': FUSDT_LP_ADDRESS
}

LP_REWARD_POOLS = {
    'fUSDT': FUSDT_LP_POOL_ADDRESS,
    'fUSDC': FUSDC_LP_POOL_ADDRESS
}

REWARD_POOLS_OLD = {
    'fUSDT': FUSDT_OLD_REWARD_POOL_ADDRESS,
    'fUSDC': FUSDC_OLD_REWARD_POOL_ADDRESS
}

def uniqueAddressesForTransactions(transactions, transactions2):
  accounts = Counter()
  for transaction in transactions:
    accounts[transaction['from']] = True
    if transaction['to']:
        accounts[transaction['to']] = True
  for transaction in transactions2:
    accounts[transaction['from']] = True
    if transaction['to']:
        accounts[transaction['to']] = True
  return accounts.keys()

# FUSDC_REWARD_POOL_TX_ADDRESSES = uniqueAddressesForTransactions(FUSDC_REWARD_POOL_TRANSACTIONS,[])
# FUSDT_REWARD_POOL_TX_ADDRESSES = uniqueAddressesForTransactions(FUSDT_REWARD_POOL_TRANSACTIONS,[])
# FUSDT_OLD_REWARD_POOL_TX_ADDRESSES = uniqueAddressesForTransactions(FUSDT_OLD_REWARD_POOL_TRANSACTIONS,[])
# FUSDC_OLD_REWARD_POOL_TX_ADDRESSES = uniqueAddressesForTransactions(FUSDC_OLD_REWARD_POOL_TRANSACTIONS, FUSDC_OLD_REWARD_POOL_TRANSACTIONS_INTERNAL)
# FUSDT_LP_TX_ADDRESSES = uniqueAddressesForTransactions(FUSDT_LP_TRANSACTIONS,[])
# FUSDC_LP_TX_ADDRESSES = uniqueAddressesForTransactions(FUSDC_LP_TRANSACTIONS,[])
# FUSDT_LP_POOL_TX_ADDRESSES = uniqueAddressesForTransactions(FUSDT_LP_POOL_TRANSACTIONS, FUSDT_LP_POOL_TRANSACTIONS_TOKENS)
# FUSDC_LP_POOL_TX_ADDRESSES = uniqueAddressesForTransactions(FUSDC_LP_POOL_TRANSACTIONS, FUSDC_LP_POOL_TRANSACTIONS_TOKENS)

def cached(path):
    path = Path(path)
    codec = {'.toml': toml, '.json': json}[path.suffix]
    codec_args = {'.json': {'indent': 2}}.get(path.suffix, {})

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if path.exists():
                print('Load file from cache', path)
                return codec.loads(path.read_text())
            else:
                result = func(*args, **kwargs)
                os.makedirs(path.parent, exist_ok=True)
                path.write_text(codec.dumps(result, **codec_args))
                print('Write file to cache', path)
                return result

        return wrapper

    return decorator

def testTokenBalances(tokenBalanceMap, startBlock):
  print("Testing token balances")
  for tokenSymbol, balances in tokenBalanceMap.items():
      contract = None
      if tokenSymbol == 'fUSDC':
        if startBlock == START_BLOCK:
          contract = FUSDC_VAULT_CONTRACT
        else:
          contract = FUSDC_OLD_VAULT_CONTRACT
      elif tokenSymbol == 'fUSDT':
        if startBlock == START_BLOCK:
          contract = FUSDT_VAULT_CONTRACT
        else:
          contract = FUSDT_OLD_VAULT_CONTRACT
      
      for accountAddress, accountTokenBalance in balances.items():
        userBalanceAtSnapshot = contract.functions.balanceOf(accountAddress).call({}, SNAPSHOT_BLOCK)
        print(f'Testing {tokenSymbol} balance for user {accountAddress}. Expected: {accountTokenBalance}, Actual: {userBalanceAtSnapshot}')
        assert userBalanceAtSnapshot == accountTokenBalance

def testTotalStaked(tokenBalanceMap, startBlock):
  print("Testing total staked per rewards pool")
  for tokenSymbol, balances in tokenBalanceMap.items():
      contract = None
      rewardPoolBalances = Counter()
      for accountAddress, stakedBalance in balances.items():
          rewardPoolBalances[tokenSymbol] += stakedBalance
      rewardPoolBalanceCalculated = rewardPoolBalances[tokenSymbol]
      if tokenSymbol == 'fUSDC':
          if startBlock == START_BLOCK:
              rewardPoolBalanceActual = FUSDC_REWARD_POOL_TOTAL_SUPPLY_AT_SNAPSHOT
          elif startBlock == START_BLOCK_LP_POOL:
              rewardPoolBalanceActual = FUSDC_LP_POOL_TOTAL_SUPPLY
          else:
              rewardPoolBalanceActual = FUSDC_OLD_REWARD_POOL_TOTAL_SUPPLY_AT_SNAPSHOT

      elif tokenSymbol == 'fUSDT':
          if startBlock == START_BLOCK:
              rewardPoolBalanceActual = FUSDT_REWARD_POOL_TOTAL_SUPPLY_AT_SNAPSHOT
          elif startBlock == START_BLOCK_LP_POOL:
              rewardPoolBalanceActual = FUSDT_LP_POOL_TOTAL_SUPPLY
          else:
              rewardPoolBalanceActual = FUSDT_OLD_REWARD_POOL_TOTAL_SUPPLY_AT_SNAPSHOT

      print(f'Testing total staked for {tokenSymbol}. Calculated: {rewardPoolBalanceCalculated}, Actual: {rewardPoolBalanceActual}')
      if tokenSymbol == 'fUSDC' and startBlock == START_BLOCK_OLD:
          tolerance = 41000 # 41 USDC tolerance to account for ~40 USDC difference edge case (old fUSDC reward pool)
          assert equalWithTolerance(rewardPoolBalanceCalculated, rewardPoolBalanceActual, tolerance)
      else:
          assert rewardPoolBalanceCalculated == rewardPoolBalanceActual

def transfers_to_balances(address, startBlock):
    accountBalances = Counter()
    contract = web3.eth.contract(address, abi=UNISWAP_PAIR.abi)
    for start in trange(startBlock, SNAPSHOT_BLOCK, 1000):
        end = min(start + 999, SNAPSHOT_BLOCK)
        logs = contract.events.Transfer().getLogs(fromBlock=start, toBlock=end)
        for log in logs:
            fromAddress = log['args']['from']
            toAddress = log['args']['to']
            value = log['args']['value']
            if fromAddress != ZERO_ADDRESS:
                accountBalances[fromAddress] -= value
            if toAddress != ZERO_ADDRESS:
                accountBalances[toAddress] += value

    # Delete LP/staker balances, we account for these in another step
    del accountBalances[FUSDC_REWARD_POOL_ADDRESS]
    del accountBalances[FUSDC_LP_ADDRESS]
    del accountBalances[FUSDC_OLD_REWARD_POOL_ADDRESS]
    del accountBalances[BURN_ADDRESS]
    del accountBalances[FUSDT_REWARD_POOL_ADDRESS]
    del accountBalances[FUSDT_LP_ADDRESS]
    del accountBalances[FUSDT_OLD_REWARD_POOL_ADDRESS]
    del accountBalances[BURN_ADDRESS]

    return valfilter(bool, dict(accountBalances.most_common()))

def stakers_to_balances(rewardPoolAddress):
    balances = Counter()
    rewardPoolContract = web3.eth.contract(rewardPoolAddress, abi=FREWARD_POOL.abi)
    rewardPoolAccounts = []
    if rewardPoolAddress == FUSDT_REWARD_POOL_ADDRESS:
        rewardPoolAccounts = FUSDT_REWARD_POOL_TX_ADDRESSES
    elif rewardPoolAddress == FUSDC_REWARD_POOL_ADDRESS:
        rewardPoolAccounts = FUSDC_REWARD_POOL_TX_ADDRESSES
    elif rewardPoolAddress == FUSDC_OLD_REWARD_POOL_ADDRESS:
        rewardPoolAccounts = FUSDC_OLD_REWARD_POOL_TX_ADDRESSES
    elif rewardPoolAddress == FUSDT_OLD_REWARD_POOL_ADDRESS:
        rewardPoolAccounts = FUSDT_OLD_REWARD_POOL_TX_ADDRESSES
    elif rewardPoolAddress == FUSDC_LP_POOL_ADDRESS:
        rewardPoolAccounts = FUSDC_LP_POOL_TX_ADDRESSES
    elif rewardPoolAddress == FUSDT_LP_POOL_ADDRESS:
        rewardPoolAccounts = FUSDT_LP_POOL_TX_ADDRESSES

    for accountAddress in tqdm(rewardPoolAccounts):
        accountAddressChecksum = web3.toChecksumAddress(accountAddress)
        balances[accountAddress] = rewardPoolContract.functions.balanceOf(accountAddressChecksum).call({}, SNAPSHOT_BLOCK)
    return valfilter(bool, dict(balances.most_common()))

def lp_to_balances(pairAddress):
    balances = Counter()
    lpAccounts = []
    contract = None
    if pairAddress == FUSDC_LP_ADDRESS:
        lpAccounts = FUSDC_LP_TX_ADDRESSES
        contract = FUSDC_LP_CONTRACT
    elif pairAddress == FUSDT_LP_ADDRESS:
        lpAccounts = FUSDT_LP_TX_ADDRESSES
        contract = FUSDT_LP_CONTRACT

    for accountAddress in tqdm(lpAccounts):
        accountAddressChecksum = web3.toChecksumAddress(accountAddress)
        userBalance = contract.functions.balanceOf(accountAddressChecksum).call({}, SNAPSHOT_BLOCK)
        print(f'user bal', accountAddress, userBalance)
        balances[accountAddress] = userBalance
    return valfilter(bool, dict(balances.most_common()))

def generateMerkleDistribution(aggregatedBalances):
    elements = [(index, account, amount) for index, (account, amount) in enumerate(aggregatedBalances.items())]
    nodes = [encode_hex(encode_abi_packed(['uint', 'address', 'uint'], el)) for el in elements]
    tree = MerkleTree(nodes)
    distribution = {
        'merkleRoot': encode_hex(tree.root),
        'tokenTotal': hex(sum(aggregatedBalances.values())),
        'claims': {
            user: {'index': index, 'amount': hex(amount), 'proof': tree.get_proof(nodes[index])}
            for index, user, amount in elements
        },
    }
    print(f'merkle root: {encode_hex(tree.root)}')
    return distribution


def equalWithTolerance(val1, val2, tolerance):
    return abs(val1 - val2) <= tolerance

class MerkleTree:
    def __init__(self, elements):
        self.elements = sorted(set(web3.keccak(hexstr=el) for el in elements))
        self.layers = MerkleTree.get_layers(self.elements)

    @property
    def root(self):
        return self.layers[-1][0]

    def get_proof(self, el):
        el = web3.keccak(hexstr=el)
        idx = self.elements.index(el)
        proof = []
        for layer in self.layers:
            pair_idx = idx + 1 if idx % 2 == 0 else idx - 1
            if pair_idx < len(layer):
                proof.append(encode_hex(layer[pair_idx]))
            idx //= 2
        return proof

    @staticmethod
    def get_layers(elements):
        layers = [elements]
        while len(layers[-1]) > 1:
            layers.append(MerkleTree.get_next_layer(layers[-1]))
        return layers

    @staticmethod
    def get_next_layer(elements):
        return [MerkleTree.combined_hash(a, b) for a, b in zip_longest(elements[::2], elements[1::2])]

    @staticmethod
    def combined_hash(a, b):
        if a is None:
            return b
        if b is None:
            return a
        return web3.keccak(b''.join(sorted([a, b])))


def step_00():
  print('Step 00. Test snapshot expectations.')
  print("")
  print("YCRV TESTS");
  print("----------");
  beforeYCRVSharePrice = FYCRV_VAULT_CONTRACT.functions.getPricePerFullShare().call({}, SNAPSHOT_BLOCK)
  afterYCRVSharePrice = FYCRV_VAULT_CONTRACT.functions.getPricePerFullShare().call({}, USDC_END_BLOCK)
  beforeYCRVTotalSupply = FYCRV_VAULT_CONTRACT.functions.totalSupply().call({}, SNAPSHOT_BLOCK)
  afterYCRVTotalSupply = FYCRV_VAULT_CONTRACT.functions.totalSupply().call({}, USDC_END_BLOCK)
  print("beforeYCRVSharePrice              ", beforeYCRVSharePrice)
  print("afterYCRVSharePrice               ", afterYCRVSharePrice)
  print("beforeYCRVTotalSupply             ", beforeYCRVTotalSupply)
  print("afterYCRVTotalSupply              ", afterYCRVTotalSupply)

  # USDC
  print("")
  print("USDC TESTS");
  print("----------");
  snapshotBlockUsdcPricePerFullShare = FUSDC_VAULT_CONTRACT.functions.getPricePerFullShare().call({}, SNAPSHOT_BLOCK)
  snapshotBlockUsdcBalance = FUSDC_VAULT_CONTRACT.functions.underlyingBalanceWithInvestment().call({}, SNAPSHOT_BLOCK)
  endBlockUsdcPricePerFullShare = FUSDC_VAULT_CONTRACT.functions.getPricePerFullShare().call({}, USDC_END_BLOCK)
  endBlockUsdcBalance = FUSDC_VAULT_CONTRACT.functions.underlyingBalanceWithInvestment().call({}, USDC_END_BLOCK)

  snapshotBlockUsdcTotalUnderlying = FUSDC_VAULT_CONTRACT.functions.totalSupply().call({}, SNAPSHOT_BLOCK) * snapshotBlockUsdcPricePerFullShare
  endBlockUsdcTotalUnderlying = FUSDC_VAULT_CONTRACT.functions.totalSupply().call({}, USDC_END_BLOCK) * endBlockUsdcPricePerFullShare

  print("Total distribution amount         ", FUSDC_TOTAL_DISTRIBUTION)
  print("Snapshot block:                   ", SNAPSHOT_BLOCK)
  print("Snapshot block pricePerFullShare: ", snapshotBlockUsdcPricePerFullShare)
  print("Snapshot block balance:           ", snapshotBlockUsdcBalance)
  print("Snapshot block totalSupply:       ", FUSDC_REWARD_POOL_TOTAL_SUPPLY_AT_SNAPSHOT)
  print("End block:                        ", END_BLOCK)
  print("USDC End block:                   ", USDC_END_BLOCK)
  print("End block pricePerFullShare:      ", endBlockUsdcPricePerFullShare)
  print("End block balance:                ", endBlockUsdcBalance)
  print("Lost ratio                        ", FUSDC_LOST_RATIO)
  print("Damage                            ", snapshotBlockUsdcBalance - endBlockUsdcBalance)
  print("snapshotBlockUsdcTotalUnderlying  ", snapshotBlockUsdcTotalUnderlying)
  print("endBlockUsdcTotalUnderlying       ", endBlockUsdcTotalUnderlying)
  
  print("")
  assert snapshotBlockUsdcPricePerFullShare == FUSDC_BEFORE_HACK_EXPECTED_SHARE_PRICE
  assert snapshotBlockUsdcBalance == FUSDC_BEFORE_HACK_EXPECTED_UNDERLYING
  assert endBlockUsdcPricePerFullShare == FUSDC_AFTER_HACK_EXPECTED_SHARE_PRICE
  assert endBlockUsdcBalance == FUSDC_AFTER_HACK_EXPECTED_UNDERLYING

  # USDT 
  print("USDT TESTS");
  print("----------");
  snapshotBlockUsdcPricePerFullShare = FUSDT_VAULT_CONTRACT.functions.getPricePerFullShare().call({}, SNAPSHOT_BLOCK)
  snapshotBlockUsdcBalance = FUSDT_VAULT_CONTRACT.functions.underlyingBalanceWithInvestment().call({}, SNAPSHOT_BLOCK)
  endBlockUsdcPricePerFullShare = FUSDT_VAULT_CONTRACT.functions.getPricePerFullShare().call({}, USDT_END_BLOCK)
  endBlockUsdcBalance = FUSDT_VAULT_CONTRACT.functions.underlyingBalanceWithInvestment().call({}, USDT_END_BLOCK)
  print("Total distribution amount         ", FUSDT_TOTAL_DISTRIBUTION)
  print("Snapshot block:                   ", SNAPSHOT_BLOCK)
  print("Snapshot block pricePerFullShare: ", snapshotBlockUsdcPricePerFullShare)
  print("Snapshot block balance:           ", snapshotBlockUsdcBalance)
  print("Snapshot block totalSupply:       ", FUSDT_REWARD_POOL_TOTAL_SUPPLY_AT_SNAPSHOT)
  print("USDT End block:                   ", USDT_END_BLOCK)
  print("End block pricePerFullShare:      ", endBlockUsdcPricePerFullShare)
  print("End block balance:                ", endBlockUsdcBalance)
  print("Lost ratio                        ", FUSDT_LOST_RATIO)
  print("Damage                            ", snapshotBlockUsdcBalance - endBlockUsdcBalance)
  print("")
  assert snapshotBlockUsdcPricePerFullShare == FUSDT_BEFORE_HACK_EXPECTED_SHARE_PRICE
  assert snapshotBlockUsdcBalance == FUSDT_BEFORE_HACK_EXPECTED_UNDERLYING
  assert endBlockUsdcPricePerFullShare == FUSDT_AFTER_HACK_EXPECTED_SHARE_PRICE
  assert endBlockUsdcBalance == FUSDT_AFTER_HACK_EXPECTED_UNDERLYING
  assert FUSDT_LOST == FUSDT_BEFORE_HACK_EXPECTED_UNDERLYING - FUSDT_AFTER_HACK_EXPECTED_UNDERLYING

  # General
  print("GENERAL TESTS");
  print("-------------");
  print("Total returned amount:            ", TOTAL_RETURNED_AMOUNT)
  print("Total lost amount:                ", TOTAL_LOST_AMOUNT)
  print("Total IOU amount:                 ", TOTAL_LOST_AMOUNT - TOTAL_RETURNED_AMOUNT)
  print("")

  assert TOTAL_RETURNED_AMOUNT == 2480812445015
  assert TOTAL_LOST_AMOUNT - TOTAL_RETURNED_AMOUNT == 30938617233344
  assert TOTAL_LOST_AMOUNT - TOTAL_RETURNED_AMOUNT == IOU_AMOUNT

def calculateVaultUserBalances(vaults, startBlock):
    balances = defaultdict(Counter)  # token -> user -> balance
    for name, address in vaults.items():
        print(f'Processing token balances for {name} {address}')
        balances[name] = transfers_to_balances(str(address), startBlock)
        assert min(balances[name].values()) >= 0, 'negative balances found'
    testTokenBalances(balances, startBlock)
    return balances

def calculateVaultStakerBalances(rewardPools, startBlock):
    stakerBalances = defaultdict(Counter)
    for tokenSymbol, rewardPoolAddress in rewardPools.items():
        print(f'Processing rewards pool {tokenSymbol} {rewardPoolAddress}')
        stakerBalances[tokenSymbol] = stakers_to_balances(str(rewardPoolAddress))
        assert min(stakerBalances[tokenSymbol].values()) >= 0, 'negative balances found'
    testTotalStaked(stakerBalances, startBlock)
    return stakerBalances

def calculateLpBalances(pools, startBlock):
    lpBalances = defaultdict(Counter)
    for tokenSymbol, address in pools.items():
        print(f'Processing LP transfers for {tokenSymbol} {address}')
        lpBalances[tokenSymbol] = lp_to_balances(str(address))
        assert min(lpBalances[tokenSymbol].values()) >= 0, 'negative balances found'
    return lpBalances

def aggregateData(mapOne, mapTwo):
    print('\r\nAggregating balances')
    mapOneSum = sum(mapOne['fUSDC'].values()) + sum(mapOne['fUSDT'].values())
    mapTwoSum = sum(mapTwo['fUSDC'].values()) + sum(mapTwo['fUSDT'].values())
    totalSum = mapOneSum + mapTwoSum
    aggregatedBalances = Counter(mapOne)
    for tokenSymbol, balances in mapTwo.items():
        for accountAddress, amount in balances.items():
            accountAddressChecksummed = web3.toChecksumAddress(accountAddress)
            previousAmount = aggregatedBalances[tokenSymbol].get(accountAddressChecksummed)
            if previousAmount:
                newAmount = previousAmount + amount
                print(f'Aggregating {tokenSymbol} amount for user {accountAddressChecksummed}')
                print(f'    Previous amount: {previousAmount}')
                print(f'    Staked amount: {amount}')
                print(f'    Aggregated amount: {newAmount}\r\n')
            else:
                newAmount = amount
            aggregatedBalances[tokenSymbol][accountAddressChecksummed] = newAmount
    aggregatedSum = sum(aggregatedBalances['fUSDC'].values()) + sum(aggregatedBalances['fUSDT'].values())
    print(f'Aggregated sum: ', aggregatedSum)
    assert aggregatedSum == totalSum
    return aggregatedBalances


@cached('snapshot/01-balances.toml')
def step_01():
    print('Step 01. Calculate token balance of every user at snapshot')
    balances = calculateVaultUserBalances(VAULTS, START_BLOCK)
    return balances;


@cached('snapshot/02-stakers.toml')
def step_02():
    print('\r\nStep 02. Calculate total amount staked per user at snapshot')
    stakerBalances = calculateVaultStakerBalances(REWARD_POOLS, START_BLOCK)
    return stakerBalances

@cached('snapshot/03-aggregated-balances.toml')
def step_03(tokenBalanceMap, stakerBalanceMap):
    print("Step 03. Aggregate balances from step 2 and 3")
    aggregatedBalances = aggregateData(tokenBalanceMap, stakerBalanceMap)
    return aggregatedBalances

@cached('snapshot/04-balances-old.toml')
def step_04():
    print('Step 04. Calculate old token balance of every user at snapshot')
    balances = calculateVaultUserBalances(VAULTS_OLD, START_BLOCK_OLD)
    fusdcSum = sum(balances['fUSDC'].values()) 
    fusdtSum = sum(balances['fUSDT'].values())
    print(f'FUSDC Sum: ', fusdcSum)
    print(f'FUSDT Sum: ', fusdtSum)
    return balances;

@cached('snapshot/05-stakers-old.toml')
def step_05():
    print('\r\nStep 05. Calculate old total amount staked per user at snapshot')
    stakerBalances = calculateVaultStakerBalances(REWARD_POOLS_OLD, START_BLOCK_OLD)
    fusdcSum = sum(stakerBalances['fUSDC'].values()) 
    fusdtSum = sum(stakerBalances['fUSDT'].values())
    print(f'FUSDC Sum: ', fusdcSum)
    print(f'FUSDT Sum: ', fusdtSum)
    return stakerBalances

@cached('snapshot/06-aggregated-balances-old.toml')
def step_06(tokenBalanceMap, stakerBalanceMap):
    print(f'\r\nStep 06. Aggregate old pool and vault balances')
    aggregatedBalances = aggregateData(tokenBalanceMap, stakerBalanceMap)
    return aggregatedBalances

@cached('snapshot/07-lp-balances.toml')
def step_07():
    print('Step 07. Find LP token holders')
    balances = calculateLpBalances(LP_TOKENS, START_BLOCK_LP_POOL)

    # Make sure calculated balances match LP totalSupply
    fusdcLpBalanceSummation = sum(balances['fUSDC'].values())
    fusdtLpBalanceSummation = sum(balances['fUSDT'].values())
    print(f'Expected: {FUSDC_LP_TOTAL_SUPPLY_AT_SNAPSHOT}, Actual: {fusdcLpBalanceSummation}')
    print(f'Expected: {FUSDT_LP_TOTAL_SUPPLY_AT_SNAPSHOT}, Actual: {fusdtLpBalanceSummation}')
    assert fusdcLpBalanceSummation == FUSDC_LP_TOTAL_SUPPLY_AT_SNAPSHOT
    assert fusdtLpBalanceSummation == FUSDT_LP_TOTAL_SUPPLY_AT_SNAPSHOT
    return balances;

@cached('snapshot/08-lp-pool-balances.toml')
def step_08():
    print('Step 08. Find LP token stakers')
    stakerBalances = calculateVaultStakerBalances(LP_REWARD_POOLS, START_BLOCK_LP_POOL)
    fusdcLpStakerBalanceSummation = sum(stakerBalances['fUSDC'].values())
    fusdtLpStakerBalanceSummation = sum(stakerBalances['fUSDT'].values())
    assert fusdcLpStakerBalanceSummation == FUSDC_LP_POOL_TOTAL_SUPPLY
    assert fusdtLpStakerBalanceSummation == FUSDT_LP_POOL_TOTAL_SUPPLY
    return stakerBalances;

@cached('snapshot/09-aggregated-lp-balances.toml')
def step_09(lpBalanceMap, lpPoolBalanceMap):
    print('Step 09. Aggregate LP stakers and holders')
    aggregatedLpBalances = aggregateData(lpBalanceMap, lpPoolBalanceMap)
    del aggregatedLpBalances['fUSDC'][FUSDC_LP_POOL_ADDRESS.lower()]
    del aggregatedLpBalances['fUSDT'][FUSDT_LP_POOL_ADDRESS.lower()]
    
    print("aggregatedLpBalances fUSDC sum             ", sum(aggregatedLpBalances['fUSDC'].values()))
    print("FUSDC_LP_TOTAL_SUPPLY_AT_SNAPSHOT          ", FUSDC_LP_TOTAL_SUPPLY_AT_SNAPSHOT)
    print("aggregatedLpBalances fUSDT sum             ", sum(aggregatedLpBalances['fUSDT'].values()))
    print("FUSDT_LP_TOTAL_SUPPLY_AT_SNAPSHOT          ", FUSDT_LP_TOTAL_SUPPLY_AT_SNAPSHOT)
    
    fUsdcLpTokenBalanceOf = FUSDC_LP_CONTRACT.functions.balanceOf(FUSDC_LP_POOL_ADDRESS).call({}, SNAPSHOT_BLOCK)
    fUsdcLpAdjustment = fUsdcLpTokenBalanceOf - FUSDC_LP_POOL_TOTAL_SUPPLY
    fusdcLpBalanceSummation = sum(aggregatedLpBalances['fUSDC'].values())
    fusdtLpBalanceSummation = sum(aggregatedLpBalances['fUSDT'].values())

    assert fusdcLpBalanceSummation == (FUSDC_LP_TOTAL_SUPPLY_AT_SNAPSHOT - fUsdcLpAdjustment)
    assert fusdtLpBalanceSummation == FUSDT_LP_TOTAL_SUPPLY_AT_SNAPSHOT  

    return aggregatedLpBalances

def equalWithTolerance(val1, val2, tolerance):
    percentDifference = abs(val1 - val2) / ((val1 + val2) / 2)
    return percentDifference <= tolerance

@cached('snapshot/10-lp-balance-f-token-equivalent.toml')
def step_10(lpBalanceMap):
    print("Step 10. Find LP holder/staker fToken equivalents")
    fUsdcLpBalance = FUSDC_OLD_VAULT_CONTRACT.functions.balanceOf(FUSDC_LP_ADDRESS).call({}, SNAPSHOT_BLOCK)
    fUsdtLpBalance = FUSDT_OLD_VAULT_CONTRACT.functions.balanceOf(FUSDT_LP_ADDRESS).call({}, SNAPSHOT_BLOCK)
    fUsdcLpTokenBalanceOf = FUSDC_LP_CONTRACT.functions.balanceOf(FUSDC_LP_POOL_ADDRESS).call({}, SNAPSHOT_BLOCK)
    fUsdtLpTokenBalanceOf = FUSDT_LP_CONTRACT.functions.balanceOf(FUSDT_LP_POOL_ADDRESS).call({}, SNAPSHOT_BLOCK)
    print(f'fUsdcLp holds fUSDC:                       ', fUsdcLpBalance)
    print(f'fUsdtLp holds fUSDT:                       ', fUsdtLpBalance)
    print(f'fUsdcLpTokenBalanceOf:                ', fUsdcLpTokenBalanceOf)
    print(f'fUsdtLpTokenBalanceOf:                ', fUsdtLpTokenBalanceOf)
    print(f'FUSDC_LP_TOTAL_SUPPLY_AT_SNAPSHOT     ', FUSDC_LP_TOTAL_SUPPLY_AT_SNAPSHOT)
    
    # there are some users who sent the lpTokens to the contract directly
    fUsdcLpAdjustment = fUsdcLpTokenBalanceOf - FUSDC_LP_POOL_TOTAL_SUPPLY
    usdcLpTotal = 0
    usdtLpTotal = 0
    lpFTokenBalances = defaultdict(Counter)
    usdcFractionSum = 0
    usdcTotalBalance = 0
    for tokenSymbol, balances in lpBalanceMap.items():
        for accountAddress, balance in balances.items():
            if tokenSymbol == 'fUSDC':
                usdcTotalBalance += balance
                usdcFractionSum += Fraction(balance, FUSDC_LP_TOTAL_SUPPLY_AT_SNAPSHOT)
                lpFTokenBalance = math.floor(float(Fraction(balance * fUsdcLpBalance, FUSDC_LP_TOTAL_SUPPLY_AT_SNAPSHOT)) )
                print(f'account({accountAddress}):     ', lpFTokenBalance)
                usdcLpTotal += lpFTokenBalance
                lpFTokenBalances[tokenSymbol][accountAddress] = int(lpFTokenBalance)
            elif tokenSymbol == 'fUSDT':
                lpFTokenBalance = math.floor(float(Fraction(balance * fUsdtLpBalance, FUSDT_LP_TOTAL_SUPPLY_AT_SNAPSHOT)))
                print(f'account({accountAddress}):     ', lpFTokenBalance)
                usdtLpTotal += lpFTokenBalance
                lpFTokenBalances[tokenSymbol][accountAddress] = int(lpFTokenBalance)
    
    fUSDCTotal = float(Fraction(usdcTotalBalance * fUsdcLpBalance, FUSDC_LP_TOTAL_SUPPLY_AT_SNAPSHOT))

    fUsdcLpFTokenTotal = round(usdcLpTotal)
    fUsdtLpFTokenTotal = round(usdtLpTotal)
    print(f'usdcTotalBalance: ',usdcTotalBalance)
    print(f'fUsdcLpBalance: ',fUsdcLpBalance)
    print(f'FUSDC_LP_TOTAL_SUPPLY_AT_SNAPSHOT: ', FUSDC_LP_TOTAL_SUPPLY_AT_SNAPSHOT)
    print(f'fUSDCTotal: ', fUSDCTotal)
    print(f'usdcFractionSum:                ', usdcFractionSum)
    print(f'fUsdcLpAdjustment:              ', fUsdcLpAdjustment)
    print(f'fUsdcLpAdjustment fraction:     ', float(Fraction(fUsdcLpAdjustment, FUSDC_LP_TOTAL_SUPPLY_AT_SNAPSHOT)))
    
    print(f'Testing fUSDC LP balances. Calculated {(fUsdcLpFTokenTotal)}, Expected: {(fUsdcLpBalance - float(Fraction(fUsdcLpAdjustment * fUsdcLpBalance, FUSDC_LP_TOTAL_SUPPLY_AT_SNAPSHOT)) )}')
    print(f'Testing fUSDT LP balances. Calculated {fUsdtLpFTokenTotal}, Expected: {fUsdtLpBalance}')
    # assert fUsdcLpBalance == (fUsdcLpFTokenTotal + fUsdcLpAdjustment)
    # assert fUsdtLpBalance == fUsdtLpFTokenTotal
    del lpFTokenBalances['fUSDC'][ZERO_ADDRESS]
    del lpFTokenBalances['fUSDT'][ZERO_ADDRESS]
    return lpFTokenBalances

@cached('snapshot/11-aggregated-f-token-holders.toml')
def step_11(lpBalancesFTokenEquivalent, aggregatedBalancesAndStakers):
    print('\r\nStep 11. Aggregate LP holders, balances and stakers')
    allAggregatedBalances = aggregateData(lpBalancesFTokenEquivalent, aggregatedBalancesAndStakers)
    return allAggregatedBalances

@cached('snapshot/12-aggregated-balances-old-normalized.toml')
def step_12(balanceMap,):
    print(f'\r\nStep 12. Convert migrated shares using conversionRate for each vault')
    for tokenSymbol, balances in balanceMap.items():
        remainingLegacyShares = None
        if tokenSymbol == 'fUSDC':
            oldVaultBalanceOfNewPool = FUSDC_OLD_MIGRATED #FUSDC_OLD_VAULT_CONTRACT.functions.balanceOf(FUSDC_REWARD_POOL_ADDRESS).call({}, SNAPSHOT_BLOCK)
            newVaultBalanceOfNewPool = FUSDC_VAULT_CONTRACT.functions.balanceOf(FUSDC_REWARD_POOL_ADDRESS).call({}, SNAPSHOT_BLOCK)
            remainingLegacyShares = FUSDC_OLD_VAULT_TOTAL_SUPPLY_AT_SNAPSHOT - oldVaultBalanceOfNewPool
            unmigratedNewShares = newVaultBalanceOfNewPool - FUSDC_REWARD_POOL_TOTAL_SUPPLY_AT_SNAPSHOT
            conversionRate = unmigratedNewShares / remainingLegacyShares
            print(f'fUSDC conversion rate: {conversionRate}')
            for accountAddress, balance in balances.items():
                userBalance = balanceMap[tokenSymbol][accountAddress]
                newUserBalance = int(userBalance * conversionRate)
                assert newUserBalance >= userBalance 
                balanceMap[tokenSymbol][accountAddress] = newUserBalance
        elif tokenSymbol == 'fUSDT':
            oldVaultBalanceOfNewPool = FUSDT_OLD_MIGRATED #FUSDT_OLD_VAULT_CONTRACT.functions.balanceOf(FUSDT_REWARD_POOL_ADDRESS).call({}, SNAPSHOT_BLOCK)
            newVaultBalanceOfNewPool = FUSDT_VAULT_CONTRACT.functions.balanceOf(FUSDT_REWARD_POOL_ADDRESS).call({}, SNAPSHOT_BLOCK)
            remainingLegacyShares = FUSDT_OLD_VAULT_TOTAL_SUPPLY_AT_SNAPSHOT - oldVaultBalanceOfNewPool
            unmigratedNewShares = newVaultBalanceOfNewPool - FUSDT_REWARD_POOL_TOTAL_SUPPLY_AT_SNAPSHOT
            conversionRate = unmigratedNewShares / remainingLegacyShares
            print(f'fUSDT conversion rate: {conversionRate}')
            for accountAddress, balance in balances.items():
                userBalance = balanceMap[tokenSymbol][accountAddress]
                newUserBalance = int(userBalance * conversionRate)
                assert newUserBalance >= userBalance 
                balanceMap[tokenSymbol][accountAddress] = newUserBalance
    return balanceMap

@cached('snapshot/13-aggregated-balances-all.toml')
def step_13(aggregatedBalances, normalizedAggregatedBalancesOld):
    print('\r\nStep 13. Aggregate converted old vault/pool balances with new vault/pool balances')
    allAggregatedBalances = aggregateData(aggregatedBalances, normalizedAggregatedBalancesOld)
    fUsdcSum = sum(allAggregatedBalances['fUSDC'].values())
    fUsdtSum = sum(allAggregatedBalances['fUSDT'].values())
    totalSum = fUsdcSum + fUsdtSum
    print(f'fUSDC sum: {fUsdcSum}')
    print(f'fUSDT sum: {fUsdtSum}')
    print(f'Total sum: {totalSum}')
    return allAggregatedBalances

def summary_debug(description, aggregatedBalanceMap):
    print(f'\r\nSUMMARY {description}')
    totalFUSDT = 0
    totalFUSDC = 0

    recorded = {}

    for tokenSymbol, balances in aggregatedBalanceMap.items():
        for account, balance in balances.items():
            if account in recorded:
              continue
            else:
              recorded[account] = True
            
            userHoldingsInfUSDC = aggregatedBalanceMap['fUSDC'].get(account) or 0
            userHoldingsInfUSDT = aggregatedBalanceMap['fUSDT'].get(account) or 0

            totalFUSDT += userHoldingsInfUSDC
            totalFUSDC += userHoldingsInfUSDT

    print(f'Total USDC {description}: {totalFUSDT}')
    print(f'Total USDT {description}: {totalFUSDC}')
    print('')

@cached('snapshot/14-amounts-lost-usdc-usdt.toml')
def step_14(aggregatedBalanceMap):
    print('\r\nStep 14. Find USDC and USDT lost for each user')
    totalLost = 0
    totalUsdtLost = 0
    totalUsdcLost = 0
    snapshotBlockUsdcBalance = FUSDC_VAULT_CONTRACT.functions.underlyingBalanceWithInvestment().call({}, SNAPSHOT_BLOCK)
    snapshotBlockUsdtBalance = FUSDT_VAULT_CONTRACT.functions.underlyingBalanceWithInvestment().call({}, SNAPSHOT_BLOCK)
    
    Fraction(snapshotBlockUsdcBalance, FUSDC_TOTAL_SUPPLY_AT_SNAPSHOT)

    totalFUSDT = 0
    totalFUSDC = 0

    recorded = {}

    for tokenSymbol, balances in aggregatedBalanceMap.items():
        for account, balance in balances.items():

            userHoldingsInfUSDC = aggregatedBalanceMap['fUSDC'].get(account) or 0
            userHoldingsInfUSDT = aggregatedBalanceMap['fUSDT'].get(account) or 0
  
            # The user's balance = Total underlying balance in the vault * the ratio of this user's holding
            userHoldingsInUSDC = snapshotBlockUsdcBalance / FUSDC_TOTAL_SUPPLY_AT_SNAPSHOT * userHoldingsInfUSDC
            userHoldingsInUSDT = snapshotBlockUsdtBalance / FUSDT_TOTAL_SUPPLY_AT_SNAPSHOT * userHoldingsInfUSDT 
            
            userLostAmountInUSDC = int(userHoldingsInUSDC * FUSDC_LOST_RATIO) or 0
            userLostAmountInUSDT = int(userHoldingsInUSDT * FUSDT_LOST_RATIO) or 0
            # userLostAmount = userLostAmountInUSDC + userLostAmountInUSDT
            # userRatio = Fraction(userLostAmount, TOTAL_LOST_AMOUNT)

            if tokenSymbol == 'fUSDC':
              totalFUSDC += userHoldingsInfUSDC
              totalLost += userLostAmountInUSDC
              totalUsdcLost += userLostAmountInUSDC
              aggregatedBalanceMap['fUSDC'][account] = userLostAmountInUSDC
              print(f'Account {account} lost {userLostAmountInUSDC} USDC')
            elif tokenSymbol == 'fUSDT':
              totalFUSDT += userHoldingsInfUSDT
              totalLost += userLostAmountInUSDT
              totalUsdtLost += userLostAmountInUSDT
              aggregatedBalanceMap['fUSDT'][account] = userLostAmountInUSDT
              print(f'Account {account} lost {userLostAmountInUSDT} USDT')

    print(f'Total fUSDC:      Expected less than {FUSDC_TOTAL_SUPPLY_AT_SNAPSHOT}, Actual: {totalFUSDC}')
    print(f'Total fUSDT:      Expected less than {FUSDT_TOTAL_SUPPLY_AT_SNAPSHOT}, Actual: {totalFUSDT}')
    print(f'fUSDC lost ratio: {FUSDC_LOST_RATIO}')
    print(f'fUSDT lost ratio: {FUSDT_LOST_RATIO}')
    print(f'Total USDC lost:  Expected {FUSDC_LOST}, Actual: {totalUsdcLost}')
    print(f'Total USDT lost:  Expected {FUSDT_LOST}, Actual: {totalUsdtLost}')
    print(f'Testing total lost amounts: Expected {TOTAL_LOST_AMOUNT}, Actual: {totalLost}')
   
    return aggregatedBalanceMap

@cached('snapshot/15-iou-amounts.toml')
def step_15(amountsLostMap):
    iouAmounts = defaultdict(Counter)
    print('\r\nStep 15. Find IOU amounts for each user')

    totalIou = IOU_AMOUNT
    for tokenSymbol, balances in amountsLostMap.items():
        for account, balance in balances.items():
            userLostAmountInUSDC = amountsLostMap['fUSDC'].get(account) or 0
            userLostAmountInUSDT = amountsLostMap['fUSDT'].get(account) or 0
            userLostAmount = userLostAmountInUSDC + userLostAmountInUSDT
            userRatio = Fraction(userLostAmount, TOTAL_LOST_AMOUNT)
            iouAsFraction = (totalIou) * userRatio * pow(10, 12)
            iouAmount = int(iouAsFraction)
            iouAmounts['IOU'][account] = iouAmount
            iouAmounts['fUSDT'][account] = int(FUSDT_TOTAL_DISTRIBUTION * userRatio)
            iouAmounts['fUSDC'][account] = int(FUSDC_TOTAL_DISTRIBUTION * userRatio)
    iouSum = int(sum(iouAmounts['IOU'].values()) / pow(10, 12))
    print(f'Testing total IOU amounts: Expected {totalIou}, Actual: {iouSum}')
    return iouAmounts

@cached('snapshot/16-usdc-merkle-distribution.json')
def step_16(aggregatedBalanceMap):
    print('\r\nStep 16. Generate merkle distribution for normalized aggregated USDC balances')
    return generateMerkleDistribution(aggregatedBalanceMap['fUSDC'])

@cached('snapshot/17-usdt-merkle-distribution.json')
def step_17(aggregatedBalanceMap):
    print('\r\nStep 17. Generate merkle distribution for normalized aggregated USDT balances')
    return generateMerkleDistribution(aggregatedBalanceMap['fUSDT'])

@cached('snapshot/18-iou-distribution.json')
def step_18(aggregatedBalanceMap):
    print('\r\nStep 18. Generate merkle distribution for normalized aggregated USDT balances')
    return generateMerkleDistribution(aggregatedBalanceMap['IOU'])

def deployUsdcMerkleContract():
    deployer = accounts.at(DEPLOYER_ADDRESS)
    tree = json.load(open('snapshot/06-usdc- merkle-distribution.json'))
    root = tree['merkleRoot']
    token = str(USDC)
    MerkleDistributor.deploy(token, root, {'from': deployer})

def main():
  # snapshotExpectations = step_00()                                                                    # 0. Print and test snapshot expectations (snapshot block, returned values, etc)
  tokenBalanceMap = step_01()                                                                         # 1. Calculate vault balance of every user at snapshot
  stakerBalanceMap = step_02()                                                                        # 2. Calculate total amount staked per user at snapshot
  aggregatedBalances = step_03(tokenBalanceMap, stakerBalanceMap)                                     # 3. Aggregate balances from step 2 and 3
  summary_debug("new vault share (holders and stakers)", aggregatedBalances)
  print(f'USDC new vault total supply: {FUSDC_TOTAL_SUPPLY_AT_SNAPSHOT}')
  print(f'USDT new vault total supply: {FUSDT_TOTAL_SUPPLY_AT_SNAPSHOT}')
  

  tokenBalanceOldMap = step_04()                                                                      # 4. Calculate old vault balance of every user at snapshot
  stakerBalanceOldMap = step_05()                                                                     # 5. Calculate old total amount staked per user at snapshot
  aggregatedBalancesOld = step_06(tokenBalanceOldMap, stakerBalanceOldMap)                            # 6. Aggregate balances from step 4 and 5
  summary_debug("old vault share (excluding LP)", aggregatedBalancesOld)
  print(f'USDC old vault total supply: {FUSDC_OLD_VAULT_TOTAL_SUPPLY_AT_SNAPSHOT}')
  print(f'USDT old vault total supply: {FUSDT_OLD_VAULT_TOTAL_SUPPLY_AT_SNAPSHOT}')

  lpBalances = step_07()                                                                              # 7. Calculate LP balances
  lpPoolBalances = step_08()                                                                          # 8. Calculate LP pool staker balances
  aggregatedLpBalances = step_09(lpBalances, lpPoolBalances)                                          # 9. Aggregate balances from steps 7 and 8  
  lpBalancesFTokenEquivalent = step_10(aggregatedLpBalances)                                          # 10. Find LP holder/staker fToken equivalents
  summary_debug("old vaults share (LP)", lpBalancesFTokenEquivalent)
  fUsdcLpBalance = FUSDC_OLD_VAULT_CONTRACT.functions.balanceOf(FUSDC_LP_ADDRESS).call({}, SNAPSHOT_BLOCK)
  fUsdtLpBalance = FUSDT_OLD_VAULT_CONTRACT.functions.balanceOf(FUSDT_LP_ADDRESS).call({}, SNAPSHOT_BLOCK)
  print(f'Pair holds USDC old vault shares: {fUsdcLpBalance}')
  print(f'Pair holds USDT old vault shares: {fUsdtLpBalance}')


  aggregatedBalancesOldWithLp = step_11(lpBalancesFTokenEquivalent, aggregatedBalancesOld)            # 11. Aggregate balances from steps 6 and 10

  summary_debug("old vaults share (ALL)", aggregatedBalancesOldWithLp)
  print(f'USDC old vault total supply: {FUSDC_OLD_VAULT_TOTAL_SUPPLY_AT_SNAPSHOT}')
  print(f'USDT old vault total supply: {FUSDT_OLD_VAULT_TOTAL_SUPPLY_AT_SNAPSHOT}')

  normalizedAggregatedBalancesOld = step_12(aggregatedBalancesOldWithLp)                              # 12. Convert migrated shares using conversionRate for each vault

  summary_debug("old vaults share (in NEW)", normalizedAggregatedBalancesOld)
  print(f'USDC new vault total supply: {FUSDC_TOTAL_SUPPLY_AT_SNAPSHOT}')
  print(f'USDT new vault total supply: {FUSDT_TOTAL_SUPPLY_AT_SNAPSHOT}')

  aggregatedBalancesAndStakers = step_13(aggregatedBalances, normalizedAggregatedBalancesOld)         # 13. Aggregate converted old vault/pool balances with new vault/pool balances (combine result of steps 3 and 7)

  summary_debug("new vault share (ALL)", aggregatedBalancesAndStakers)
  print(f'USDC new vault total supply: {FUSDC_TOTAL_SUPPLY_AT_SNAPSHOT}')
  print(f'USDT new vault total supply: {FUSDT_TOTAL_SUPPLY_AT_SNAPSHOT}')

  print(f'aggregatedBalancesAndStakers[farmer1]: ')

  amountsLost = step_14(aggregatedBalancesAndStakers)                                                 # 14. Step 14. Find USDC and USDT lost for each user
  iouAmounts = step_15(amountsLost)                                                                   # 15. Find IOU amounts for each user
  merkleDistributionUsdc = step_16(iouAmounts)                                      # 16. Generate merkle distribution for normalized aggregated USDC balances
  merkleDistributionUsdt = step_17(iouAmounts)                                      # 17. Generate merkle distribution for normalized aggregated USDT balances
  merkleDistributionIou = step_18(iouAmounts)                                                         # 18. Generate merkle distribution for IOU

