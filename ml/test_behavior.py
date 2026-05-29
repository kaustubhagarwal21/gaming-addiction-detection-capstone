import joblib
import pandas as pd

# load model
model = joblib.load("models/behavior_model.pkl")

# sample test input
test_data = pd.DataFrame([[
    6,30,5,60,0.7,7,10,4,10,0.2,0.8,200,0.9,2,0.8,0.2,0.6,0.4,1,0.9
]])

prediction = model.predict(test_data)[0]

label_map = {
    0: "Low Addiction",
    1: "Medium Addiction",
    2: "High Addiction"
}

print("Prediction:", label_map[prediction])