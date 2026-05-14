"""CLI entry point for the Meeting Summarizer pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the meeting summarizer."""
    # CLI에서 받을 입력 오디오 파일 경로를 정의합니다.
    parser = argparse.ArgumentParser(
        description="Transcribe a meeting audio file and save Korean meeting minutes."
    )
    parser.add_argument(
        type=Path,
        dest="audio_file",
        help="Path to the meeting audio file.",
    )
    return parser.parse_args()


def build_output_path(audio_file: Path) -> Path:
    """Build the output path next to the original audio file."""
    # 원본 파일과 같은 디렉토리에 "{원본파일명}_회의록.txt" 형식으로 저장합니다.
    base_output_path = audio_file.parent / f"{audio_file.stem}_회의록.txt"
    if not base_output_path.exists():
        return base_output_path

    # 기존 회의록을 덮어쓰지 않도록 번호를 붙인 새 파일명을 사용합니다.
    counter = 1
    while True:
        candidate_path = audio_file.parent / f"{audio_file.stem}_회의록_{counter}.txt"
        if not candidate_path.exists():
            return candidate_path
        counter += 1


def run_pipeline(audio_file: Path) -> Path:
    """Run the transcription and summarization pipeline, then save the result."""
    from dotenv import load_dotenv

    from summarize import summarize_transcript
    from transcribe import transcribe_audio
    from utils import ensure_audio_file

    try:
        # 1. .env 파일에서 OPENAI_API_KEY 같은 환경 변수를 불러옵니다.
        load_dotenv()

        # 2. 입력 오디오 파일이 존재하고 지원되는 형식인지 확인합니다.
        ensure_audio_file(audio_file)

        # 3. 오디오를 텍스트로 변환합니다. 25MB 초과 파일은 transcribe 단계에서 청크 분할됩니다.
        transcript = transcribe_audio(audio_file)

        # 4. transcript를 회의록 형식으로 요약합니다.
        meeting_minutes = summarize_transcript(transcript)

        # 5. 회의록을 터미널에 출력하고 원본 파일과 같은 디렉토리에 저장합니다.
        output_file = build_output_path(audio_file)
        print(meeting_minutes)
        output_file.write_text(meeting_minutes, encoding="utf-8")
        print(f"\n회의록 저장 완료: {output_file}")
        return output_file
    except Exception as exc:
        # 사용자에게 실패 원인을 명확히 보여주고, CLI 종료 코드도 실패로 전달합니다.
        raise RuntimeError(f"회의록 생성 실패: {exc}") from exc


def main() -> int:
    """Load environment variables and start the CLI pipeline."""
    try:
        args = parse_args()
        run_pipeline(args.audio_file)
        return 0
    except Exception as exc:
        # CLI 전체에서 잡히지 않은 오류를 마지막으로 안내합니다.
        print(f"Application error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
