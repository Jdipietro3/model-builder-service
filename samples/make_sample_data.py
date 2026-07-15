"""Generate synthetic demo datasets: churn.csv (binary classification) and
house_prices.csv (regression). Run: python samples/make_sample_data.py"""

from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).resolve().parent
rng = np.random.default_rng(42)


def make_churn(n: int = 5000) -> pd.DataFrame:
    tenure = rng.integers(1, 72, n)
    monthly = np.round(rng.uniform(20, 120, n), 2)
    contract = rng.choice(["month-to-month", "one-year", "two-year"], n, p=[0.55, 0.25, 0.2])
    support_calls = rng.poisson(1.5, n)
    payment = rng.choice(["credit_card", "bank_transfer", "electronic_check"], n)
    intl_plan = rng.choice(["yes", "no"], n, p=[0.15, 0.85])

    logit = (
        -1.2
        - 0.04 * tenure
        + 0.015 * monthly
        + 0.45 * support_calls
        + np.where(contract == "month-to-month", 1.1, np.where(contract == "one-year", 0.2, -0.6))
        + np.where(payment == "electronic_check", 0.5, 0.0)
        + np.where(intl_plan == "yes", 0.4, 0.0)
        + rng.normal(0, 0.8, n)
    )
    churned = (1 / (1 + np.exp(-logit)) > 0.5).astype(int)

    df = pd.DataFrame(
        {
            "customer_id": [f"C{100000 + i}" for i in range(n)],
            "tenure_months": tenure,
            "monthly_charges": monthly,
            "contract_type": contract,
            "support_calls": support_calls,
            "payment_method": payment,
            "international_plan": intl_plan,
            "churned": churned,
        }
    )
    # Realistic imperfection: some missing values
    df.loc[rng.choice(n, size=n // 50, replace=False), "monthly_charges"] = np.nan
    return df


def make_house_prices(n: int = 3000) -> pd.DataFrame:
    sqft = rng.integers(600, 4500, n)
    beds = np.clip((sqft / 900 + rng.normal(0, 0.7, n)).round().astype(int), 1, 6)
    baths = np.clip((beds - rng.integers(0, 2, n)), 1, 4)
    age = rng.integers(0, 80, n)
    neighborhood = rng.choice(["downtown", "suburbs", "rural", "waterfront"], n, p=[0.3, 0.45, 0.15, 0.1])
    garage = rng.choice(["yes", "no"], n, p=[0.7, 0.3])

    price = (
        50_000
        + 140 * sqft
        + 12_000 * beds
        + 9_000 * baths
        - 800 * age
        + np.select(
            [neighborhood == "waterfront", neighborhood == "downtown", neighborhood == "rural"],
            [120_000, 60_000, -30_000],
            default=0,
        )
        + np.where(garage == "yes", 15_000, 0)
        + rng.normal(0, 25_000, n)
    ).round(-2)

    return pd.DataFrame(
        {
            "listing_id": [f"L{200000 + i}" for i in range(n)],
            "sqft": sqft,
            "bedrooms": beds,
            "bathrooms": baths,
            "age_years": age,
            "neighborhood": neighborhood,
            "has_garage": garage,
            "price": price,
        }
    )


if __name__ == "__main__":
    churn = make_churn()
    churn.to_csv(OUT_DIR / "churn.csv", index=False)
    print(f"churn.csv: {len(churn)} rows, churn rate {churn['churned'].mean():.1%}")

    prices = make_house_prices()
    prices.to_csv(OUT_DIR / "house_prices.csv", index=False)
    print(f"house_prices.csv: {len(prices)} rows, mean price ${prices['price'].mean():,.0f}")
