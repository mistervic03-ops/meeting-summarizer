"""Utility helpers for audio splitting and file cleanup."""

from __future__ import annotations

from pathlib import Path
from shutil import which
from tempfile import mkdtemp

from pydub import AudioSegment


# OpenAI STT API에 안전하게 넘기기 위한 파일 크기 기준입니다.
# multipart 업로드 오버헤드와 MB 계산 차이를 고려해 25MB보다 보수적으로 잡습니다.
MAX_AUDIO_SIZE_BYTES = 24_000_000

# 현재 프로젝트에서 입력으로 허용할 오디오 확장자 목록입니다.
SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}

# pydub/ffmpeg에 넘길 포맷명을 확장자 기준으로 매핑합니다.
AUDIO_FORMAT_BY_EXTENSION = {
    ".mp3": "mp3",
    ".mp4": "mp4",
    ".mpeg": "mp3",
    ".mpga": "mp3",
    ".m4a": "mp4",
    ".wav": "wav",
    ".webm": "webm",
}

# 인코딩 후 파일 크기가 살짝 커지는 상황을 피하기 위한 안전 여유입니다.
CHUNK_SIZE_SAFETY_RATIO = 0.9

# 너무 작은 조각으로 무한히 줄어드는 것을 막는 최소 청크 길이입니다.
MIN_CHUNK_DURATION_MS = 1_000

# 임시 청크 파일을 담는 폴더 이름 접두사입니다.
TEMP_CHUNK_DIR_PREFIX = "meeting_summarizer_chunks_"

# pydub이 실제 오디오 디코딩/인코딩에 사용하는 외부 실행 파일 후보입니다.
AUDIO_CONVERTER_CANDIDATES = ("ffmpeg", "avconv")
AUDIO_PROBE_CANDIDATES = ("ffprobe", "avprobe")


def ensure_audio_file(audio_file: Path) -> None:
    """Validate that the provided path points to a supported audio file."""
    try:
        # 파일이 실제로 존재하는지 확인합니다.
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file does not exist: {audio_file}")

        # 디렉터리나 다른 경로가 아니라 일반 파일인지 확인합니다.
        if not audio_file.is_file():
            raise ValueError(f"Audio path is not a file: {audio_file}")

        # 지원하지 않는 확장자는 이후 STT 처리 전에 명확히 거절합니다.
        if audio_file.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
            raise ValueError(f"Unsupported audio file extension: {audio_file.suffix}")
    except Exception as exc:
        raise RuntimeError(f"Audio file validation failed: {exc}") from exc


def split_audio_if_needed(audio_file: Path) -> list[Path]:
    """Return audio chunks, splitting the file first when it exceeds the size limit."""
    try:
        ensure_audio_file(audio_file)

        # 25MB 이하 파일은 분할하지 않고 그대로 API 처리 대상으로 반환합니다.
        if audio_file.stat().st_size <= MAX_AUDIO_SIZE_BYTES:
            return [audio_file]

        # 25MB 초과 파일은 실제 분할 함수에 위임합니다.
        return split_audio_file(audio_file)
    except Exception as exc:
        raise RuntimeError(f"Audio splitting check failed: {exc}") from exc


def split_audio_file(audio_file: Path) -> list[Path]:
    """Split a large audio file into chunks below the configured size limit."""
    chunk_files: list[Path] = []
    temp_dir: Path | None = None

    try:
        ensure_audio_file(audio_file)
        ensure_audio_tooling_available()

        # 원본 파일을 pydub AudioSegment로 읽어 전체 길이를 밀리초 단위로 확인합니다.
        audio_format = get_audio_format(audio_file)
        audio = AudioSegment.from_file(audio_file, format=audio_format)
        if len(audio) <= 0:
            raise ValueError(f"Audio file is empty or unreadable: {audio_file}")

        # 임시 청크 파일은 시스템 임시 폴더 아래 별도 디렉터리에 생성합니다.
        temp_dir = Path(mkdtemp(prefix=TEMP_CHUNK_DIR_PREFIX, dir="/private/tmp"))
        chunk_duration_ms = calculate_initial_chunk_duration_ms(audio_file, len(audio))

        start_ms = 0
        chunk_index = 1

        while start_ms < len(audio):
            end_ms = min(start_ms + chunk_duration_ms, len(audio))
            chunk_path, actual_end_ms = export_chunk_under_size(
                audio=audio,
                start_ms=start_ms,
                end_ms=end_ms,
                output_dir=temp_dir,
                source_file=audio_file,
                chunk_index=chunk_index,
                audio_format=audio_format,
            )

            chunk_files.append(chunk_path)
            chunk_duration_ms = max(actual_end_ms - start_ms, MIN_CHUNK_DURATION_MS)
            start_ms = actual_end_ms
            chunk_index += 1

        return chunk_files
    except Exception as exc:
        cleanup_targets = [*chunk_files]
        if temp_dir is not None:
            cleanup_targets.append(temp_dir)
        cleanup_temp_files(cleanup_targets)
        raise RuntimeError(f"Audio file splitting failed for {audio_file}: {exc}") from exc


