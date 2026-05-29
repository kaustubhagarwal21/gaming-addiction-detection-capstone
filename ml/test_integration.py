import joblib
import numpy as np
import os
import sys

try:
    import librosa
except ImportError:
    librosa = None


# Set up paths relative to CAPSTONE root
script_dir = os.path.dirname(os.path.abspath(__file__))
capstone_root = os.path.dirname(script_dir)  # Go up one level to CAPSTONE

# Define model paths
behavior_model_path = os.path.join(capstone_root, "models", "behavior_model.pkl")
chat_model_path = os.path.join(capstone_root, "models", "chat_model.pkl")
voice_model_path = os.path.join(capstone_root, "models", "voice_model.pkl")
vectorizer_path = os.path.join(capstone_root, "chat", "A_REVIEW_2", "models", "tfidf_vectorizer.pkl")

# Load models
print("\n" + "="*60)
print("Loading models...")
print("="*60)
behavior_model = joblib.load(behavior_model_path)
chat_model = joblib.load(chat_model_path)
voice_model = joblib.load(voice_model_path)
vectorizer = joblib.load(vectorizer_path)
print("✓ All models loaded successfully!\n")

def get_behavior_input():
    """Get behavioral features from user (demo: 5 features, full: 20 features)"""
    print("\n" + "-"*60)
    print("BEHAVIOR INPUT")
    print("-"*60)
    
    # Ask user for mode
    while True:
        mode = input("Choose mode: (d)emo with 5 features or (f)ull with 20 features? (d/f): ").strip().lower()
        if mode in ['d', 'demo']:
            return get_demo_behavior_input()
        elif mode in ['f', 'full']:
            return get_full_behavior_input()
        else:
            print("Please enter 'd' for demo or 'f' for full")

def get_demo_behavior_input():
    """Demo mode: Get 5 key behavior features + use defaults for rest"""
    print("\nDEMO MODE - Enter 5 key behavioral features:")
    print("1. Daily play time (hours)")
    print("2. Weekly play time (hours)")
    print("3. Sessions per day")
    print("4. Days played per week")
    print("5. Craving score (0-10)")
    
    while True:
        try:
            user_input = input("\nEnter 5 values (comma-separated, or press Enter for defaults): ").strip()
            if not user_input:
                demo_values = [6, 30, 5, 7, 7]
                print(f"Using default demo values: {demo_values}")
                break
            values = [float(x.strip()) for x in user_input.split(",")]
            if len(values) != 5:
                print(f"Error: Expected 5 values, got {len(values)}. Please try again.")
                continue
            demo_values = values
            print(f"Using your values: {demo_values}")
            break
        except EOFError:
            demo_values = [6, 30, 5, 7, 7]
            print(f"Using default demo values: {demo_values}")
            break
        except ValueError:
            print("Error: Invalid input. Please enter 5 comma-separated numbers.")
    
    # Map demo 5 features to full 20 features
    # [daily, weekly, sessions, days_per_week, craving] -> [all 20]
    behavior_input = [
        demo_values[0],          # daily_play_time
        demo_values[1],          # weekly_play_time
        demo_values[2],          # sessions_per_day
        60,                      # avg_session_duration (default)
        0.5,                     # late_night_play_ratio (default)
        demo_values[3],          # days_played_per_week
        14,                      # longest_play_streak_days (default)
        5,                       # binge_sessions_per_week (default)
        30,                      # avg_break_between_sessions (default)
        0.3,                     # rapid_relogin_ratio (default)
        demo_values[4],          # urge_to_continue_score
        3,                       # loss_of_time_awareness_score (default)
        2,                       # control_loss_score (default)
        demo_values[4] - 1,      # craving_score (based on feature 5)
        5,                       # tolerance_score (default)
        2,                       # missed_sleep_days_per_week (default)
        3,                       # fatigue_after_play_score (default)
        4,                       # routine_disruption_score (default)
        5,                       # neglect_responsibilities_score (default)
        4                        # gaming_priority_score (default)
    ]
    
    return behavior_input

def get_full_behavior_input():
    """Full mode: Get all 20 behavior features"""
    print("\nFULL MODE - Enter all 20 behavioral features:")
    print("Features: daily_play_time, weekly_play_time, sessions_per_day, avg_session_duration,")
    print("          late_night_ratio, days_played_per_week, longest_play_streak, binge_sessions,")
    print("          avg_break_between_sessions, rapid_relogin_ratio, urge_to_continue, loss_of_time_awareness,")
    print("          control_loss, craving, tolerance, missed_sleep_days, fatigue, routine_disruption,")
    print("          neglect_responsibilities, gaming_priority")
    
    while True:
        try:
            user_input = input("\nEnter 20 values (or press Enter for default): ").strip()
            if not user_input:
                behavior_input = [6,30,5,60,0.7,7,10,4,10,0.2,0.8,200,0.9,2,0.8,0.2,0.6,0.4,1,0.9]
                print(f"Using default behavior input")
                break
            values = [float(x.strip()) for x in user_input.split(",")]
            if len(values) != 20:
                print(f"Error: Expected 20 values, got {len(values)}. Please try again.")
                continue
            behavior_input = values
            break
        except EOFError:
            behavior_input = [6,30,5,60,0.7,7,10,4,10,0.2,0.8,200,0.9,2,0.8,0.2,0.6,0.4,1,0.9]
            print(f"Using default behavior input")
            break
        except ValueError:
            print("Error: Invalid input. Please enter 20 comma-separated numbers.")
    
    return behavior_input

