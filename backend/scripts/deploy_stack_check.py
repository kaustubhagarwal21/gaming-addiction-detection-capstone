import os, joblib, numpy as np
HERE = os.path.dirname(__file__); MODELS = os.path.join(HERE, '..', 'models')
print("numpy", np.__version__)

for f in ['behavior_model.pkl', 'chat_model.pkl', 'voice_model.pkl',
          'tfidf_vectorizer.pkl', 'feature_scaler.pkl']:
    obj = joblib.load(os.path.join(MODELS, f))
    print("  loaded", f, "->", type(obj).__name__)

try:
    import librosa
    print("librosa", librosa.__version__, "import OK")
except Exception as e:
    print("librosa FAIL:", repr(e)[:140])

try:
    import shap
    bm = joblib.load(os.path.join(MODELS, 'behavior_model.pkl'))
    sv = shap.TreeExplainer(bm).shap_values(np.zeros((1, bm.n_features_in_)))
    nclass = len(sv) if isinstance(sv, list) else np.asarray(sv).shape
    print("shap", shap.__version__, "OK -> shap_values", nclass)
except Exception as e:
    print("shap NOT usable:", repr(e)[:140])

print("STACK_CHECK_DONE")
