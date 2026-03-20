import tensorflow as tf
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input, decode_predictions

model = MobileNetV2(weights="imagenet")

def classify_image(image_array):
    image_array = preprocess_input(image_array)
    preds = model.predict(image_array)
    decoded = decode_predictions(preds, top=3)[0]
    return decoded