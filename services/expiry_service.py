from datetime import datetime, timedelta

#Default shelf life if not found in database
DEFAULT_SHELF_LIFE = {
    "Milk": 7,
    "Eggs": 21,
    "Chicken Breast": 3,
    "Rice": 365,
    "Spinach": 5,
    "Bread": 5,
    "Cheese": 14,
    "Yogurt": 10,
    "Apples": 30
}

def predict_expiry(item_name: str, purchase_date: datetime):
    shelf_life_days = DEFAULT_SHELF_LIFE.get(item_name, 7)
    expiry_date = purchase_date + timedelta(days=shelf_life_days)
    return expiry_date


def get_expiry_status(expiry_date: datetime):
    today = datetime.now()
    days_left = (expiry_date - today).days

    if days_left < 0:
        return "Expired"
    elif days_left <= 2:
        return "Expiring Soon"
    else:
        return "Fresh"

def days_until_expiry(expiry_date: datetime):
    today = datetime.now()
    return (expiry_date - today).days