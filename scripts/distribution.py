import json
from brownie import MerkleDistributor, accounts, interface

USDC_ADDRESS = '0x2d69ad895797c880abce92437788047ba0eb7ff6'
# USDT_ADDRESS = '0xdac17f958d2ee523a2206206994597c13d831ec7'
DEPLOYER_ADDRESS = '0x61C59b3c032B9c1b17B830694C52E84f9c47e23D'

def main():
    with open('snapshot/10-usdc-merkle-distribution.json') as fp:
        tree = json.load(fp)
    deployer = accounts.at(DEPLOYER_ADDRESS)
    usdc = interface.ERC20(USDC_ADDRESS)
    print(f'Deployer address {DEPLOYER_ADDRESS}')
    print(f'Deployer USDC balance: {usdc.balanceOf(deployer)}')
    print(f'Deployer eth balance: {deployer.balance()}')
    distributor = MerkleDistributor.deploy(usdc, tree['merkleRoot'], {'from': deployer})

    usdc.transfer(distributor, tree['tokenTotal'], {'from': deployer})
    for i, (address, claim) in enumerate(tree['claims'].items()):
        if not i % 50:
            print(f"Distribution in progress, {i} / {len(tree['claims'])}...")
        balance = usdc.balanceOf(address)
        distributor.claim(
            claim['index'], address, claim['amount'], claim['proof'], 0, {'from': deployer}
        )
        assert usdc.balanceOf(address) == balance + claim['amount']
    assert usdc.balanceOf(distributor) == 0
    print("Distribution was successful!")
