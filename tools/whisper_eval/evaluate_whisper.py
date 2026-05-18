"""GPU faster-whisper 전사 품질 평가용 독립 실행 스크립트입니다.

프로덕션 STT provider나 앱 런타임과 분리해, 단일 오디오 파일의 전사 결과와
기본 timing 지표만 확인합니다.
"""

from __future__ import annotations

import argparse
import os
import re
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "distil-large-v3"
DEFAULT_DEVICE = "cuda"
DEFAULT_COMPUTE_TYPE = "float16"
DEFAULT_LANGUAGE = "ko"


def parse_args() -> argparse.Namespace:
    """CLI 인자와 환경 변수 기본값을 파싱합니다."""
    parser = argparse.ArgumentParser(description="Run a standalone faster-whisper STT evaluation.")
    parser.add_argument("audio_file", type=Path, help="Transcribe할 오디오 파일 경로")
    parser.add_argument("--model", default=os.getenv("WHISPER_EVAL_MODEL", DEFAULT_MODEL))
    parser.add_argument("--device", default=os.getenv("WHISPER_EVAL_DEVICE", DEFAULT_DEVICE))
    parser.add_argument("--compute-type", default=os.getenv("WHISPER_EVAL_COMPUTE_TYPE", DEFAULT_COMPUTE_TYPE))
    parser.add_argument("--language", default=os.getenv("WHISPER_EVAL_LANGUAGE", DEFAULT_LANGUAGE))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.getenv("WHISPER_EVAL_OUTPUT_DIR", Path(__file__).resolve().parent / "outputs")),
        help="Transcript 저장 디렉터리",
    )
    parser.add_argument("--output-file", type=Path, default=None, help="지정 시 transcript 저장 파일 경로")
    return parser.parse_args()


def import_whisper_model() -> Any:
    """faster-whisper 설치 여부를 확인하고 WhisperModel을 반환합니다."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is required for this evaluation tool. "
            "Install it in the active environment with `python3 -m pip install faster-whisper` "
            "or `python3 -m pip install -r requirements.txt`."
        ) from exc
    return WhisperModel


def get_audio_duration_seconds(audio_file: Path) -> float | None:
    """가능하면 오디오 길이를 초 단위로 반환합니다."""
    try:
        from pydub import AudioSegment

        return len(AudioSegment.from_file(audio_file)) / 1000
    except Exception:
        pass

    if audio_file.suffix.lower() != ".wav":
        return None

    try:
        with wave.open(str(audio_file), "rb") as wav_file:
            frames = wav_file.getnframes()
            frame_rate = wav_file.getframerate()
            if frame_rate <= 0:
                return None
            return frames / float(frame_rate)
    except Exception:
        return None


def build_output_path(audio_file: Path, output_dir: Path, output_file: Path | None, model: str, device: str) -> Path:
    """Transcript 저장 경로를 만듭니다."""
    if output_file is not None:
        return output_file

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_slug = slugify(model)
    device_slug = slugify(device)
    return output_dir / f"{audio_file.stem}_{model_slug}_{device_slug}_{timestamp}.txt"


def slugify(value: str) -> str:
    """파일명에 쓰기 쉬운 값으로 정리합니다."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "value"


def save_transcript(output_path: Path, transcript: str) -> None:
    """Transcript를 UTF-8 텍스트 파일로 저장합니다."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(transcript, encoding="utf-8")


def main() -> int:
    """faster-whisper 모델을 로드하고 단일 오디오 파일을 전사합니다."""
    args = parse_args()
    audio_file = args.audio_file.expanduser().resolve()
    if not audio_file.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_file}")

    WhisperModel = import_whisper_model()
    audio_duration_seconds = get_audio_duration_seconds(audio_file)

    print("Whisper GPU evaluation")
    print(f"audio_file={audio_file}")
    print(f"model={args.model}")
    print(f"device={args.device}")
    print(f"compute_type={args.compute_type}")
    print(f"language={args.language}")
    if audio_duration_seconds is not None:
        print(f"audio_duration_seconds={audio_duration_seconds:.3f}")
    else:
        print("audio_duration_seconds=unknown")

    model_load_started_at = time.perf_counter()
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    model_load_seconds = time.perf_counter() - model_load_started_at

    transcription_started_at = time.perf_counter()
    segments, info = model.transcribe(str(audio_file), language=args.language)
    transcript = " ".join(segment.text.strip() for segment in segments if segment.text.strip())
    transcription_seconds = time.perf_counter() - transcription_started_at

    output_path = build_output_path(
        audio_file=audio_file,
        output_dir=args.output_dir.expanduser().resolve(),
        output_file=args.output_file.expanduser().resolve() if args.output_file else None,
        model=args.model,
        device=args.device,
    )
    save_transcript(output_path, transcript)

    print(f"detected_language={getattr(info, 'language', 'unknown')}")
    print(f"language_probability={getattr(info, 'language_probability', 'unknown')}")
    print(f"model_load_seconds={model_load_seconds:.3f}")
    print(f"transcription_seconds={transcription_seconds:.3f}")
    if audio_duration_seconds and transcription_seconds > 0:
        print(f"realtime_factor={transcription_seconds / audio_duration_seconds:.3f}")
    print(f"output_path={output_path}")
    print()
    print("Transcript")
    print(transcript)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
