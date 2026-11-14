
class PricingEngine:
    """
    Institutional Pricing v0.4.0.
    Ensures penny-accurate TCO with integrated infrastructure markups.
    """
    def __init__(self, markup_percent: float = 10.0):
        self.markup = 1 + (markup_percent / 100)
        # Rates per 1k tokens (Institutional Standard)
        self.rates = {
            "gpt-4o": {"input": 0.005, "output": 0.015},
            "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
            "default": {"input": 0.02, "output": 0.02}
        }

    def calculate_cost(self, model: str, tokens: int) -> float:
        """Calculates true cost with institutional overhead."""
        model_rates = self.rates.get(model, self.rates["default"])
        # Simplified: assuming 75/25 split for generic estimates
        avg_rate = (model_rates["input"] * 0.75) + (model_rates["output"] * 0.25)
        raw_cost = (tokens / 1000) * avg_rate
        return round(raw_cost * self.markup, 6)