def get_chat_input():
    """Get chat text from user"""
    print("\n" + "-"*60)
    print("CHAT INPUT")
    print("-"*60)
    try:
        chat_text = input("Enter gaming chat text (or press Enter for default): ").strip()
        if not chat_text:
            chat_text = "I can't stop playing this game"
            print(f"Using default: '{chat_text}'")
    except EOFError:
        chat_text = "I can't stop playing this game"
        print(f"Using default: '{chat_text}'")
    return chat_text

def get_voice_input():
    """Get voice features from an existing audio file in data/voice/raw_audio"""
    print("\n" + "-"*60)
    print("VOICE INPUT")
    print("-"*60)

    audio_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'voice', 'raw_audio')
    files = [f for f in os.listdir(audio_dir) if f.lower().endswith(('.wav', '.mp3', '.flac', '.ogg'))]

    if not files:
        raise FileNotFoundError(f"No audio files found in {audio_dir}")

    print("Available audio files:")
    for idx, fn in enumerate(files, 1):
        print(f"  {idx}. {fn}")

    if librosa is None:
        raise ImportError('librosa is required for audio feature extraction. Please install it with pip install librosa')

    while True:
        try:
            choice = input("Select an audio file by number (or press Enter for 1): ").strip()
            if not choice:
                choice = '1'
            choice = int(choice)
            if not 1 <= choice <= len(files):
                print(f"Please choose a number between 1 and {len(files)}")
                continue
            break
        except EOFError:
            choice = 1
            break
        except ValueError:
            print("Invalid selection. Enter a numeric value.")

    selected_file = files[choice-1]
    audio_path = os.path.join(audio_dir, selected_file)

    print(f"Loading audio file: {audio_path}")

    y, sr = librosa.load(audio_path, sr=None, mono=True)

    # Extract 17 MFCC-like features (mean of first 17 MFCC coefficients)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=17)
    mfcc_means = np.mean(mfcc, axis=1)

    print(f"Extracted MFCC features (17 dims) from {selected_file}")

    return mfcc_means.tolist()

def predict_and_display(behavior_input, chat_text, voice_input):
    """Make predictions and display results"""
    
    # Behavior Prediction
    behavior_pred = behavior_model.predict([behavior_input])[0]
    behavior_score = behavior_pred / 2
    
    # Chat Prediction
    chat_features = vectorizer.transform([chat_text])
    chat_score = chat_model.predict(chat_features)[0]
    
    # Voice Prediction
    voice_pred = voice_model.predict([np.array(voice_input)])[0]
    emotion_map = {
        "neutral": 0.2,
        "excited": 0.6,
        "frustrated": 0.8,
        "angry": 0.9
    }
    voice_score = emotion_map.get(voice_pred, 0.5)
    
    # Final Score
    final_score = 0.4 * behavior_score + 0.3 * chat_score + 0.3 * voice_score
    
    # Determine addiction level
    if final_score < 0.3:
        addiction_level = "Low Addiction"
    elif final_score < 0.6:
        addiction_level = "Medium Addiction"
    else:
        addiction_level = "High Addiction"
    
    # Display Results
    print("\n" + "="*60)
    print("PREDICTION RESULTS")
    print("="*60)
    
    print(f"\n📊 COMPONENT SCORES:")
    print(f"  • Behavior Score:  {behavior_score:.4f}")
    print(f"  • Chat Score:      {chat_score:.4f}")
    print(f"  • Voice Emotion:   {voice_pred}")
    print(f"  • Voice Score:     {voice_score:.4f}")
    
    print(f"\n📈 WEIGHTED CONTRIBUTION:")
    print(f"  {'Category':<20} {'Weight':<10} {'Score':<15}")
    print(f"  {'-'*45}")
    print(f"  {'Behavior':<20} {'40%':<10} {0.4 * behavior_score:<15.4f}")
    print(f"  {'Chat':<20} {'30%':<10} {0.3 * chat_score:<15.4f}")
    print(f"  {'Voice':<20} {'30%':<10} {0.3 * voice_score:<15.4f}")
    print(f"  {'-'*45}")
    print(f"  {'FINAL SCORE':<20} {'100%':<10} {final_score:<15.4f}")
    
    print(f"\n🎮 ADDICTION LEVEL: {addiction_level}")
    print("="*60 + "\n")
    
    return final_score, addiction_level

# Main Interactive Loop
def main():
    while True:
        try:
            # Get user inputs
            behavior_input = get_behavior_input()
            chat_text = get_chat_input()
            voice_input = get_voice_input()
            
            # Make predictions
            final_score, addiction_level = predict_and_display(behavior_input, chat_text, voice_input)
            
            # Ask if user wants to continue
            while True:
                try:
                    response = input("Do you want to test again? (yes/no): ").strip().lower()
                    if response in ['yes', 'y']:
                        break
                    elif response in ['no', 'n']:
                        print("\n" + "="*60)
                        print("Thank you for using the Gaming Addiction Predictor!")
                        print("="*60 + "\n")
                        return
                    else:
                        print("Please enter 'yes' or 'no'")
                except EOFError:
                    print("\n" + "="*60)
                    print("Thank you for using the Gaming Addiction Predictor!")
                    print("="*60 + "\n")
                    return
        
        except KeyboardInterrupt:
            print("\n\nProgram interrupted. Exiting...")
            return
        except Exception as e:
            print(f"\nError occurred: {e}")
            print("Please try again.\n")

if __name__ == "__main__":
    main()