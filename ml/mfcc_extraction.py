from pathlib import Path

import pandas as pd

from pipeline_utils import TARGET_SR, extract_features_from_file


SEGMENT_DIR = Path("voice_module/dataset_segments")
LABEL_FILE = Path("voice_module/labels/voice_labels.csv")
OUTPUT_FILE = Path("voice_module/voice_features.csv")


def main():
    labels_df = pd.read_csv(LABEL_FILE)
    label_map = dict(zip(labels_df["filename"], labels_df["emotion_label"]))

    rows = []

    for audio_path in SEGMENT_DIR.iterdir():
        if audio_path.suffix.lower() != ".wav":
            continue

        if audio_path.name not in label_map:
            continue

        try:
            row = extract_features_from_file(audio_path, sr=TARGET_SR)
            row["emotion_label"] = label_map[audio_path.name]
            row["filename"] = audio_path.name
            rows.append(row)
        except Exception as exc:
            print("Error processing:", audio_path.name, exc)

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_FILE, index=False)

    print("Feature dataset saved:", OUTPUT_FILE)
    print("Total samples:", len(df))


if __name__ == "__main__":
    main()
