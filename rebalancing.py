import time
import json
import requests
from web3 import Web3
import os
from dotenv import load_dotenv
import logging
import pdb

# Load environment variables
load_dotenv()
RPC_URL = os.getenv("RPC_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS")
ROUTER_ADDRESS = os.getenv("ROUTER_ADDRESS")
POOL_ADDRESS = os.getenv("POOL_ADDRESS")

# Set up logging351351
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(message)s')
logging.info('Bot started.')

# Connect to Base Mainnet
web3 = Web3(Web3.HTTPProvider(RPC_URL))
if not web3.is_connected():
    logging.error("Failed to connect to Base Mainnet")
    raise Exception("Failed to connect to Base Mainnet")
else:
    logging.info("Connected to Base Mainnet")

# Load contract ABIs
try:
    with open("router_abi.json", "r") as abi_file:
        ROUTER_ABI = json.load(abi_file)
    with open("pool_abi.json", "r") as abi_file:
        POOL_ABI = json.load(abi_file)
except FileNotFoundError as e:
    logging.error(f"ABI file not found: {e}")
    raise

# Initialize contracts
router_contract = web3.eth.contract(address=ROUTER_ADDRESS, abi=ROUTER_ABI)
pool_contract = web3.eth.contract(address=POOL_ADDRESS, abi=POOL_ABI)

# Fetch real-time price from Dexscreener API
def get_token_price(pool_address):
    """Fetch token price from Dexscreener API."""
    try:
        url = f"https://api.dexscreener.io/latest/dex/pairs/base/{pool_address}"
        response = requests.get(url)
        data = response.json()
        price = float(data['pair']['priceUsd'])
        logging.info(f"Fetched token price: ${price}")
        return price
    except Exception as e:
        logging.error(f"Error fetching token price: {e}")
        return None

# Fetch reserves from the pool contract
def get_pool_data():
    """Fetch reserves and timestamp from the pool contract."""
    try:
        reserves = pool_contract.functions.getReserves().call()
        reserve0 = reserves[0]
        reserve1 = reserves[1]
        block_timestamp_last = reserves[2]
        logging.info(f"Reserves - Token0: {reserve0}, Token1: {reserve1}, Timestamp: {block_timestamp_last}")
        return reserve0, reserve1
    except Exception as e:
        logging.error(f"Error fetching pool reserves: {e}")
        return None, None

# Fetch token addresses from the pool
def get_token_addresses():
    """Fetch token addresses from the pool contract."""
    try:
        token0 = pool_contract.functions.token0().call()
        token1 = pool_contract.functions.token1().call()
        logging.info(f"Token0: {token0}, Token1: {token1}")
        return token0, token1
    except Exception as e:
        logging.error(f"Error fetching token addresses: {e}")
        return None, None

# Calculate price using reserves
def calculate_price(reserve0, reserve1):
    """Calculate the price of token0 in terms of token1."""
    if reserve1 == 0:
        logging.error("Reserve1 is zero, cannot calculate price")
        return None
    return reserve0 / reserve1

# Check if the current price is out of range
def is_out_of_range(price, lower_tick, upper_tick):
    return price < lower_tick or price > upper_tick

# Calculate a new tick range dynamically
def calculate_tick_range(price, volatility):
    """
    Calculate the tick range based on the current price and volatility percentage.
    Args:
        price: Current price of the token.
        volatility: Volatility percentage (e.g., 0.01 for 0.01%).
    Returns:
        lower_tick: Lower bound of the price range.
        upper_tick: Upper bound of the price range.
    """
    lower_tick = price * (1 - volatility / 100)
    upper_tick = price * (1 + volatility / 100)
    logging.info(f"Tick range calculated with volatility {volatility}%: {lower_tick:.6f} - {upper_tick:.6f}")
    return lower_tick, upper_tick

# Fetch LP token balance
def get_lp_balance():
    """Fetch the LP token balance for the wallet."""
    try:
        balance = pool_contract.functions.balanceOf(WALLET_ADDRESS).call()
        logging.info(f"LP Token Balance: {balance}")
        print(f"LP Token Balance: {balance}")
        return balance
    except Exception as e:
        logging.error(f"Error fetching LP token balance: {e}")
        return None

# Add liquidity (old method, not currently used)
def add_liquidity(tokenA, tokenB, amountADesired, amountBDesired, amountAMin, amountBMin, deadline):
    """Add liquidity to the pool."""
    try:
        gas_price = web3.eth.gas_price
        tx_add = router_contract.functions.addLiquidity(
            tokenA,
            tokenB,
            amountADesired,
            amountBDesired,
            amountAMin,
            amountBMin,
            WALLET_ADDRESS,
            deadline
        ).buildTransaction({
            "from": WALLET_ADDRESS,
            "gas": 300000,
            "gasPrice": gas_price,
            "nonce": web3.eth.getTransactionCount(WALLET_ADDRESS)
        })

        signed_tx_add = web3.eth.account.signTransaction(tx_add, private_key=PRIVATE_KEY)
        tx_add_hash = web3.eth.sendRawTransaction(signed_tx_add.rawTransaction)
        logging.info(f"Liquidity added: {tx_add_hash.hex()}")
    except Exception as e:
        logging.error(f"Error in adding liquidity: {e}")

# Remove liquidity (old method, not currently used)
def remove_liquidity(tokenA, tokenB, liquidity, amountAMin, amountBMin, deadline):
    """Remove liquidity from the pool."""
    try:
        gas_price = web3.eth.gas_price
        tx_remove = router_contract.functions.removeLiquidity(
            tokenA,
            tokenB,
            liquidity,
            amountAMin,
            amountBMin,
            WALLET_ADDRESS,
            deadline
        ).buildTransaction({
            "from": WALLET_ADDRESS,
            "gas": 300000,
            "gasPrice": gas_price,
            "nonce": web3.eth.getTransactionCount(WALLET_ADDRESS)
        })

        signed_tx_remove = web3.eth.account.signTransaction(tx_remove, private_key=PRIVATE_KEY)
        tx_remove_hash = web3.eth.sendRawTransaction(signed_tx_remove.rawTransaction)
        logging.info(f"Liquidity removed: {tx_remove_hash.hex()}")
    except Exception as e:
        logging.error(f"Error in removing liquidity: {e}")

# Monitoring and rebalancing loop
def monitor_and_rebalance():
    """Fetch pool data and determine if rebalancing is needed."""
    try:
        # Fetch LP token balance
        get_lp_balance()

        # Fetch token price from Dexscreener
        price = get_token_price(POOL_ADDRESS)
        if price is None:
            return
        logging.info(f"Fetched token price: {price}")

        # Fetch reserves from the pool
        reserve0, reserve1 = get_pool_data()
        if reserve0 is None or reserve1 is None:
            return

        # Calculate on-chain price
        on_chain_price = calculate_price(reserve0, reserve1)
        if on_chain_price is None:
            logging.warning("Unable to calculate on-chain price")
            return
        logging.info(f"On-chain price: {on_chain_price}")

        # Compare and adjust liquidity if needed
        lower_tick, upper_tick = calculate_tick_range(price, volatility=0.01)
        if is_out_of_range(on_chain_price, lower_tick, upper_tick):
            logging.info("Price is out of range. Rebalancing...")
        else:
            logging.info("Price is within range. No action needed.")
    except Exception as e:
        logging.error(f"Error during monitoring: {e}")

# Main loop
if __name__ == "__main__":
    while True:
        monitor_and_rebalance()
        time.sleep(60)  # Check every minute


