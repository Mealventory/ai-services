# models/produce_classifier.py

from keras.applications import MobileNetV2
from keras.applications.mobilenet_v2 import preprocess_input, decode_predictions
import numpy as np

model = MobileNetV2(weights="imagenet")

def classify_image(image_array):
    
    image_array = preprocess_input(image_array)
    preds = model.predict(image_array)
    decoded = decode_predictions(preds, top=3)[0]
    return decoded



import joblib
import pandas as pd
from datetime import datetime

class ExpiryClassifier:
    def __init__(self, model_path=None):
        
        from pathlib import Path
        model_path = model_path or Path(__file__).resolve().parents[1] / "Scripts" / "expiry_predictor.pkl"
        self.model = joblib.load(model_path)

    def predict_days_to_expiry(self, food_data):
        
        features = pd.DataFrame([{
            'avg_shelf_life_days': food_data['avg_shelf_life_days'],
            'temperature': food_data['temperature'],
            'humidity': food_data['humidity']
        }])
        predicted_days = self.model.predict(features)
        return predicted_days[0]

    def get_expiry_date(self, food_data):
        
        days_to_expiry = self.predict_days_to_expiry(food_data)
        purchase_date = food_data['purchase_date']
        if isinstance(purchase_date, str):
            purchase_date = datetime.strptime(purchase_date, "%Y-%m-%d")
        expiry_date = purchase_date + pd.Timedelta(days=days_to_expiry)
        return expiry_date