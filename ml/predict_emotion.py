import argparse
import csv
from collections import Counter
from pathlib import Path

import joblib

from pipeline_utils import (
    ENERGY_THRESHOLD,
    SEGMENT_DURATION,
    TARGET_SR,
    clean_audio_file,
    extract_features_from_audio,
    feature_row_to_frame,
    filter_speech_segments,
    segment_audio_array,
    write_segments,
)


def save_predictions(predictions, csv_path: Path):
    fieldnames = [
        "segment_index",
        "start_sec",
        "end_sec",
        "prediction",
        "confidence",
        "energy_mean",
        "energy_std",
        "pitch_mean",
        "pitch_std",
        "speech_segment_path",
    ]

    probability_fields = sorted(
        {
            key
            for row in predictions
            for key in row.keys()
            if key.startswith("prob_")
        }
    )
    fieldnames.extend(probability_fields)

    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(predictions)


def save_summary(
    summary_path: Path,
    input_audio: Path,
    model_path: Path,
    run_dir: Path,
    total_duration_sec: float,
    total_segments: int,
    predictions,
    segment_duration: int,
    energy_threshold: float,
):
    counts = Counter(row["prediction"] for row in predictions)
    dominant_prediction = counts.most_common(1)[0][0] if predictions else "none"
    confidence_values = [row["confidence"] for row in predictions if row["confidence"] != ""]

    lines = [
        f"audio_file={input_audio}",
        f"model_file={model_path}",
        f"run_directory={run_dir}",
        f"duration_sec={total_duration_sec:.2f}",
        f"segment_duration_sec={segment_duration}",
        f"energy_threshold={energy_threshold}",
        f"total_full_segments={total_segments}",
        f"kept_speech_segments={len(predictions)}",
        "overall_counts=" + (", ".join(f"{label}:{count}" for label, count in counts.most_common()) if predictions else "none"),
        f"dominant_prediction={dominant_prediction}",
    ]

    if confidence_values:
        lines.append(f"avg_confidence={sum(confidence_values) / len(confidence_values):.4f}")

    lines.extend(
        [
            "",
            "artifacts=",
            f"cleaned_audio={run_dir / 'cleaned_audio' / 'cleaned_audio.wav'}",
            f"segments_dir={run_dir / 'segments'}",
            f"speech_segments_dir={run_dir / 'speech_segments'}",
            f"segment_predictions_csv={run_dir / 'segment_predictions.csv'}",
            "",
            "sample_predictions=",
        ]
    )

    for row in predictions[:20]:
        confidence_text = f", confidence={row['confidence']:.8f}" if row["confidence"] != "" else ""
        probability_keys = sorted(key for key in row.keys() if key.startswith("prob_"))
        probability_text = ""
        if probability_keys:
            probability_text = ", probs=" + ", ".join(
                f"{key[5:]}:{row[key]:.8f}" for key in probability_keys
            )
        lines.append(
            f"seg={row['segment_index']}, start={row['start_sec']}, end={row['end_sec']}, "
            f"pred={row['prediction']}{confidence_text}{probability_text}"
        )

    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_run_directory(output_root: Path, input_audio: Path) -> Path:
    run_name = f"{input_audio.stem}_analysis"
    run_dir = output_root / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "cleaned_audio").mkdir(exist_ok=True)
    (run_dir / "segments").mkdir(exist_ok=True)
    (run_dir / "speech_segments").mkdir(exist_ok=True)
    return run_dir


def predict_kept_segments(kept_segments, model):
    predictions = []

    for item in kept_segments:
        feature_row = extract_features_from_audio(item["audio"])
        feature_frame = feature_row_to_frame(feature_row)
        prediction = model.predict(feature_frame)[0]

        row = {
            "segment_index": item["segment_index"],
            "start_sec": item["start_sec"],
            "end_sec": item["end_sec"],
            "prediction": prediction,
            "energy_mean": round(feature_row["energy_mean"], 6),
            "energy_std": round(feature_row["energy_std"], 6),
            "pitch_mean": round(feature_row["pitch_mean"], 6),
            "pitch_std": round(feature_row["pitch_std"], 6),
            "speech_segment_path": str(item.get("speech_path", "")),
        }

        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba(feature_frame)[0]
            classes = list(model.classes_)
            row["confidence"] = float(max(probabilities))
            for label, probability in zip(classes, probabilities):
                row[f"prob_{label}"] = float(probability)
        else:
            row["confidence"] = ""

        predictions.append(row)

    return predictions


def main():
    project_root = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(
        description="Run the full emotion inference pipeline on an input audio file."
    )
    parser.add_argument("audio_file", help="Path to an MP3/WAV/MPEG audio file")
    parser.add_argument(
        "--model",
        default=str(project_root / "models" / "best_emotion_model.pkl"),
        help="Path to the trained model file",
    )
    parser.add_argument(
        "--output-root",
        default=str(project_root / "results"),
        help="Directory where the run folder should be created",
    )
    parser.add_argument(
        "--segment-duration",
        type=int,
        default=SEGMENT_DURATION,
        help="Segment length in seconds",
    )
    parser.add_argument(
        "--energy-threshold",
        type=float,
        default=ENERGY_THRESHOLD,
        help="Minimum mean RMS energy required to keep a segment",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=TARGET_SR,
        help="Audio sample rate used for cleaning and feature extraction",
    )
    args = parser.parse_args()

    input_audio = Path(args.audio_file).expanduser().resolve()
    model_path = Path(args.model).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()

    if not input_audio.exists():
        raise FileNotFoundError(f"Audio file not found: {input_audio}")
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    run_dir = build_run_directory(output_root, input_audio)
    cleaned_audio_path = run_dir / "cleaned_audio" / "cleaned_audio.wav"
    csv_path = run_dir / "segment_predictions.csv"
    summary_path = run_dir / "summary.txt"

    model = joblib.load(model_path)
    cleaned_audio = clean_audio_file(input_audio, cleaned_audio_path, target_sr=args.sample_rate)

    segments = segment_audio_array(
        cleaned_audio,
        sr=args.sample_rate,
        segment_duration=args.segment_duration,
    )
    written_segments = write_segments(
        segments,
        run_dir / "segments",
        prefix="segment",
        sr=args.sample_rate,
    )

    kept_segments, _ = filter_speech_segments(
        written_segments,
        output_dir=run_dir / "speech_segments",
        threshold=args.energy_threshold,
        sr=args.sample_rate,
    )

    predictions = predict_kept_segments(kept_segments, model)
    save_predictions(predictions, csv_path)
    save_summary(
        summary_path,
        input_audio,
        model_path,
        run_dir,
        len(cleaned_audio) / args.sample_rate,
        len(written_segments),
        predictions,
        args.segment_duration,
        args.energy_threshold,
    )

    counts = Counter(row["prediction"] for row in predictions)
    dominant_prediction = counts.most_common(1)[0][0] if predictions else "none"

    print(f"Run directory: {run_dir}")
    print(f"Cleaned audio: {cleaned_audio_path}")
    print(f"Total segments created: {len(written_segments)}")
    print(f"Speech segments kept: {len(predictions)}")
    print(
        "Prediction counts: "
        + (", ".join(f"{label}:{count}" for label, count in counts.most_common()) if predictions else "none")
    )
    print(f"Dominant prediction: {dominant_prediction}")
    print(f"Summary file: {summary_path}")
    print(f"CSV file: {csv_path}")


if __name__ == "__main__":
    main()
