import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import joblib


data = pd.DataFrame({
    "avg_shelf_life_days": [7, 7, 30, 30, 5, 5, 10, 10],
    "temperature": [4, 25, 4, 25, 4, 25, 4, 25],
    "humidity": [50, 70, 50, 70, 50, 70, 50, 70],
    "days_to_expiry": [7, 3, 30, 20, 5, 2, 10, 6]
})

X = data[["avg_shelf_life_days", "temperature", "humidity"]]
y = data["days_to_expiry"]

model = RandomForestRegressor()
model.fit(X, y)

# Save model
joblib.dump(model, "expiry_predictor.pkl")

print("Model trained and saved!")