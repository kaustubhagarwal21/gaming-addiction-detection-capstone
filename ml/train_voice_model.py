import os
import joblib
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, ConfusionMatrixDisplay

DATA_FILE = "voice_module/voice_features.csv"
RESULT_DIR = "voice_module/results"
MODEL_PATH = "voice_module/voice_model.pkl"

os.makedirs(RESULT_DIR, exist_ok=True)

# load dataset
df = pd.read_csv(DATA_FILE)

# split features and labels
X = df.drop(columns=["emotion_label", "filename"])
y = df["emotion_label"]

# train/test split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# train model
model = RandomForestClassifier(n_estimators=200, random_state=42)
model.fit(X_train, y_train)

# predictions
y_pred = model.predict(X_test)

# accuracy
accuracy = accuracy_score(y_test, y_pred)
print("Accuracy:", accuracy)

# classification report
report = classification_report(y_test, y_pred)
print(report)

with open(os.path.join(RESULT_DIR, "classification_report.txt"), "w") as f:
    f.write("Accuracy: " + str(accuracy) + "\n\n")
    f.write(report)

# confusion matrix
cm = confusion_matrix(y_test, y_pred)
disp = ConfusionMatrixDisplay(cm, display_labels=model.classes_)
disp.plot()

plt.savefig(os.path.join(RESULT_DIR, "confusion_matrix.png"))
plt.close()

# save model
joblib.dump(model, MODEL_PATH)

print("Model saved:", MODEL_PATH)