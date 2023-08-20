flashloan_fee_rate = 0.0009

# Define risk parameters
RISK_PARAMETERS = {
    "ETH": {
        "LTV": 0.75, 
        "Liquidation_Threshold": 0.80, 
        "Liquidation_Bonus": 0.05 
    },
    "USDC": {
        "LTV": 0.75,
        "Liquidation_Threshold": 0.80,
        "Liquidation_Bonus": 0.05
    },
}