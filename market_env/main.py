from __future__ import annotations
import random
import numpy as np
from constants import flashloan_fee_rate, RISK_PARAMETERS

# Aave interest rate model
class AaveRateModel:
    def __init__(self, base_rate, optimal_utilization, slope1, slope2):
        self.base_rate = base_rate
        self.optimal_utilization = optimal_utilization
        self.slope1 = slope1
        self.slope2 = slope2

    def get_rate(self, utilization_rate):
        if utilization_rate <= self.optimal_utilization:
            return self.base_rate + (utilization_rate / self.optimal_utilization) * self.slope1
        else:
            excess_utilization = utilization_rate - self.optimal_utilization
            return self.base_rate + self.slope1 + (excess_utilization / (1 - self.optimal_utilization)) * self.slope2
        
    @staticmethod
    def get_utilization_rate():
        # A placeholder value
        return 0.5

class Trader:
    def __init__(self, collateral: float, leverage: float, expiry_length: int, 
                 simulated_usdc_reserves: list = None, simulated_eth_reserves: list = None):
        
        self.collateral = collateral
        self.leverage = leverage
        self.expiry_length = expiry_length  # Unit in days
        
        # trader's own wallet after deposit margin, this wallet pay transaction fee
        self.balance = {'USDC': 10000 - collateral, 'ETH': 0.005}
        # trader's funds on Contango  
        self.funds_available = {'USDC': collateral, 'ETH': 0.0}  
        self.simulated_usdc_reserves = simulated_usdc_reserves or []
        self.simulated_eth_reserves = simulated_eth_reserves or []
        self.current_reserve_idx = 0
    
    def simulate_reserves(self, steps: int):
        usdc_reserves = [100000]  # Assumed starting reserve for USDC
        eth_reserves = [100]  # Assumed tarting reserve for ETH

        for _ in range(steps - 1):
            usdc_reserves.append(usdc_reserves[-1] + random.randint(-1000, 1000))
            eth_reserves.append(eth_reserves[-1] + random.uniform(-1, 1))

        self.simulated_usdc_reserves = usdc_reserves
        self.simulated_eth_reserves = eth_reserves
    
    def gas_fee(self):
        self.gas_price = random.uniform(20, 100) * 1e-9  # random gas price between 20 Gwei and 100 Gwei
        gas_used = random.randint(21000, 200000)  # random gas used
        fee = self.gas_price * gas_used
        self.balance['ETH'] -= fee  # Deducting the gas fee from ETH balance
        return fee
    
    def execute_long(self):
        self.flashloan_from_aave()
        eth_received_adjusted, spot_price = self.swap_eth()
        self.lend_eth_on_aave()
        self.borrow_from_aave(spot_price, eth_received_adjusted)
        self.repay_flashloan()
        
    def flashloan_from_aave(self):
        borrow_amount = self.collateral * (self.leverage - 1)
        self.funds_available["USDC"] += borrow_amount
        self.gas_fee()

    def swap_eth(self):
        
        usdc_reserve = self.simulated_usdc_reserves[self.current_reserve_idx]
        eth_reserve = self.simulated_eth_reserves[self.current_reserve_idx]
        
        spot_price = usdc_reserve / eth_reserve
        usdc_to_swap = self.funds_available['USDC']
        k = eth_reserve * usdc_reserve
        new_usdc_reserve = usdc_reserve + usdc_to_swap
        new_eth_reserve = k / new_usdc_reserve
        
        eth_received = eth_reserve - new_eth_reserve
        
        slippage = random.uniform(-0.01, 0.01)
        eth_received_adjusted = eth_received * (1 - slippage)
        
        self.funds_available['USDC'] -= usdc_to_swap
        self.gas_fee()
        self.funds_available['ETH'] += eth_received_adjusted
        
        self.current_reserve_idx += 1  # Move to the next index for the next simulation
        
        return eth_received_adjusted, spot_price

    # Initialize the AaveRateModel for ETH and USDC, https://docs.aave.com/risk/liquidity-risk/borrow-interest-rate
    eth_rate_model = AaveRateModel(base_rate=0, optimal_utilization=0.45, slope1=0.04, slope2=3)
    usdc_rate_model = AaveRateModel(base_rate=0, optimal_utilization=0.8, slope1=0.04, slope2=0.75)

    def lend_eth_on_aave(self):
        eth_lending_rate = self.eth_rate_model.get_rate(AaveRateModel.get_utilization_rate())
        lending_interest = self.funds_available['ETH'] * eth_lending_rate * (self.expiry_length / 365)
        self.gas_fee()
        self.funds_available['ETH'] += lending_interest

    def borrow_from_aave(self, spot_price, eth_received_adjusted):
        usdc_borrowing_rate = self.usdc_rate_model.get_rate(AaveRateModel.get_utilization_rate())
        eth_value_in_usdc = eth_received_adjusted * spot_price
        max_usdc_borrowable = eth_value_in_usdc * RISK_PARAMETERS['ETH']['LTV']
        borrow_interest = max_usdc_borrowable * usdc_borrowing_rate * self.expiry_length / 365
        # Increase the available funds if USDC by the borrowed amount minus interest, prepare to repay flashloan
        self.funds_available['USDC'] += max_usdc_borrowable - borrow_interest 
        self.gas_fee()

    def repay_flashloan(self):
        borrow_amount = self.collateral * (self.leverage - 1)
        flashloan_fee = borrow_amount * flashloan_fee_rate
        flashloan_borrow_interest = borrow_amount * self.usdc_rate_model.get_rate(AaveRateModel.get_utilization_rate())

        total_repayment = borrow_amount + flashloan_fee + flashloan_borrow_interest

        if self.funds_available['USDC'] >= total_repayment:
            # Enough funds to repay
            self.funds_available['USDC'] -= total_repayment
            self.balance['USDC'] -= (flashloan_fee + flashloan_borrow_interest + self.gas_fee()) # Deducting fees from balance
            return f"Repayment successful! Available USDC: {self.funds_available['USDC']}. Balance: {self.balance['USDC']} USDC and {self.balance['ETH']} ETH."
        else:
            # Not enough funds
            original_funds = {
                'USDC': self.funds_available['USDC'] + total_repayment, 
                'ETH': self.funds_available['ETH']
            }
            original_balance = {
                'USDC': self.balance['USDC'] + flashloan_fee + flashloan_borrow_interest, 
                'ETH': self.balance['ETH']
            }
            # Deducting fees from the original balance
            original_balance['USDC'] -= (flashloan_fee + self.gas_fee())

            return f"Flashloan failed, you paid flashloan transaction fee and gas fee. Available funds: {original_funds['USDC']} USDC and {original_funds['ETH']} ETH. Balance: {original_balance['USDC']} USDC and {original_balance['ETH']} ETH."

if __name__ == "__main__":
    # Test 1: Basic test with default parameters
    trader1 = Trader(collateral=1000, leverage=2, expiry_length=30)
    trader1.simulate_reserves(100)
    trader1.execute_long()
    print("Trader 1 Funds:", trader1.funds_available)
    print("Trader 1 Balance:", trader1.balance)

    # Test 2: Test with different leverage
    trader2 = Trader(collateral=1000, leverage=4, expiry_length=30)
    trader2.simulate_reserves(100)
    trader2.execute_long()
    print("\nTrader 2 Funds:", trader2.funds_available)
    print("Trader 2 Balance:", trader2.balance)

