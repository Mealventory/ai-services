from services.expiry_service import predict_expiry, get_expiry_status
from services.recommendation_service import recommend_recipes
from datetime import datetime

#Test expiry
purchase_date = datetime(2026, 3, 20)
expiry = predict_expiry("Milk", purchase_date)
status = get_expiry_status(expiry)

print("Expiry Date:", expiry)
print("Status:", status)


#Test recipe recommendation
user_inventory = ["Milk", "Eggs", "Chicken Breast", "Rice"]
expiring_items = ["Milk", "Chicken Breast"]

recipes = [
    {"name": "Omelette", "ingredients": ["Eggs", "Milk", "Cheese"]},
    {"name": "Chicken Rice", "ingredients": ["Chicken Breast", "Rice"]},
    {"name": "Salad", "ingredients": ["Spinach", "Tomato"]}
]

recommended = recommend_recipes(user_inventory, recipes, expiring_items)

print("Recommended Recipes:", recommended)