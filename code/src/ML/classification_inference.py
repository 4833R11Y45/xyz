import joblib
import re
import os
from nltk.corpus import stopwords
from nltk.stem import PorterStemmer
import pandas as pd
from src.utils import helper

CLASSIFICATION_MODEL = helper.get_path("models", "classifcation_model_6May_2024")
model_path = os.path.join(CLASSIFICATION_MODEL, "classifcation_model_6May_2024", "rf_model.joblib")
vectorizer_path = os.path.join(CLASSIFICATION_MODEL, "classifcation_model_6May_2024", "count_vectorizer.joblib")

# GL Codes Mapping
category_to_gl_mapping = {
    "Conveyance Expense": "510002",
    "Travel": "510004",
    "Hotel": "510003",
    "Electricity": "507001",
    "PTCL": "507005",
    "Gas": "507004",
    "Water": "507003",
    "Director's Utilities": "501006"
}


def preprocess_text(raw_text):
    text = raw_text.lower()
    text = re.sub(r'[^a-zA-Z\s]', '', text)

    stop_words = set(stopwords.words('english'))
    words = text.split()
    words = [word for word in words if word not in stop_words]
    ps = PorterStemmer()
    words = [ps.stem(word) for word in words]

    return ' '.join(words)

def load_dataframe_for_prediction(raw_text):
    data = {'processed_text': [preprocess_text(raw_text)]}
    return pd.DataFrame(data)

def predict_template(raw_text):
    try:
        model = joblib.load(model_path)
        vectorizer = joblib.load(vectorizer_path)
        df_pred = pd.DataFrame({'processed_text': [preprocess_text(raw_text)]})
        text_vectorized = vectorizer.transform(df_pred['processed_text'])
        print("Processed Text Vectorized Shape:", text_vectorized.shape)
        template_prediction = model.predict(text_vectorized)
        predicted_category = template_prediction[0]

        # Added gl_code mapping to be displayed according to predicted category
        if predicted_category in category_to_gl_mapping:
            gl_code = category_to_gl_mapping[predicted_category]
            return {"predicted_category": predicted_category, "gl_code": gl_code}
        else:
            return {"predicted_category": predicted_category, "gl_code": "N/A"}
    except Exception as e:
        return {"error": f"An error occurred: {str(e)}"}
