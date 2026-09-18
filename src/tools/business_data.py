def get_sales_performance(period: str) -> dict:
    """
    Temporary stand-in for the future Fabric Data Agent.

    Returns controlled business data for testing agent grounding.
    """

    return {
        "period": period,
        "currency": "INR million",
        "regions": [
            {
                "region": "West",
                "current_sales": 11.8,
                "next_month_target": 14.0,
                "next_month_ml_forecast": 12.4,
            },
            {
                "region": "South",
                "current_sales": 9.7,
                "next_month_target": 10.0,
                "next_month_ml_forecast": 10.3,
            },
            {
                "region": "North",
                "current_sales": 10.4,
                "next_month_target": 11.0,
                "next_month_ml_forecast": 11.7,
            },
        ],
    }