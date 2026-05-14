"""CLI entry point for the Meeting Summarizer pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

from dotenv import load_dotenv

from summarize import summarize_meeting
from transcribe import transcribe_audio
from utils import cleanup_temp_files, ensure_audio_file, split_audio_if_needed


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the meeting summarizer."""
    parser = argparse.ArgumentParser(description="Summarize a meeting audio file.")
    parser.add_argument("audio_file", type=Path, help="Path to the meeting audio file.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("meeting_summary.txt"),
        help="Path where the meeting summary text file will be written.",
    )
    return parser.parse_args()


def run_pipeline(audio_file: Path, output_file: Path) -> None:
    """Run the audio transcription and meeting summary pipeline."""
    temp_files: list[Path] = []

    try:
        ensure_audio_file(audio_file)
        audio_chunks = split_audio_if_needed(audio_file)
        temp_files.extend(chunk for chunk in audio_chunks if chunk != audio_file)

        transcript = transcribe_audio(audio_chunks)
        summary = summarize_meeting(transcript)

        output_file.write_text(summary, encoding="utf-8")
        print(f"Meeting summary saved to: {output_file}")
    except Exception as exc:
        print(f"Failed to summarize meeting audio: {exc}")
        raise
    finally:
        cleanup_temp_files(temp_files)


def main() -> None:
    """Load environment variables and start the CLI pipeline."""
    try:
        load_dotenv()
        args = parse_args()
        run_pipeline(args.audio_file, args.output)
    except Exception as exc:
        print(f"Application error: {exc}")


if __name__ == "__main__":
    main()
