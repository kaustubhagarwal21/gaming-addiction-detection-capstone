import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
import joblib
import numpy as np

# Load cleaned dataset
data = pd.read_csv("data/chat/chat_cleaned.csv")

data["chat"] = data["chat"].astype(str)

texts = data["chat"]

# Create TF-IDF vectorizer
vectorizer = TfidfVectorizer(max_features=500)

# Transform text
X = vectorizer.fit_transform(texts)

# Save vectorizer
joblib.dump(vectorizer, "models/tfidf_vectorizer.pkl")

# Save feature matrix
np.save("data/chat/chat_features.npy", X.toarray())

print("TF-IDF features extracted successfully.")