def cleanup_temp_files(temp_files: list[Path]) -> None:
    """Delete temporary files and directories created during audio processing."""
    touched_dirs: set[Path] = set()

    # 처리 중 만들어진 임시 파일을 하나씩 삭제합니다.
    for temp_file in temp_files:
        try:
            if temp_file.is_dir() and temp_file.name.startswith(TEMP_CHUNK_DIR_PREFIX):
                cleanup_temp_directory(temp_file)
                continue

            if temp_file.exists():
                touched_dirs.add(temp_file.parent)
                temp_file.unlink()
        except Exception as exc:
            # 정리 실패는 전체 파이프라인을 중단시키지 않고 메시지만 출력합니다.
            print(f"Failed to delete temporary file {temp_file}: {exc}")

    # 청크 파일을 담았던 임시 디렉터리가 비어 있으면 함께 삭제합니다.
    for temp_dir in touched_dirs:
        try:
            if temp_dir.name.startswith(TEMP_CHUNK_DIR_PREFIX) and temp_dir.exists():
                temp_dir.rmdir()
        except Exception as exc:
            print(f"Failed to delete temporary directory {temp_dir}: {exc}")


def cleanup_temp_directory(temp_dir: Path) -> None:
    """Delete a temporary chunk directory and any files directly inside it."""
    try:
        for child_path in temp_dir.iterdir():
            if child_path.is_file():
                child_path.unlink()
        temp_dir.rmdir()
    except Exception as exc:
        print(f"Failed to delete temporary directory {temp_dir}: {exc}")


def ensure_audio_tooling_available() -> None:
    """Ensure ffmpeg tooling required by pydub is available."""
    # pydub은 Python 패키지 외에 ffmpeg/ffprobe 같은 시스템 도구가 필요합니다.
    converter = find_executable(AUDIO_CONVERTER_CANDIDATES)
    probe = find_executable(AUDIO_PROBE_CANDIDATES)

    if converter is None or probe is None:
        raise RuntimeError(
            "ffmpeg tooling is missing. Install ffmpeg so pydub can read and split audio files."
        )


def find_executable(candidates: tuple[str, ...]) -> str | None:
    """Return the first available executable from the candidate names."""
    for executable_name in candidates:
        executable_path = which(executable_name)
        if executable_path is not None:
            return executable_path
    return None


def get_audio_format(audio_file: Path) -> str:
    """Return the pydub/ffmpeg audio format for a supported audio file."""
    try:
        return AUDIO_FORMAT_BY_EXTENSION[audio_file.suffix.lower()]
    except KeyError as exc:
        raise ValueError(f"Unsupported audio file extension: {audio_file.suffix}") from exc


def calculate_initial_chunk_duration_ms(audio_file: Path, duration_ms: int) -> int:
    """Estimate an initial chunk duration that should export below the size limit."""
    if duration_ms <= 0:
        raise ValueError("Audio duration must be greater than zero.")

    # 원본 크기와 재생 시간을 기준으로 25MB 이하가 될 만한 길이를 보수적으로 추정합니다.
    bytes_per_ms = audio_file.stat().st_size / duration_ms
    estimated_duration = int((MAX_AUDIO_SIZE_BYTES * CHUNK_SIZE_SAFETY_RATIO) / bytes_per_ms)
    return max(min(estimated_duration, duration_ms), MIN_CHUNK_DURATION_MS)


def export_chunk_under_size(
    audio: AudioSegment,
    start_ms: int,
    end_ms: int,
    output_dir: Path,
    source_file: Path,
    chunk_index: int,
    audio_format: str,
) -> tuple[Path, int]:
    """Export one audio chunk, shrinking its duration until it is below the size limit."""
    current_end_ms = end_ms

    while current_end_ms > start_ms:
        chunk_path = build_chunk_path(output_dir, source_file, chunk_index)
        audio_chunk = audio[start_ms:current_end_ms]
        export_audio_chunk(audio_chunk, chunk_path, audio_format)

        if chunk_path.stat().st_size <= MAX_AUDIO_SIZE_BYTES:
            return chunk_path, current_end_ms

        chunk_path.unlink(missing_ok=True)
        current_duration_ms = current_end_ms - start_ms

        if current_duration_ms <= MIN_CHUNK_DURATION_MS:
            raise ValueError(
                f"Unable to create a chunk below {MAX_AUDIO_SIZE_BYTES} bytes from {source_file}."
            )

        # 실제 export 크기가 크면 현재 구간을 80%로 줄여 다시 시도합니다.
        reduced_duration_ms = max(int(current_duration_ms * 0.8), MIN_CHUNK_DURATION_MS)
        current_end_ms = min(start_ms + reduced_duration_ms, len(audio))

    raise ValueError(f"Unable to create a valid audio chunk from {source_file}.")


def build_chunk_path(output_dir: Path, source_file: Path, chunk_index: int) -> Path:
    """Build a deterministic temporary path for an exported audio chunk."""
    safe_stem = source_file.stem.replace(" ", "_")
    return output_dir / f"{safe_stem}_chunk_{chunk_index:03d}{source_file.suffix.lower()}"


def export_audio_chunk(audio_chunk: AudioSegment, output_path: Path, audio_format: str) -> None:
    """Export an AudioSegment chunk with format-specific encoder options."""
    export_kwargs: dict[str, str] = {"format": audio_format}

    # ffmpeg에서 컨테이너 포맷별 기본 오디오 코덱이 모호한 경우를 보완합니다.
    if audio_format == "mp4":
        export_kwargs["codec"] = "aac"
    elif audio_format == "webm":
        export_kwargs["codec"] = "libopus"

    audio_chunk.export(output_path, **export_kwargs)
