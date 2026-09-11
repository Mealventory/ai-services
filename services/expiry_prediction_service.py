# services/expiry_prediction_service.py
from models.produce_classifier import ExpiryClassifier
from datetime import datetime

# Load trained classifier once
expiry_classifier = ExpiryClassifier()

def get_expiry_date(food_data):
    """
    Returns the predicted expiry date as a string in YYYY-MM-DD format.
    """
    # Convert purchase_date to datetime if it's a string
    if isinstance(food_data['purchase_date'], str):
        food_data['purchase_date'] = datetime.strptime(food_data['purchase_date'], "%Y-%m-%d")
    
    # Get the predicted expiry date from the classifier
    expiry_date = expiry_classifier.get_expiry_date(food_data)
    
    # Return as string so JSON serialization works
    return expiry_date.strftime("%Y-%m-%d")