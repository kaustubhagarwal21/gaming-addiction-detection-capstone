import pandas as pd
import re
import nltk

from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer

# Load dataset
data = pd.read_csv("chat_dataset.csv")

# Keep only required columns
data = data[["text", "toxicity_score"]]

# Rename columns
data = data.rename(columns={
    "text": "chat",
    "toxicity_score": "score"
})

# 🔴 DROP NULL VALUES HERE (VERY IMPORTANT)
data = data.dropna(subset=["chat", "score"])

# Initialize tools
stop_words = set(stopwords.words("english"))
lemmatizer = WordNetLemmatizer()

def clean_text(text):

    # Convert to lowercase
    text = str(text).lower()

    # Remove URLs
    text = re.sub(r"http\S+", "", text)

    # Remove emojis / punctuation
    text = re.sub(r"[^\w\s]", "", text)

    # Remove numbers
    text = re.sub(r"\d+", "", text)

    # Tokenize
    words = text.split()

    # Remove stopwords
    words = [word for word in words if word not in stop_words]

    # Lemmatization
    words = [lemmatizer.lemmatize(word) for word in words]

    return " ".join(words)

# Apply cleaning
data["chat"] = data["chat"].apply(clean_text)

# 🔴 REMOVE EMPTY STRINGS AFTER CLEANING
data = data[data["chat"].str.strip() != ""]

# Save cleaned dataset
data.to_csv("data/chat/chat_cleaned.csv", index=False)

print("Chat cleaning complete.")