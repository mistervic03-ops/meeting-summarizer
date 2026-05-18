"""오디오 분할과 임시 파일 정리를 위한 유틸리티 함수입니다."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from shutil import which
from tempfile import mkdtemp

from pydub import AudioSegment


logger = logging.getLogger(__name__)

# OpenAI STT 업로드 제한보다 여유 있게 잡은 청크 크기입니다.
MAX_AUDIO_SIZE_BYTES = 24_000_000

# 현재 입력으로 허용하는 오디오 확장자입니다.
SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}

# pydub/ffmpeg가 이해하는 포맷명으로 확장자를 변환합니다.
AUDIO_FORMAT_BY_EXTENSION = {
    ".mp3": "mp3",
    ".mp4": "mp4",
    ".mpeg": "mp3",
    ".mpga": "mp3",
    ".m4a": "mp4",
    ".wav": "wav",
    ".webm": "webm",
}

# 인코딩 후 파일 크기 변동을 고려해 초기 청크 길이를 보수적으로 계산합니다.
CHUNK_SIZE_SAFETY_RATIO = 0.9

# 청크 길이가 지나치게 작아지는 무한 축소 상황을 막습니다.
MIN_CHUNK_DURATION_MS = 1_000

# 임시 청크 디렉터리를 식별하고 안전하게 정리하기 위한 접두사입니다.
TEMP_CHUNK_DIR_PREFIX = "meeting_summarizer_chunks_"

# pydub이 내부적으로 호출하는 외부 오디오 도구 후보입니다.
AUDIO_CONVERTER_CANDIDATES = ("ffmpeg", "avconv")
AUDIO_PROBE_CANDIDATES = ("ffprobe", "avprobe")


@dataclass(frozen=True)
class AudioChunkConfig:
    """오디오 청크 분할 기준을 담는 설정입니다."""

    duration_seconds: int | None = None
    overlap_seconds: int = 0


def ensure_audio_file(audio_file: Path) -> None:
    """입력 경로가 지원되는 오디오 파일인지 검증합니다."""
    try:
        # 존재하지 않는 파일, 디렉터리, 지원하지 않는 확장자를 초기에 걸러냅니다.
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file does not exist: {audio_file}")

        if not audio_file.is_file():
            raise ValueError(f"Audio path is not a file: {audio_file}")

        if audio_file.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
            raise ValueError(f"Unsupported audio file extension: {audio_file.suffix}")
    except Exception as exc:
        raise RuntimeError(f"Audio file validation failed: {exc}") from exc


def split_audio_if_needed(audio_file: Path, chunk_config: AudioChunkConfig | None = None) -> list[Path]:
    """크기 제한을 넘으면 파일을 먼저 분할한 뒤 오디오 청크 목록을 반환합니다."""
    try:
        ensure_audio_file(audio_file)
        chunk_config = chunk_config or AudioChunkConfig()

        # plain STT는 기존 크기 기반 동작을 유지합니다.
        if chunk_config.duration_seconds is None and audio_file.stat().st_size <= MAX_AUDIO_SIZE_BYTES:
            return [audio_file]

        return split_audio_file(audio_file, chunk_config=chunk_config)
    except Exception as exc:
        raise RuntimeError(f"Audio splitting check failed: {exc}") from exc


def split_audio_file(audio_file: Path, chunk_config: AudioChunkConfig | None = None) -> list[Path]:
    """큰 오디오 파일을 설정된 크기 제한 이하의 청크로 분할합니다."""
    chunk_files: list[Path] = []
    temp_dir: Path | None = None

    try:
        # pydub은 ffmpeg 계열 도구가 없으면 대부분의 포맷을 처리할 수 없습니다.
        ensure_audio_file(audio_file)
        ensure_audio_tooling_available()

        # 전체 오디오를 읽어 길이 기반으로 청크 경계를 계산합니다.
        audio_format = get_audio_format(audio_file)
        audio = AudioSegment.from_file(audio_file, format=audio_format)
        if len(audio) <= 0:
            raise ValueError(f"Audio file is empty or unreadable: {audio_file}")

        chunk_config = chunk_config or AudioChunkConfig()
        fixed_duration_ms = resolve_fixed_chunk_duration_ms(chunk_config, len(audio))

        # 시간 기준 설정이 있고 원본이 단일 청크로 충분하면 원본을 그대로 사용합니다.
        if fixed_duration_ms is not None and len(audio) <= fixed_duration_ms and audio_file.stat().st_size <= MAX_AUDIO_SIZE_BYTES:
            logger.info(
                "audio_chunking mode=fixed skipped source=%s duration_seconds=%.1f target_seconds=%s",
                audio_file,
                len(audio) / 1000,
                chunk_config.duration_seconds,
            )
            return [audio_file]

        # 모든 청크는 /private/tmp 하위의 전용 임시 디렉터리에 생성합니다.
        temp_dir = Path(mkdtemp(prefix=TEMP_CHUNK_DIR_PREFIX, dir="/private/tmp"))
        chunk_files = export_audio_chunks(audio, audio_file, temp_dir, audio_format, chunk_config=chunk_config)
        logger.info(
            "audio_chunking completed source=%s chunk_count=%s duration_seconds=%.1f target_seconds=%s overlap_seconds=%s",
            audio_file,
            len(chunk_files),
            len(audio) / 1000,
            chunk_config.duration_seconds or "size-based",
            chunk_config.overlap_seconds,
        )
        return chunk_files
    except Exception as exc:
        # 분할 중 실패하면 지금까지 만든 청크와 임시 디렉터리를 즉시 정리합니다.
        cleanup_targets = [*chunk_files]
        if temp_dir is not None:
            cleanup_targets.append(temp_dir)
        cleanup_temp_files(cleanup_targets)
        raise RuntimeError(f"Audio file splitting failed for {audio_file}: {exc}") from exc


def export_audio_chunks(
    audio: AudioSegment,
    source_file: Path,
    output_dir: Path,
    audio_format: str,
    chunk_config: AudioChunkConfig | None = None,
) -> list[Path]:
    """모든 오디오 청크를 설정된 크기 제한 이하로 export합니다."""
    # 원본 파일 크기/길이 비율로 첫 청크 길이를 추정한 뒤 실제 export 크기로 보정합니다.
    chunk_files: list[Path] = []
    chunk_config = chunk_config or AudioChunkConfig()
    fixed_duration_ms = resolve_fixed_chunk_duration_ms(chunk_config, len(audio))
    overlap_ms = resolve_chunk_overlap_ms(chunk_config, fixed_duration_ms)
    chunk_duration_ms = fixed_duration_ms or calculate_initial_chunk_duration_ms(source_file, len(audio))
    start_ms = 0
    chunk_index = 1

    while start_ms < len(audio):
        end_ms = min(start_ms + chunk_duration_ms, len(audio))
        chunk_path, actual_end_ms = export_chunk_under_size(
            audio=audio,
            start_ms=start_ms,
            end_ms=end_ms,
            output_dir=output_dir,
            source_file=source_file,
            chunk_index=chunk_index,
            audio_format=audio_format,
        )

        chunk_files.append(chunk_path)
        actual_duration_ms = max(actual_end_ms - start_ms, MIN_CHUNK_DURATION_MS)
        chunk_duration_ms = fixed_duration_ms or actual_duration_ms
        logger.info(
            "audio_chunking chunk_index=%s start_seconds=%.1f end_seconds=%.1f duration_seconds=%.1f overlap_seconds=%.1f path=%s",
            chunk_index,
            start_ms / 1000,
            actual_end_ms / 1000,
            actual_duration_ms / 1000,
            overlap_ms / 1000,
            chunk_path,
        )

        if actual_end_ms >= len(audio):
            break

        next_start_ms = actual_end_ms - overlap_ms
        if next_start_ms <= start_ms:
            next_start_ms = actual_end_ms
        start_ms = next_start_ms
        chunk_index += 1

    return chunk_files


def resolve_fixed_chunk_duration_ms(chunk_config: AudioChunkConfig, audio_duration_ms: int) -> int | None:
    """시간 기준 청크 길이를 ms로 변환합니다."""
    if chunk_config.duration_seconds is None:
        return None
    if chunk_config.duration_seconds <= 0:
        raise ValueError("Chunk duration seconds must be greater than zero.")
    return max(min(chunk_config.duration_seconds * 1000, audio_duration_ms), MIN_CHUNK_DURATION_MS)


def resolve_chunk_overlap_ms(chunk_config: AudioChunkConfig, chunk_duration_ms: int | None) -> int:
    """청크 overlap 값을 안전한 ms 범위로 제한합니다."""
    if chunk_config.overlap_seconds < 0:
        raise ValueError("Chunk overlap seconds must be zero or greater.")
    if chunk_duration_ms is None or chunk_config.overlap_seconds == 0:
        return 0

    requested_overlap_ms = chunk_config.overlap_seconds * 1000
    max_overlap_ms = max(chunk_duration_ms - MIN_CHUNK_DURATION_MS, 0)
    return min(requested_overlap_ms, max_overlap_ms)


def cleanup_temp_files(temp_files: list[Path]) -> None:
    """오디오 처리 중 생성된 임시 파일과 디렉터리를 삭제합니다."""
    # 파일 삭제 후 비어 있는 청크 디렉터리까지 지우기 위해 parent를 모아둡니다.
    touched_dirs: set[Path] = set()

    for temp_file in temp_files:
        cleanup_temp_path(temp_file, touched_dirs)

    for temp_dir in touched_dirs:
        try:
            if temp_dir.name.startswith(TEMP_CHUNK_DIR_PREFIX) and temp_dir.exists():
                temp_dir.rmdir()
        except Exception as exc:
            print(f"Failed to delete temporary directory {temp_dir}: {exc}")


def cleanup_temp_path(temp_path: Path, touched_dirs: set[Path]) -> None:
    """임시 경로 하나를 삭제하고 부모 디렉터리를 정리 후보로 기록합니다."""
    try:
        # 청크 디렉터리 자체를 받은 경우 내부 파일까지 정리합니다.
        if temp_path.is_dir() and temp_path.name.startswith(TEMP_CHUNK_DIR_PREFIX):
            cleanup_temp_directory(temp_path)
            return

        if temp_path.exists():
            touched_dirs.add(temp_path.parent)
            temp_path.unlink()
    except Exception as exc:
        print(f"Failed to delete temporary file {temp_path}: {exc}")


def cleanup_temp_directory(temp_dir: Path) -> None:
    """임시 청크 디렉터리와 그 안의 직접 하위 파일을 삭제합니다."""
    try:
        # 이 프로젝트가 만든 임시 디렉터리는 파일만 담는 구조로 유지합니다.
        for child_path in temp_dir.iterdir():
            if child_path.is_file():
                child_path.unlink()
        temp_dir.rmdir()
    except Exception as exc:
        print(f"Failed to delete temporary directory {temp_dir}: {exc}")


def ensure_audio_tooling_available() -> None:
    """pydub에 필요한 ffmpeg 도구가 사용 가능한지 확인합니다."""
    converter = find_executable(AUDIO_CONVERTER_CANDIDATES)
    probe = find_executable(AUDIO_PROBE_CANDIDATES)

    if converter is None or probe is None:
        raise RuntimeError(
            "ffmpeg tooling is missing. Install ffmpeg so pydub can read and split audio files."
        )


def find_executable(candidates: tuple[str, ...]) -> str | None:
    """후보 이름 중 처음으로 찾은 실행 파일 경로를 반환합니다."""
    for executable_name in candidates:
        executable_path = which(executable_name)
        if executable_path is not None:
            return executable_path
    return None


def get_audio_format(audio_file: Path) -> str:
    """지원되는 오디오 파일의 pydub/ffmpeg 포맷명을 반환합니다."""
    try:
        return AUDIO_FORMAT_BY_EXTENSION[audio_file.suffix.lower()]
    except KeyError as exc:
        raise ValueError(f"Unsupported audio file extension: {audio_file.suffix}") from exc


def calculate_initial_chunk_duration_ms(audio_file: Path, duration_ms: int) -> int:
    """크기 제한 이하로 export될 가능성이 높은 초기 청크 길이를 추정합니다."""
    if duration_ms <= 0:
        raise ValueError("Audio duration must be greater than zero.")

    # 원본의 bytes/ms를 기준으로 API 제한보다 약간 작은 청크 길이를 예측합니다.
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
    """오디오 청크 하나를 크기 제한 이하가 될 때까지 줄여 export합니다."""
    current_end_ms = end_ms

    while current_end_ms > start_ms:
        chunk_path = build_chunk_path(output_dir, source_file, chunk_index)
        audio_chunk = audio[start_ms:current_end_ms]
        export_audio_chunk(audio_chunk, chunk_path, audio_format)

        if chunk_path.stat().st_size <= MAX_AUDIO_SIZE_BYTES:
            return chunk_path, current_end_ms

        # export 결과가 크면 파일을 지우고 같은 시작점에서 더 짧게 재시도합니다.
        chunk_path.unlink(missing_ok=True)
        current_duration_ms = current_end_ms - start_ms

        if current_duration_ms <= MIN_CHUNK_DURATION_MS:
            raise ValueError(
                f"Unable to create a chunk below {MAX_AUDIO_SIZE_BYTES} bytes from {source_file}."
            )

        reduced_duration_ms = max(int(current_duration_ms * 0.8), MIN_CHUNK_DURATION_MS)
        current_end_ms = min(start_ms + reduced_duration_ms, len(audio))

    raise ValueError(f"Unable to create a valid audio chunk from {source_file}.")


def build_chunk_path(output_dir: Path, source_file: Path, chunk_index: int) -> Path:
    """export된 오디오 청크의 결정적인 임시 경로를 만듭니다."""
    safe_stem = source_file.stem.replace(" ", "_")
    return output_dir / f"{safe_stem}_chunk_{chunk_index:03d}{source_file.suffix.lower()}"


def export_audio_chunk(audio_chunk: AudioSegment, output_path: Path, audio_format: str) -> None:
    """포맷별 인코더 옵션을 적용해 AudioSegment 청크를 export합니다."""
    export_kwargs: dict[str, str] = {"format": audio_format}

    # 컨테이너 포맷만으로 코덱이 모호한 경우 ffmpeg에 명시적으로 알려줍니다.
    if audio_format == "mp4":
        export_kwargs["codec"] = "aac"
    elif audio_format == "webm":
        export_kwargs["codec"] = "libopus"

    audio_chunk.export(output_path, **export_kwargs)
