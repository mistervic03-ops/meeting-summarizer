"""Meeting Summarizer 파이프라인의 CLI 진입점입니다."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """회의록 생성 CLI 인자를 파싱합니다."""
    # CLI에서는 오디오 파일 경로 하나만 받아 전체 파이프라인을 실행합니다.
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
    """원본 오디오 파일 옆에 저장할 회의록 경로를 만듭니다."""
    # 같은 이름의 회의록이 없으면 가장 읽기 쉬운 기본 파일명을 사용합니다.
    base_output_path = audio_file.parent / f"{audio_file.stem}_회의록.txt"
    if not base_output_path.exists():
        return base_output_path

    # 이미 존재하면 기존 결과를 덮어쓰지 않도록 번호를 붙입니다.
    counter = 1
    while True:
        candidate_path = audio_file.parent / f"{audio_file.stem}_회의록_{counter}.txt"
        if not candidate_path.exists():
            return candidate_path
        counter += 1


def run_pipeline(audio_file: Path) -> Path:
    """STT와 요약 파이프라인을 실행한 뒤 결과를 저장합니다."""
    from dotenv import load_dotenv

    from summarize import summarize_transcript
    from transcribe import transcribe_audio
    from utils import ensure_audio_file

    try:
        # CLI 실행 시에도 .env의 API 키와 모델 설정을 사용할 수 있게 로드합니다.
        load_dotenv()
        ensure_audio_file(audio_file)

        # STT와 요약 모듈은 파일 분할과 긴 transcript 처리를 내부에서 담당합니다.
        transcript = transcribe_audio(audio_file)
        summary = summarize_transcript(transcript)
        meeting_minutes = summary["minutes"]

        # 터미널 확인과 파일 저장을 모두 제공해 CLI 단독 사용성을 유지합니다.
        output_file = build_output_path(audio_file)
        print(meeting_minutes)
        output_file.write_text(meeting_minutes, encoding="utf-8")
        print(f"\n회의록 저장 완료: {output_file}")
        return output_file
    except Exception as exc:
        raise RuntimeError(f"회의록 생성 실패: {exc}") from exc


def main() -> int:
    """환경 변수를 로드하고 CLI 파이프라인을 시작합니다."""
    try:
        args = parse_args()
        run_pipeline(args.audio_file)
        return 0
    except Exception as exc:
        # shell에서 실패 여부를 알 수 있도록 1을 반환합니다.
        print(f"Application error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
