"""STT 모듈 단위 테스트입니다."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def import_transcribe_with_fakes():
    """외부 의존성이 없을 때 fake 모듈로 transcribe.py를 import합니다."""
    fake_dotenv = types.SimpleNamespace(load_dotenv=lambda: None)
    fake_openai = types.SimpleNamespace(OpenAI=object)
    fake_pydub = types.SimpleNamespace(AudioSegment=object)

    with patch.dict(
        sys.modules,
        {"dotenv": fake_dotenv, "openai": fake_openai, "pydub": fake_pydub},
    ):
        sys.modules.pop("utils", None)
        sys.modules.pop("transcribe", None)
        return importlib.import_module("transcribe")


transcribe = import_transcribe_with_fakes()
from backend.services.stt import providers as stt_providers
from backend.services.stt import transformers_whisper


class TranscribeTests(unittest.TestCase):
    """OpenAI API를 호출하지 않고 STT 흐름을 테스트합니다."""

    def setUp(self) -> None:
        """테스트 간 local Whisper model cache가 섞이지 않게 초기화합니다."""
        stt_providers.LocalWhisperProvider._model_cache.clear()
        transcribe.get_stt_provider.__globals__["LocalWhisperProvider"]._model_cache.clear()
        transformers_whisper.reset_resident_pipeline_for_tests()
        sys.modules["transcribe"] = transcribe
        sys.modules.pop("faster_whisper", None)

    def test_normalize_audio_files_accepts_single_path_or_list(self) -> None:
        """단일 Path와 Path 리스트를 모두 리스트 형태로 정규화합니다."""
        audio_file = Path("meeting.wav")

        self.assertEqual(transcribe.normalize_audio_files(audio_file), [audio_file])
        self.assertEqual(transcribe.normalize_audio_files([audio_file]), [audio_file])

    def test_extract_transcript_text_supports_common_response_shapes(self) -> None:
        """문자열, 객체, dict 응답에서 transcript text를 추출합니다."""
        self.assertEqual(transcribe.extract_transcript_text("hello"), "hello")
        self.assertEqual(transcribe.extract_transcript_text(types.SimpleNamespace(text="object text")), "object text")
        self.assertEqual(transcribe.extract_transcript_text({"text": "dict text"}), "dict text")

    def test_get_transcription_model_uses_env_override(self) -> None:
        """환경 변수로 STT 모델명을 덮어쓸 수 있습니다."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(transcribe.get_transcription_model(), "gpt-4o-transcribe")
        with patch.dict(os.environ, {"OPENAI_TRANSCRIPTION_MODEL": "custom-stt"}):
            self.assertEqual(transcribe.get_transcription_model(), "custom-stt")

    def test_transcribe_audio_uses_openai_provider_by_default(self) -> None:
        """기본 STT provider는 기존 OpenAI workflow를 그대로 호출합니다."""
        audio_file = Path("meeting.wav")

        with patch.dict(os.environ, {}, clear=True), patch.object(
            transcribe,
            "_transcribe_audio_openai",
            return_value="plain text",
        ) as openai_mock:
            transcript = transcribe.transcribe_audio(audio_file)

        self.assertEqual(transcript, "plain text")
        openai_mock.assert_called_once_with(audio_file, progress_callback=None)

    def test_transcribe_audio_provider_override_takes_precedence_over_env(self) -> None:
        """요청별 STT provider 지정은 환경 변수보다 우선합니다."""
        audio_file = Path("meeting.wav")

        with patch.dict(os.environ, {"STT_PROVIDER": "local_gpu_whisper"}, clear=True), patch.object(
            transcribe,
            "_transcribe_audio_openai",
            return_value="cloud transcript",
        ) as openai_mock:
            transcript = transcribe.transcribe_audio(audio_file, stt_provider="openai")

        self.assertEqual(transcript, "cloud transcript")
        openai_mock.assert_called_once_with(audio_file, progress_callback=None)

    def test_transcribe_audio_local_whisper_uses_mocked_faster_whisper(self) -> None:
        """local_whisper provider는 faster-whisper 모델을 지연 로드해 plain transcript를 반환합니다."""
        created_models: list[tuple[str, str, str]] = []
        transcribed_paths: list[tuple[str, str]] = []

        class FakeWhisperModel:
            def __init__(self, model_name: str, device: str, compute_type: str) -> None:
                created_models.append((model_name, device, compute_type))

            def transcribe(self, audio_path: str, language: str):
                transcribed_paths.append((audio_path, language))
                return [types.SimpleNamespace(text=" 첫 번째 문장 "), types.SimpleNamespace(text="두 번째 문장")], object()

        stt_providers.LocalWhisperProvider._model_cache.clear()
        fake_faster_whisper = types.SimpleNamespace(WhisperModel=FakeWhisperModel)
        env = {
            "STT_PROVIDER": "local_whisper",
            "LOCAL_WHISPER_MODEL": "tiny",
            "LOCAL_WHISPER_DEVICE": "cpu",
            "LOCAL_WHISPER_COMPUTE_TYPE": "int8",
            "LOCAL_WHISPER_LANGUAGE": "ko",
        }

        with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, {"faster_whisper": fake_faster_whisper}):
            transcript = transcribe.transcribe_audio(Path("meeting.wav"))

        self.assertEqual(transcript, "첫 번째 문장 두 번째 문장")
        self.assertEqual(created_models, [("tiny", "cpu", "int8")])
        self.assertEqual(transcribed_paths, [("meeting.wav", "ko")])

    def test_transcribe_audio_local_whisper_reuses_cached_model(self) -> None:
        """local_whisper provider는 같은 설정의 모델을 요청마다 다시 로드하지 않습니다."""
        model_load_count = 0

        class FakeWhisperModel:
            def __init__(self, model_name: str, device: str, compute_type: str) -> None:
                nonlocal model_load_count
                model_load_count += 1

            def transcribe(self, audio_path: str, language: str):
                return [types.SimpleNamespace(text=Path(audio_path).stem)], object()

        stt_providers.LocalWhisperProvider._model_cache.clear()
        fake_faster_whisper = types.SimpleNamespace(WhisperModel=FakeWhisperModel)
        env = {"STT_PROVIDER": "local_whisper", "LOCAL_WHISPER_MODEL": "tiny"}

        with patch.dict(os.environ, env, clear=True), patch.dict(sys.modules, {"faster_whisper": fake_faster_whisper}):
            self.assertEqual(transcribe.transcribe_audio(Path("one.wav")), "one")
            self.assertEqual(transcribe.transcribe_audio(Path("two.wav")), "two")

        self.assertEqual(model_load_count, 1)

    def test_transcribe_audio_local_whisper_missing_dependency_fails_cleanly(self) -> None:
        """faster-whisper가 없으면 설치 방법을 포함한 명확한 오류를 냅니다."""
        stt_providers.LocalWhisperProvider._model_cache.clear()

        with patch.dict(os.environ, {"STT_PROVIDER": "local_whisper"}, clear=True), patch.dict(
            sys.modules,
            {"faster_whisper": None},
        ):
            with self.assertRaisesRegex(RuntimeError, "requires faster-whisper"):
                transcribe.transcribe_audio(Path("meeting.wav"))

    def test_transcribe_audio_local_gpu_whisper_uses_mocked_transformers_pipeline(self) -> None:
        """local_gpu_whisper provider는 resident Transformers pipeline을 plain chunk workflow에 연결합니다."""
        created_pipelines: list[dict[str, object]] = []
        inference_calls: list[tuple[str, bool, dict[str, str]]] = []

        class FakeCuda:
            def is_available(self) -> bool:
                return True

        class FakePipeline:
            def __call__(self, audio_path: str, return_timestamps: bool, generate_kwargs: dict[str, str]):
                inference_calls.append((audio_path, return_timestamps, generate_kwargs))
                return {"text": f" transcript-{Path(audio_path).stem} "}

        def fake_pipeline(**kwargs):
            created_pipelines.append(kwargs)
            return FakePipeline()

        fake_torch = types.ModuleType("torch")
        fake_torch.float16 = "float16"
        fake_torch.bfloat16 = "bfloat16"
        fake_torch.float32 = "float32"
        fake_torch.cuda = FakeCuda()
        fake_transformers = types.ModuleType("transformers")
        fake_transformers.pipeline = fake_pipeline

        audio_file = Path("meeting.wav")
        chunk_one = Path("chunk_001.wav")
        chunk_two = Path("chunk_002.wav")
        env = {
            "STT_PROVIDER": "local_gpu_whisper",
            "LOCAL_GPU_WHISPER_MODEL": "openai/whisper-large-v3-turbo",
            "LOCAL_GPU_DEVICE": "cuda:0",
            "LOCAL_GPU_TORCH_DTYPE": "float16",
            "LOCAL_GPU_MAX_CONCURRENCY": "4",
            "PLAIN_TRANSCRIPTION_CONCURRENCY": "2",
        }

        with patch.dict(os.environ, env, clear=True), patch.dict(
            sys.modules,
            {"torch": fake_torch, "transformers": fake_transformers},
        ), patch.object(transcribe, "prepare_audio_files", return_value=[chunk_one, chunk_two]), patch.object(
            transcribe, "normalize_audio_files", return_value=[audio_file]
        ), patch.object(transcribe, "log_transcription_run_diagnostics"), patch.object(
            transcribe, "cleanup_temp_files"
        ):
            transcript = transcribe.transcribe_audio(audio_file)

        self.assertEqual(transcript, "transcript-chunk_001\n\ntranscript-chunk_002")
        self.assertEqual(len(created_pipelines), 1)
        self.assertEqual(created_pipelines[0]["model"], "openai/whisper-large-v3-turbo")
        self.assertEqual(created_pipelines[0]["device"], "cuda:0")
        self.assertEqual(created_pipelines[0]["torch_dtype"], "float16")
        self.assertEqual(
            sorted(inference_calls),
            [
                ("chunk_001.wav", True, {"language": "ko", "task": "transcribe"}),
                ("chunk_002.wav", True, {"language": "ko", "task": "transcribe"}),
            ],
        )

    def test_transcribe_audio_local_gpu_whisper_reuses_resident_pipeline(self) -> None:
        """local_gpu_whisper provider는 같은 설정에서 pipeline을 요청마다 다시 만들지 않습니다."""
        pipeline_load_count = 0

        class FakeCuda:
            def is_available(self) -> bool:
                return True

        class FakePipeline:
            def __call__(self, audio_path: str, return_timestamps: bool, generate_kwargs: dict[str, str]):
                return {"text": Path(audio_path).stem}

        def fake_pipeline(**kwargs):
            nonlocal pipeline_load_count
            pipeline_load_count += 1
            return FakePipeline()

        fake_torch = types.ModuleType("torch")
        fake_torch.float16 = "float16"
        fake_torch.bfloat16 = "bfloat16"
        fake_torch.float32 = "float32"
        fake_torch.cuda = FakeCuda()
        fake_transformers = types.ModuleType("transformers")
        fake_transformers.pipeline = fake_pipeline
        env = {"STT_PROVIDER": "local_gpu_whisper", "PLAIN_TRANSCRIPTION_CONCURRENCY": "1"}

        with patch.dict(os.environ, env, clear=True), patch.dict(
            sys.modules,
            {"torch": fake_torch, "transformers": fake_transformers},
        ), patch.object(transcribe, "prepare_audio_files", side_effect=lambda audio_file, **kwargs: [audio_file]), patch.object(
            transcribe, "normalize_audio_files", side_effect=lambda audio_file: [audio_file]
        ), patch.object(transcribe, "log_transcription_run_diagnostics"), patch.object(
            transcribe, "cleanup_temp_files"
        ):
            self.assertEqual(transcribe.transcribe_audio(Path("one.wav")), "one")
            self.assertEqual(transcribe.transcribe_audio(Path("two.wav")), "two")

        self.assertEqual(pipeline_load_count, 1)

    def test_local_gpu_whisper_config_defaults_to_turbo_and_concurrency_three(self) -> None:
        """local_gpu_whisper 기본 설정은 운영 후보 baseline을 사용합니다."""
        with patch.dict(os.environ, {}, clear=True):
            config = transformers_whisper.get_config()

        self.assertEqual(config.model_name, "openai/whisper-large-v3-turbo")
        self.assertEqual(config.max_concurrency, 3)
        self.assertEqual(config.device, "cuda:0")
        self.assertEqual(config.torch_dtype, "float16")

    def test_local_gpu_whisper_initial_prompt_uses_only_organization_terms(self) -> None:
        """local_gpu_whisper prompt는 canonical organization_terms만 사용합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            vocabulary_file = Path(temp_dir) / "stt_vocabulary.yaml"
            vocabulary_file.write_text(
                "\n".join(
                    [
                        "organization_terms:",
                        "  - BigxData",
                        "  - Agent Works",
                        "  - bigxdata",
                        "aliases:",
                        "  - 비식데이터",
                        "descriptions:",
                        "  - BigxData is an internal company term.",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "STT_VOCABULARY_PATH": str(vocabulary_file),
                    "ENABLE_STT_VOCABULARY_HINTS": "true",
                    "LOCAL_GPU_ENABLE_STT_PROMPT": "true",
                },
            ):
                prompt = transformers_whisper.get_local_gpu_whisper_initial_prompt()

        self.assertEqual(prompt, "BigxData, Agent Works")

    def test_local_gpu_whisper_initial_prompt_is_disabled_by_default(self) -> None:
        """local_gpu_whisper STT prompt는 명시적으로 켜지 않으면 비활성화됩니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            vocabulary_file = Path(temp_dir) / "stt_vocabulary.yaml"
            vocabulary_file.write_text("organization_terms:\n  - BigxData\n", encoding="utf-8")

            with patch.dict(os.environ, {"STT_VOCABULARY_PATH": str(vocabulary_file)}, clear=True):
                prompt = transformers_whisper.get_local_gpu_whisper_initial_prompt()

        self.assertEqual(prompt, "")

    def test_local_gpu_whisper_initial_prompt_missing_file_degrades_gracefully(self) -> None:
        """vocabulary 파일이 없어도 local_gpu_whisper prompt는 빈 값으로 안전하게 비활성화됩니다."""
        with patch.dict(
            os.environ,
            {
                "STT_VOCABULARY_PATH": "/tmp/missing-local-gpu-stt-vocabulary.yaml",
                "ENABLE_STT_VOCABULARY_HINTS": "true",
                "LOCAL_GPU_ENABLE_STT_PROMPT": "true",
            },
        ):
            prompt = transformers_whisper.get_local_gpu_whisper_initial_prompt()

        self.assertEqual(prompt, "")

    def test_local_gpu_whisper_passes_vocabulary_prompt_ids_to_pipeline(self) -> None:
        """pipeline tokenizer가 numpy prompt ids를 반환해도 torch Tensor로 변환해 전달합니다."""
        inference_generate_kwargs: list[dict[str, object]] = []
        tokenizer_prompts: list[str] = []

        class FakeCuda:
            def is_available(self) -> bool:
                return True

        class FakeTensor:
            def __init__(self, value: object, dtype: object):
                self.value = value
                self.dtype = dtype
                self.device = None

            def to(self, device: object | None = None, dtype: object | None = None):
                self.device = device
                self.dtype = dtype
                return self

        class FakeTokenizer:
            def get_prompt_ids(self, prompt: str) -> np.ndarray:
                tokenizer_prompts.append(prompt)
                return np.array([101, 202], dtype=np.int64)

        class FakePipeline:
            device = "cuda:0"
            tokenizer = FakeTokenizer()

            def __call__(self, audio_path: str, return_timestamps: bool, generate_kwargs: dict[str, object]):
                inference_generate_kwargs.append(generate_kwargs)
                return {"text": "prompted transcript"}

        fake_torch = types.ModuleType("torch")
        fake_torch.float16 = "float16"
        fake_torch.bfloat16 = "bfloat16"
        fake_torch.float32 = "float32"
        fake_torch.long = "long"
        fake_torch.tensor = lambda value, dtype: FakeTensor(value, dtype)
        fake_torch.cuda = FakeCuda()
        fake_transformers = types.ModuleType("transformers")
        fake_transformers.pipeline = lambda **_kwargs: FakePipeline()
        config = transformers_whisper.LocalGpuWhisperConfig(
            model_name="openai/whisper-large-v3-turbo",
            device="cuda:0",
            torch_dtype="float16",
            max_concurrency=1,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            vocabulary_file = Path(temp_dir) / "stt_vocabulary.yaml"
            vocabulary_file.write_text(
                "\n".join(
                    [
                        "organization_terms:",
                        "  - BigxData",
                        "  - Tableau",
                        "aliases:",
                        "  - 태블로",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "STT_VOCABULARY_PATH": str(vocabulary_file),
                    "ENABLE_STT_VOCABULARY_HINTS": "true",
                    "LOCAL_GPU_ENABLE_STT_PROMPT": "true",
                },
            ), patch.dict(sys.modules, {"torch": fake_torch, "transformers": fake_transformers}):
                transcript = transformers_whisper.transcribe_file(Path("meeting.wav"), config=config)

        self.assertEqual(transcript, "prompted transcript")
        self.assertEqual(tokenizer_prompts, ["BigxData, Tableau"])
        self.assertEqual(len(inference_generate_kwargs), 1)
        prompt_ids = inference_generate_kwargs[0]["prompt_ids"]
        self.assertIsInstance(prompt_ids, FakeTensor)
        self.assertEqual(prompt_ids.dtype, "long")
        self.assertEqual(prompt_ids.device, "cuda:0")
        self.assertEqual(prompt_ids.value.tolist(), [101, 202])
        self.assertEqual(inference_generate_kwargs[0]["language"], "ko")
        self.assertEqual(inference_generate_kwargs[0]["task"], "transcribe")

    def test_local_gpu_whisper_prompt_ids_uses_configured_device_when_pipeline_device_is_absent(self) -> None:
        """pipeline device 속성이 없어도 설정된 LOCAL_GPU_DEVICE 기준으로 prompt_ids를 이동합니다."""
        class FakeTensor:
            def __init__(self, value: object, dtype: object):
                self.value = value
                self.dtype = dtype
                self.device = None

            def to(self, device: object | None = None, dtype: object | None = None):
                self.device = device
                self.dtype = dtype
                return self

        class FakeTokenizer:
            def get_prompt_ids(self, prompt: str) -> list[int]:
                return [101, 202]

        class FakePipeline:
            tokenizer = FakeTokenizer()

        fake_torch = types.ModuleType("torch")
        fake_torch.long = "long"
        fake_torch.tensor = lambda value, dtype: FakeTensor(value, dtype)
        config = transformers_whisper.LocalGpuWhisperConfig(
            model_name="openai/whisper-large-v3-turbo",
            device="cuda:0",
            torch_dtype="float16",
            max_concurrency=1,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            vocabulary_file = Path(temp_dir) / "stt_vocabulary.yaml"
            vocabulary_file.write_text("organization_terms:\n  - BigxData\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "STT_VOCABULARY_PATH": str(vocabulary_file),
                    "ENABLE_STT_VOCABULARY_HINTS": "true",
                    "LOCAL_GPU_ENABLE_STT_PROMPT": "true",
                },
            ), patch.dict(sys.modules, {"torch": fake_torch}):
                prompt_ids = transformers_whisper.build_whisper_prompt_ids(FakePipeline(), config)

        self.assertIsInstance(prompt_ids, FakeTensor)
        self.assertEqual(prompt_ids.device, "cuda:0")
        self.assertEqual(prompt_ids.dtype, "long")

    def test_local_gpu_whisper_prompt_ids_conversion_failure_degrades_to_no_prompt(self) -> None:
        """prompt_ids 변환이 실패해도 전사는 prompt 없이 계속됩니다."""
        inference_generate_kwargs: list[dict[str, object]] = []

        class FakeCuda:
            def is_available(self) -> bool:
                return True

        class FakeTokenizer:
            def get_prompt_ids(self, prompt: str) -> np.ndarray:
                return np.array([101, 202], dtype=np.int64)

        class FakePipeline:
            tokenizer = FakeTokenizer()

            def __call__(self, audio_path: str, return_timestamps: bool, generate_kwargs: dict[str, object]):
                inference_generate_kwargs.append(generate_kwargs)
                return {"text": "unprompted transcript"}

        fake_torch = types.ModuleType("torch")
        fake_torch.float16 = "float16"
        fake_torch.bfloat16 = "bfloat16"
        fake_torch.float32 = "float32"
        fake_torch.long = "long"
        fake_torch.tensor = Mock(side_effect=TypeError("bad prompt ids"))
        fake_torch.cuda = FakeCuda()
        fake_transformers = types.ModuleType("transformers")
        fake_transformers.pipeline = lambda **_kwargs: FakePipeline()
        config = transformers_whisper.LocalGpuWhisperConfig(
            model_name="openai/whisper-large-v3-turbo",
            device="cuda:0",
            torch_dtype="float16",
            max_concurrency=1,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            vocabulary_file = Path(temp_dir) / "stt_vocabulary.yaml"
            vocabulary_file.write_text("organization_terms:\n  - BigxData\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "STT_VOCABULARY_PATH": str(vocabulary_file),
                    "ENABLE_STT_VOCABULARY_HINTS": "true",
                    "LOCAL_GPU_ENABLE_STT_PROMPT": "true",
                },
            ), patch.dict(sys.modules, {"torch": fake_torch, "transformers": fake_transformers}):
                transcript = transformers_whisper.transcribe_file(Path("meeting.wav"), config=config)

        self.assertEqual(transcript, "unprompted transcript")
        self.assertEqual(inference_generate_kwargs, [{"language": "ko", "task": "transcribe"}])

    def test_local_gpu_whisper_cleanup_reduces_repeated_korean_character_artifacts(self) -> None:
        """local_gpu_whisper cleanup은 길게 반복된 한글 음절 artifact만 줄입니다."""
        transcript = "오늘 논의는 오오오오오오 여기서 시작합니다."

        cleaned = transformers_whisper.cleanup_repetition_artifacts(transcript)

        self.assertEqual(cleaned, "오늘 논의는 오 여기서 시작합니다.")

    def test_local_gpu_whisper_cleanup_reduces_repeated_short_acronym_artifacts(self) -> None:
        """local_gpu_whisper cleanup은 반복 붕괴된 짧은 acronym 나열을 줄입니다."""
        transcript = "이번 분기 KPI, KPI, KPI, KPI 기준을 다시 봅니다. . . . . 다음 안건입니다."

        cleaned = transformers_whisper.cleanup_repetition_artifacts(transcript)

        self.assertEqual(cleaned, "이번 분기 KPI 기준을 다시 봅니다. 다음 안건입니다.")

    def test_local_gpu_whisper_cleanup_preserves_normal_korean_conversation_repetition(self) -> None:
        """local_gpu_whisper cleanup은 정상적인 짧은 대화 반복을 보존합니다."""
        transcript = "네, 네. 그 부분은 맞습니다. 네, 그러면 다음으로 넘어가겠습니다."

        cleaned = transformers_whisper.cleanup_repetition_artifacts(transcript)

        self.assertEqual(cleaned, transcript)

    def test_local_gpu_whisper_cleanup_preserves_normal_domain_terms(self) -> None:
        """local_gpu_whisper cleanup은 정상적으로 등장한 도메인 용어를 바꾸지 않습니다."""
        transcript = "KPI 기준으로 LLM과 SLM을 비교하고 Graph RAG 적용 범위를 논의했습니다."

        cleaned = transformers_whisper.cleanup_repetition_artifacts(transcript)

        self.assertEqual(cleaned, transcript)

    def test_local_gpu_whisper_converts_m4a_to_wav_before_pipeline(self) -> None:
        """Transformers pipeline에 m4a를 직접 넘기지 않고 임시 WAV를 전달합니다."""
        inference_calls: list[str] = []

        class FakeCuda:
            def is_available(self) -> bool:
                return True

        class FakePipeline:
            def __call__(self, audio_path: str, return_timestamps: bool, generate_kwargs: dict[str, str]):
                inference_calls.append(audio_path)
                return {"text": " converted transcript "}

        fake_torch = types.ModuleType("torch")
        fake_torch.float16 = "float16"
        fake_torch.bfloat16 = "bfloat16"
        fake_torch.float32 = "float32"
        fake_torch.cuda = FakeCuda()
        fake_transformers = types.ModuleType("transformers")
        fake_transformers.pipeline = lambda **_kwargs: FakePipeline()
        config = transformers_whisper.LocalGpuWhisperConfig(
            model_name="openai/whisper-large-v3-turbo",
            device="cuda:0",
            torch_dtype="float16",
            max_concurrency=1,
        )

        with patch.dict(sys.modules, {"torch": fake_torch, "transformers": fake_transformers}), patch.object(
            transformers_whisper.subprocess,
            "run",
        ) as run_mock:
            transcript = transformers_whisper.transcribe_file(Path("meeting.m4a"), config=config)

        self.assertEqual(transcript, "converted transcript")
        run_mock.assert_called_once()
        ffmpeg_command = run_mock.call_args.args[0]
        self.assertEqual(ffmpeg_command[:4], ["ffmpeg", "-y", "-i", "meeting.m4a"])
        self.assertIn("-ac", ffmpeg_command)
        self.assertIn("1", ffmpeg_command)
        self.assertIn("-ar", ffmpeg_command)
        self.assertIn("16000", ffmpeg_command)
        self.assertEqual(len(inference_calls), 1)
        self.assertTrue(inference_calls[0].endswith(".wav"))
        self.assertNotEqual(inference_calls[0], "meeting.m4a")
        self.assertFalse(Path(inference_calls[0]).exists())

    def test_local_gpu_whisper_uses_wav_input_without_conversion(self) -> None:
        """이미 WAV인 chunk는 기존 경로를 그대로 pipeline에 넘깁니다."""
        inference_calls: list[str] = []

        class FakeCuda:
            def is_available(self) -> bool:
                return True

        class FakePipeline:
            def __call__(self, audio_path: str, return_timestamps: bool, generate_kwargs: dict[str, str]):
                inference_calls.append(audio_path)
                return {"text": "wav transcript"}

        fake_torch = types.ModuleType("torch")
        fake_torch.float16 = "float16"
        fake_torch.bfloat16 = "bfloat16"
        fake_torch.float32 = "float32"
        fake_torch.cuda = FakeCuda()
        fake_transformers = types.ModuleType("transformers")
        fake_transformers.pipeline = lambda **_kwargs: FakePipeline()
        config = transformers_whisper.LocalGpuWhisperConfig(
            model_name="openai/whisper-large-v3-turbo",
            device="cuda:0",
            torch_dtype="float16",
            max_concurrency=1,
        )

        with patch.dict(sys.modules, {"torch": fake_torch, "transformers": fake_transformers}), patch.object(
            transformers_whisper.subprocess,
            "run",
        ) as run_mock:
            transcript = transformers_whisper.transcribe_file(Path("meeting.wav"), config=config)

        self.assertEqual(transcript, "wav transcript")
        run_mock.assert_not_called()
        self.assertEqual(inference_calls, ["meeting.wav"])

    def test_local_gpu_whisper_ffmpeg_failure_is_actionable(self) -> None:
        """ffmpeg 변환 실패는 원인 파악이 가능한 RuntimeError로 감쌉니다."""
        with patch.object(
            transformers_whisper.subprocess,
            "run",
            side_effect=subprocess.CalledProcessError(1, ["ffmpeg"], stderr="invalid input"),
        ):
            with self.assertRaisesRegex(RuntimeError, "ffmpeg failed to convert audio.*meeting.m4a.*invalid input"):
                transformers_whisper.prepare_audio_for_transformers(Path("meeting.m4a"))

    def test_transcribe_audio_local_gpu_whisper_missing_dependency_fails_cleanly(self) -> None:
        """torch/transformers가 없으면 runtime 준비 방법을 포함한 명확한 오류를 냅니다."""
        with patch.dict(os.environ, {"STT_PROVIDER": "local_gpu_whisper"}, clear=True), patch.dict(
            sys.modules,
            {"torch": None, "transformers": None},
        ), patch.object(transcribe, "prepare_audio_files", return_value=[Path("meeting.wav")]), patch.object(
            transcribe, "normalize_audio_files", return_value=[Path("meeting.wav")]
        ), patch.object(transcribe, "log_transcription_run_diagnostics"), patch.object(
            transcribe, "cleanup_temp_files"
        ):
            with self.assertRaisesRegex(RuntimeError, "requires torch and transformers"):
                transcribe.transcribe_audio(Path("meeting.wav"))

    def test_transcribe_audio_rejects_unknown_stt_provider(self) -> None:
        """지원하지 않는 STT_PROVIDER 값은 명확히 거절합니다."""
        with patch.dict(os.environ, {"STT_PROVIDER": "unknown"}):
            with self.assertRaisesRegex(ValueError, "Unsupported STT_PROVIDER"):
                transcribe.transcribe_audio(Path("meeting.wav"))

    def test_get_transcription_language_defaults_to_korean_and_allows_env_override(self) -> None:
        """STT 언어 힌트는 기본 한국어이고 환경 변수로 덮어쓸 수 있습니다."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(transcribe.get_transcription_language(), "ko")
        with patch.dict(os.environ, {"OPENAI_TRANSCRIPTION_LANGUAGE": "en"}):
            self.assertEqual(transcribe.get_transcription_language(), "en")

    def test_load_stt_vocabulary_terms_reads_yaml_and_deduplicates(self) -> None:
        """STT vocabulary YAML은 읽기 쉬운 순서로 중복을 제거해 로드합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            vocabulary_file = Path(temp_dir) / "stt_vocabulary.yaml"
            vocabulary_file.write_text(
                "\n".join(
                    [
                        "organization_terms:",
                        "  - BigxData",
                        "  - Tableau",
                        "  - bigxdata",
                        "  - Semantic Layer",
                    ]
                ),
                encoding="utf-8",
            )

            terms = transcribe.load_stt_vocabulary_terms(vocabulary_file)

        self.assertEqual(terms, ["BigxData", "Tableau", "Semantic Layer"])

    def test_load_stt_vocabulary_terms_tolerates_missing_file(self) -> None:
        """vocabulary 파일이 없어도 전사 흐름은 실패하지 않습니다."""
        self.assertEqual(transcribe.load_stt_vocabulary_terms(Path("/tmp/missing-stt-vocabulary.yaml")), [])

    def test_load_stt_vocabulary_terms_ignores_malformed_entries(self) -> None:
        """문자열 term이 아닌 항목은 조용히 건너뜁니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            vocabulary_file = Path(temp_dir) / "stt_vocabulary.yaml"
            vocabulary_file.write_text(
                "\n".join(
                    [
                        "organization_terms:",
                        "  - BigxData",
                        "  - 12345",
                        "  - []",
                        "  - name: Broken",
                        "  - Agent Works # inline comment",
                    ]
                ),
                encoding="utf-8",
            )

            terms = transcribe.load_stt_vocabulary_terms(vocabulary_file)

        self.assertEqual(terms, ["BigxData", "Agent Works"])

    def test_build_stt_vocabulary_prompt_is_compact(self) -> None:
        """STT vocabulary prompt는 설명 없이 제한 길이 안에서 구성됩니다."""
        terms = [f"Term {index}" for index in range(200)]

        prompt = transcribe.build_stt_vocabulary_prompt(terms)

        self.assertLessEqual(len(prompt), transcribe.MAX_STT_VOCABULARY_PROMPT_CHARS)
        self.assertTrue(prompt.startswith("Known organization, product, and technical terms that may appear: "))
        self.assertIn("Term 0", prompt)

    def test_get_plain_transcription_concurrency_defaults_and_clamps_env(self) -> None:
        """plain STT 동시성은 기본값과 안전한 상한/하한을 적용합니다."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(transcribe.get_plain_transcription_concurrency(), 3)
        with patch.dict(os.environ, {"PLAIN_TRANSCRIPTION_CONCURRENCY": "4"}):
            self.assertEqual(transcribe.get_plain_transcription_concurrency(), 4)
        with patch.dict(os.environ, {"PLAIN_TRANSCRIPTION_CONCURRENCY": "0"}):
            self.assertEqual(transcribe.get_plain_transcription_concurrency(), 1)
        with patch.dict(os.environ, {"PLAIN_TRANSCRIPTION_CONCURRENCY": "20"}):
            self.assertEqual(transcribe.get_plain_transcription_concurrency(), 5)

    def test_get_trace_prefix_includes_human_readable_timestamp(self) -> None:
        """trace prefix는 사람이 읽기 쉬운 시각과 고정 marker를 포함합니다."""
        with patch.object(transcribe, "get_trace_timestamp", return_value="12:34:56"):
            self.assertEqual(transcribe.get_trace_prefix(), "[12:34:56][TRANSCRIBE_TRACE]")

    def test_build_timing_summary_computes_chunk_latency_metadata(self) -> None:
        """timing summary helper는 chunk 평균/최대/총 elapsed metadata를 만듭니다."""
        stats = transcribe.TranscriptionTimingStats(
            mode="plain",
            model_name="mock-stt",
            chunk_config=transcribe.AudioChunkConfig(duration_seconds=300, overlap_seconds=0),
        )
        stats.total_chunks = 3
        stats.preparation_seconds = 2.0
        stats.merge_seconds = 0.5
        stats.retry_count = 1
        stats.chunk_elapsed_seconds = [10.0, 20.0, 30.0]

        summary = transcribe.build_timing_summary(stats)

        self.assertEqual(summary["mode"], "plain")
        self.assertEqual(summary["model"], "mock-stt")
        self.assertEqual(summary["total_chunks"], 3)
        self.assertEqual(summary["completed_chunks"], 3)
        self.assertEqual(summary["avg_chunk_seconds"], 20.0)
        self.assertEqual(summary["slowest_chunk_seconds"], 30.0)
        self.assertEqual(summary["retry_count"], 1)
        self.assertEqual(summary["chunk_duration_seconds"], 300)

    def test_get_audio_chunk_config_uses_plain_safe_duration_default(self) -> None:
        """plain mode도 실제 긴 녹음에서는 시간 기준 청크 검증을 사용합니다."""
        with patch.dict(os.environ, {}, clear=True):
            chunk_config = transcribe.get_audio_chunk_config()

        self.assertEqual(chunk_config.duration_seconds, 300)
        self.assertEqual(chunk_config.overlap_seconds, 0)

    def test_transcribe_audio_joins_chunks_and_cleans_temp_files(self) -> None:
        """청크 transcript를 합치고 새로 생성된 임시 청크를 정리합니다."""
        original_file = Path("meeting.wav")
        temp_chunk = Path("/private/tmp/meeting_chunk_001.wav")

        with patch.dict(os.environ, {"PLAIN_TRANSCRIPTION_CONCURRENCY": "1"}), patch.object(
            transcribe, "prepare_audio_files", return_value=[original_file, temp_chunk]
        ), patch.object(
            transcribe, "transcribe_chunk", side_effect=[" first ", "second"]
        ), patch.object(transcribe, "log_transcription_run_diagnostics"), patch.object(
            transcribe, "cleanup_temp_files"
        ) as cleanup_mock:
            transcript = transcribe.transcribe_audio(original_file)

        self.assertEqual(transcript, "first\n\nsecond")
        cleanup_mock.assert_called_once_with([temp_chunk])

    def test_transcribe_audio_plain_mode_keeps_string_return(self) -> None:
        """기본 plain mode와 명시적 plain mode는 기존 string 반환을 유지합니다."""
        audio_file = Path("meeting.wav")

        with patch.dict(os.environ, {"PLAIN_TRANSCRIPTION_CONCURRENCY": "1"}), patch.object(
            transcribe, "prepare_audio_files", return_value=[audio_file]
        ), patch.object(
            transcribe, "normalize_audio_files", return_value=[audio_file]
        ), patch.object(transcribe, "log_transcription_run_diagnostics"), patch.object(
            transcribe, "transcribe_chunk", return_value="plain text"
        ), patch.object(transcribe, "cleanup_temp_files"):
            self.assertEqual(transcribe.transcribe_audio(audio_file), "plain text")

    def test_transcribe_audio_plain_passes_configured_concurrency(self) -> None:
        """plain workflow는 환경 변수로 설정한 동시성을 chunk helper에 전달합니다."""
        audio_file = Path("meeting.wav")
        captured: dict[str, int] = {}

        def transcribe_chunks_side_effect(**kwargs):
            captured["concurrency"] = kwargs["concurrency"]
            return ["plain text"]

        with patch.dict(os.environ, {"PLAIN_TRANSCRIPTION_CONCURRENCY": "4"}), patch.object(
            transcribe, "prepare_audio_files", return_value=[audio_file]
        ), patch.object(transcribe, "normalize_audio_files", return_value=[audio_file]), patch.object(
            transcribe, "log_transcription_run_diagnostics"
        ), patch.object(
            transcribe, "transcribe_plain_chunks_concurrently", side_effect=transcribe_chunks_side_effect
        ), patch.object(
            transcribe, "cleanup_temp_files"
        ):
            transcript = transcribe.transcribe_audio(audio_file)

        self.assertEqual(transcript, "plain text")
        self.assertEqual(captured["concurrency"], 4)

    def test_plain_concurrency_one_preserves_sequential_like_call_order(self) -> None:
        """동시성 1에서는 plain chunk 호출 순서가 기존 순차 흐름과 같습니다."""
        call_order: list[str] = []
        chunks = [Path("chunk_001.wav"), Path("chunk_002.wav"), Path("chunk_003.wav")]
        stats = transcribe.TranscriptionTimingStats(
            mode="plain",
            model_name="mock-stt",
            chunk_config=transcribe.AudioChunkConfig(duration_seconds=300, overlap_seconds=0),
            concurrency=1,
        )

        def transcribe_chunk_side_effect(audio_file, **kwargs):
            call_order.append(audio_file.name)
            return audio_file.stem

        with patch.object(transcribe, "transcribe_chunk", side_effect=transcribe_chunk_side_effect):
            transcripts = transcribe.transcribe_plain_chunks_concurrently(
                files_to_transcribe=chunks,
                chunk_config=stats.chunk_config,
                source_files=[Path("meeting.wav")],
                timing_stats=stats,
                model_name="mock-stt",
                concurrency=1,
            )

        self.assertEqual(call_order, ["chunk_001.wav", "chunk_002.wav", "chunk_003.wav"])
        self.assertEqual(transcripts, ["chunk_001", "chunk_002", "chunk_003"])

    def test_plain_concurrency_reports_chunk_progress(self) -> None:
        """plain chunk workflow는 총 청크 수와 완료 청크 수를 callback으로 알립니다."""
        progress_events: list[tuple[int, int]] = []
        chunks = [Path("chunk_001.wav"), Path("chunk_002.wav")]
        stats = transcribe.TranscriptionTimingStats(
            mode="plain",
            model_name="mock-stt",
            chunk_config=transcribe.AudioChunkConfig(duration_seconds=300, overlap_seconds=0),
            concurrency=1,
        )

        with patch.object(transcribe, "transcribe_chunk", side_effect=lambda audio_file, **kwargs: audio_file.stem):
            transcripts = transcribe.transcribe_plain_chunks_concurrently(
                files_to_transcribe=chunks,
                chunk_config=stats.chunk_config,
                source_files=[Path("meeting.wav")],
                timing_stats=stats,
                model_name="mock-stt",
                concurrency=1,
                chunk_progress_callback=lambda completed, total: progress_events.append((completed, total)),
            )

        self.assertEqual(transcripts, ["chunk_001", "chunk_002"])
        self.assertEqual(progress_events, [(0, 2), (1, 2), (2, 2)])

    def test_plain_concurrency_preserves_original_chunk_order(self) -> None:
        """늦게 끝난 chunk가 있어도 최종 transcript 순서는 원본 chunk 순서를 따릅니다."""
        chunks = [Path("chunk_001.wav"), Path("chunk_002.wav"), Path("chunk_003.wav")]
        stats = transcribe.TranscriptionTimingStats(
            mode="plain",
            model_name="mock-stt",
            chunk_config=transcribe.AudioChunkConfig(duration_seconds=300, overlap_seconds=0),
            concurrency=3,
        )

        def transcribe_chunk_side_effect(audio_file, **kwargs):
            if audio_file.name == "chunk_001.wav":
                time.sleep(0.03)
            return audio_file.stem

        with patch.object(transcribe, "transcribe_chunk", side_effect=transcribe_chunk_side_effect):
            transcripts = transcribe.transcribe_plain_chunks_concurrently(
                files_to_transcribe=chunks,
                chunk_config=stats.chunk_config,
                source_files=[Path("meeting.wav")],
                timing_stats=stats,
                model_name="mock-stt",
                concurrency=3,
            )

        self.assertEqual(transcripts, ["chunk_001", "chunk_002", "chunk_003"])

    def test_plain_concurrency_failed_chunk_raises_clear_error(self) -> None:
        """plain 병렬 처리 중 chunk 실패는 index와 path를 포함해 실패합니다."""
        chunks = [Path("chunk_001.wav"), Path("chunk_002.wav")]
        stats = transcribe.TranscriptionTimingStats(
            mode="plain",
            model_name="mock-stt",
            chunk_config=transcribe.AudioChunkConfig(duration_seconds=300, overlap_seconds=0),
            concurrency=2,
        )

        def transcribe_chunk_side_effect(audio_file, **kwargs):
            if audio_file.name == "chunk_002.wav":
                raise RuntimeError("provider down")
            return audio_file.stem

        with patch.object(transcribe, "transcribe_chunk", side_effect=transcribe_chunk_side_effect):
            with self.assertRaisesRegex(RuntimeError, "Plain transcription chunk failed index=2 path=chunk_002.wav"):
                transcribe.transcribe_plain_chunks_concurrently(
                    files_to_transcribe=chunks,
                    chunk_config=stats.chunk_config,
                    source_files=[Path("meeting.wav")],
                    timing_stats=stats,
                    model_name="mock-stt",
                    concurrency=2,
                )

    def test_transcribe_audio_plain_snapshots_model_for_all_chunks(self) -> None:
        """plain workflow는 시작 시 resolved model을 모든 chunk에 동일하게 사용합니다."""
        used_models: list[str] = []

        def create_side_effect(**kwargs):
            used_models.append(kwargs["model"])
            os.environ["OPENAI_TRANSCRIPTION_MODEL"] = "drifted-stt"
            return types.SimpleNamespace(text=Path(kwargs["file"].name).stem)

        create_mock = Mock(side_effect=create_side_effect)
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = Path(temp_dir) / "meeting.wav"
            chunk_one = Path(temp_dir) / "chunk_001.wav"
            chunk_two = Path(temp_dir) / "chunk_002.wav"
            for path in (source_file, chunk_one, chunk_two):
                path.write_bytes(b"audio")

            diagnostic = transcribe.AudioChunkDiagnostic(path=chunk_one, duration_seconds=1.0, size_mb=0.001)
            with patch.dict(os.environ, {"OPENAI_TRANSCRIPTION_MODEL": "snapshot-stt"}), patch.object(
                transcribe, "prepare_audio_files", return_value=[chunk_one, chunk_two]
            ), patch.object(transcribe, "normalize_audio_files", return_value=[source_file]), patch.object(
                transcribe, "log_transcription_run_diagnostics"
            ), patch.object(
                transcribe, "validate_chunk_before_transcription", return_value=diagnostic
            ), patch.object(
                transcribe, "create_openai_client", return_value=fake_client
            ), patch.object(
                transcribe, "cleanup_temp_files"
            ):
                transcript = transcribe.transcribe_audio(source_file)

        self.assertEqual(transcript, "chunk_001\n\nchunk_002")
        self.assertEqual(used_models, ["snapshot-stt", "snapshot-stt"])

    def test_transcribe_audio_plain_can_switch_to_full_transcribe_model_for_ab_test(self) -> None:
        """plain workflow는 gpt-4o-transcribe override를 모든 chunk에 동일하게 적용합니다."""
        used_models: list[str] = []

        def create_side_effect(**kwargs):
            used_models.append(kwargs["model"])
            return types.SimpleNamespace(text=Path(kwargs["file"].name).stem)

        create_mock = Mock(side_effect=create_side_effect)
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = Path(temp_dir) / "meeting.wav"
            chunk_one = Path(temp_dir) / "chunk_001.wav"
            chunk_two = Path(temp_dir) / "chunk_002.wav"
            for path in (source_file, chunk_one, chunk_two):
                path.write_bytes(b"audio")

            diagnostic = transcribe.AudioChunkDiagnostic(path=chunk_one, duration_seconds=1.0, size_mb=0.001)
            with patch.dict(os.environ, {"OPENAI_TRANSCRIPTION_MODEL": "gpt-4o-transcribe"}), patch.object(
                transcribe, "prepare_audio_files", return_value=[chunk_one, chunk_two]
            ), patch.object(transcribe, "normalize_audio_files", return_value=[source_file]), patch.object(
                transcribe, "log_transcription_run_diagnostics"
            ), patch.object(
                transcribe, "validate_chunk_before_transcription", return_value=diagnostic
            ), patch.object(
                transcribe, "create_openai_client", return_value=fake_client
            ), patch.object(
                transcribe, "cleanup_temp_files"
            ):
                transcript = transcribe.transcribe_audio(source_file)

        self.assertEqual(transcript, "chunk_001\n\nchunk_002")
        self.assertEqual(used_models, ["gpt-4o-transcribe", "gpt-4o-transcribe"])

    def test_prepare_audio_files_cleans_generated_chunks_on_failure(self) -> None:
        """여러 파일 처리 중 실패해도 이미 생성한 청크를 정리합니다."""
        first_file = Path("first.wav")
        second_file = Path("second.wav")
        generated_chunk = Path("/private/tmp/first_chunk_001.wav")

        with patch.object(transcribe, "ensure_audio_file"), patch.object(
            transcribe, "split_audio_if_needed", side_effect=[[generated_chunk], RuntimeError("boom")]
        ), patch.object(transcribe, "cleanup_temp_files") as cleanup_mock:
            with self.assertRaises(RuntimeError):
                transcribe.prepare_audio_files([first_file, second_file])

        cleanup_mock.assert_called_once_with([generated_chunk])

    def test_prepare_audio_files_plain_uses_plain_chunk_config(self) -> None:
        """plain mode 준비 단계는 기존 크기 기반 config로 분할 함수를 호출합니다."""
        audio_file = Path("meeting.wav")

        with patch.object(transcribe, "ensure_audio_file"), patch.object(
            transcribe, "split_audio_if_needed", return_value=[audio_file]
        ) as split_mock:
            prepared = transcribe.prepare_audio_files(audio_file)

        self.assertEqual(prepared, [audio_file])
        chunk_config = split_mock.call_args.kwargs["chunk_config"]
        self.assertEqual(chunk_config.duration_seconds, 300)
        self.assertEqual(chunk_config.overlap_seconds, 0)

    def test_build_audio_chunk_diagnostic_returns_duration_and_size(self) -> None:
        """청크 진단 helper는 duration과 파일 크기를 함께 반환합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"x" * 1024 * 1024)

            with patch.object(transcribe, "get_audio_duration_seconds", return_value=12.5):
                diagnostic = transcribe.build_audio_chunk_diagnostic(audio_file)

        self.assertEqual(diagnostic.path, audio_file)
        self.assertEqual(diagnostic.duration_seconds, 12.5)
        self.assertAlmostEqual(diagnostic.size_mb, 1.0)

    def test_validate_chunk_before_transcription_rejects_oversized_duration(self) -> None:
        """전사 직전 guard는 설정 길이를 초과한 의심 청크를 차단합니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")

            with patch.object(transcribe, "get_audio_duration_seconds", return_value=190.0):
                with self.assertRaisesRegex(RuntimeError, "audio chunk is too long"):
                    transcribe.validate_chunk_before_transcription(
                        audio_file,
                        transcribe.AudioChunkConfig(duration_seconds=150, overlap_seconds=0),
                        [audio_file],
                    )

    def test_transcribe_chunk_uses_chunk_verification(self) -> None:
        """plain chunk 호출도 OpenAI 호출 전 chunk 검증을 거칩니다."""
        create_mock = Mock(return_value=types.SimpleNamespace(text="hello"))
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")
            diagnostic = transcribe.AudioChunkDiagnostic(path=audio_file, duration_seconds=1.0, size_mb=0.001)

            with patch.object(transcribe, "ensure_audio_file"), patch.object(
                transcribe, "validate_chunk_before_transcription"
            ) as validate_mock, patch.object(transcribe, "create_openai_client", return_value=fake_client):
                validate_mock.return_value = diagnostic
                transcribe.transcribe_chunk(audio_file)

        validate_mock.assert_called_once()
        self.assertEqual(validate_mock.call_args.args[1].duration_seconds, 300)

    def test_openai_wrapper_receives_stt_vocabulary_prompt(self) -> None:
        """공통 OpenAI STT wrapper는 vocabulary prompt를 요청에 전달합니다."""
        create_mock = Mock(return_value=types.SimpleNamespace(text="hello"))
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            vocabulary_file = Path(temp_dir) / "stt_vocabulary.yaml"
            audio_file.write_bytes(b"audio")
            vocabulary_file.write_text("organization_terms:\n  - BigxData\n  - Semantic Layer\n", encoding="utf-8")

            with patch.object(transcribe, "ensure_audio_file"), patch.object(
                transcribe, "create_openai_client", return_value=fake_client
            ), patch.dict(os.environ, {"STT_VOCABULARY_PATH": str(vocabulary_file)}):
                transcribe.call_openai_transcription(
                    audio_file=audio_file,
                    chunk_config=transcribe.AudioChunkConfig(duration_seconds=300, overlap_seconds=0),
                    source_files=[audio_file],
                )

        self.assertIn("prompt", create_mock.call_args.kwargs)
        self.assertIn("BigxData", create_mock.call_args.kwargs["prompt"])
        self.assertIn("Semantic Layer", create_mock.call_args.kwargs["prompt"])

    def test_disabling_stt_vocabulary_hints_prevents_injection(self) -> None:
        """환경 변수로 STT vocabulary hint 주입을 끌 수 있습니다."""
        create_mock = Mock(return_value=types.SimpleNamespace(text="hello"))
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            vocabulary_file = Path(temp_dir) / "stt_vocabulary.yaml"
            audio_file.write_bytes(b"audio")
            vocabulary_file.write_text("organization_terms:\n  - BigxData\n", encoding="utf-8")

            with patch.object(transcribe, "ensure_audio_file"), patch.object(
                transcribe, "create_openai_client", return_value=fake_client
            ), patch.dict(
                os.environ,
                {
                    "ENABLE_STT_VOCABULARY_HINTS": "false",
                    "STT_VOCABULARY_PATH": str(vocabulary_file),
                },
            ):
                transcribe.call_openai_transcription(
                    audio_file=audio_file,
                    chunk_config=transcribe.AudioChunkConfig(duration_seconds=300, overlap_seconds=0),
                    source_files=[audio_file],
                )

        self.assertNotIn("prompt", create_mock.call_args.kwargs)

    def test_plain_transcribe_chunk_uses_stt_vocabulary_hint(self) -> None:
        """plain chunk path도 vocabulary hint를 포함합니다."""
        create_mock = Mock(return_value=types.SimpleNamespace(text="hello"))
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            vocabulary_file = Path(temp_dir) / "stt_vocabulary.yaml"
            audio_file.write_bytes(b"audio")
            vocabulary_file.write_text("organization_terms:\n  - Agent Works\n", encoding="utf-8")

            with patch.object(transcribe, "ensure_audio_file"), patch.object(
                transcribe, "create_openai_client", return_value=fake_client
            ), patch.dict(os.environ, {"STT_VOCABULARY_PATH": str(vocabulary_file)}):
                result = transcribe.transcribe_chunk(audio_file)

        self.assertEqual(result, "hello")
        self.assertIn("Agent Works", create_mock.call_args.kwargs["prompt"])

    def test_all_transcription_paths_use_shared_openai_wrapper(self) -> None:
        """plain 경로는 공통 OpenAI 호출 래퍼를 통과합니다."""
        audio_file = Path("meeting.wav")

        with patch.object(
            transcribe,
            "call_openai_transcription",
            return_value=types.SimpleNamespace(text="plain text"),
        ) as wrapper_mock:
            result = transcribe.transcribe_chunk(audio_file)

        self.assertEqual(result, "plain text")
        self.assertNotIn("mode", wrapper_mock.call_args.kwargs)

    def test_openai_wrapper_logs_diagnostics_before_send(self) -> None:
        """공통 OpenAI 래퍼는 전송 전에 chunk 검증과 진단을 먼저 실행합니다."""
        events: list[str] = []

        def validate_side_effect(*args, **kwargs):
            events.append("validate")
            return transcribe.AudioChunkDiagnostic(path=args[0], duration_seconds=1.0, size_mb=0.001)

        def create_side_effect(**kwargs):
            events.append("openai")
            return types.SimpleNamespace(text="hello")

        create_mock = Mock(side_effect=create_side_effect)
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")

            with patch.object(transcribe, "ensure_audio_file"), patch.object(
                transcribe, "validate_chunk_before_transcription", side_effect=validate_side_effect
            ), patch.object(transcribe, "create_openai_client", return_value=fake_client):
                transcribe.call_openai_transcription(
                    audio_file=audio_file,
                    chunk_config=transcribe.AudioChunkConfig(duration_seconds=300, overlap_seconds=0),
                    source_files=[audio_file],
                )

        self.assertEqual(events, ["validate", "openai"])

    def test_input_too_large_retry_depth_is_bounded(self) -> None:
        """input_too_large 재시도는 최대 깊이에서 명확히 중단됩니다."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")

            with self.assertRaisesRegex(RuntimeError, "still too large"):
                transcribe.split_chunk_for_input_too_large(
                    audio_file=audio_file,
                    chunk_config=transcribe.AudioChunkConfig(duration_seconds=60, overlap_seconds=0),
                    retry_depth=transcribe.INPUT_TOO_LARGE_MAX_RETRY_DEPTH,
                    original_error=RuntimeError("input_too_large"),
                )

    def test_transcribe_chunk_calls_openai_client_without_real_api(self) -> None:
        """fake OpenAI client로 단일 청크 STT 호출 파라미터를 확인합니다."""
        create_mock = Mock(return_value=types.SimpleNamespace(text="hello"))
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")

            with patch.object(transcribe, "ensure_audio_file"), patch.object(
                transcribe, "create_openai_client", return_value=fake_client
            ), patch.dict(os.environ, {"OPENAI_TRANSCRIPTION_MODEL": "mock-stt"}, clear=True):
                result = transcribe.transcribe_chunk(audio_file)

        self.assertEqual(result, "hello")
        self.assertEqual(create_mock.call_args.kwargs["model"], "mock-stt")
        self.assertEqual(create_mock.call_args.kwargs["language"], "ko")
        self.assertNotIn("chunking_strategy", create_mock.call_args.kwargs)

    def test_transcribe_chunk_uses_language_env_override(self) -> None:
        """plain STT 호출에도 언어 환경 변수 override를 전달합니다."""
        create_mock = Mock(return_value=types.SimpleNamespace(text="hello"))
        fake_client = types.SimpleNamespace(
            audio=types.SimpleNamespace(transcriptions=types.SimpleNamespace(create=create_mock))
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_file = Path(temp_dir) / "meeting.wav"
            audio_file.write_bytes(b"audio")

            with patch.object(transcribe, "ensure_audio_file"), patch.object(
                transcribe, "create_openai_client", return_value=fake_client
            ), patch.dict(os.environ, {"OPENAI_TRANSCRIPTION_LANGUAGE": "en"}):
                transcribe.transcribe_chunk(audio_file)

        self.assertEqual(create_mock.call_args.kwargs["language"], "en")


if __name__ == "__main__":
    unittest.main()
