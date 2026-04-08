from models.produce_classifier import ExpiryClassifier

# create an instance of your classifier
classifier = ExpiryClassifier()

# define a sample food item
food_data = {
    "avg_shelf_life_days": 7,   # typical shelf life of the food
    "temperature": 20,          # current storage temp in °C
    "humidity": 50,             # current humidity %
    "purchase_date": "2026-04-07"  # date you bought it
}

# get the predicted expiry date
print(classifier.get_expiry_date(food_data))