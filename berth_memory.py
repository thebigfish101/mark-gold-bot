import json
import os

class BerthMemory:
    def __init__(self):
        self.trades = []

    def add_trade(self, trade):
        self.trades.append({
            "timestamp": str(trade.get("timestamp", "")),
            "entry": trade["entry"],
            "sl": trade["sl"],
            "tp": trade["tp"],
            "direction": trade["direction"],
            "lot": trade["lot"]
        })

    def save(self, filename):
        with open(filename, "w") as f:
            json.dump(self.trades, f, indent=2)

    @classmethod
    def load(cls, filename):
        if os.path.exists(filename):
            with open(filename, "r") as f:
                memory = cls()
                memory.trades = json.load(f)
                return memory
        else:
            return cls()
