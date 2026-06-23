"""회의 요약 파이프라인 단위 테스트입니다."""

from __future__ import annotations

import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import ANY, Mock, patch

from summarize_test_helpers import collect_schema_objects, empty_track_b_structure, schema_contains_key, summarize

class SummarizeProviderTests(unittest.TestCase):
    """기존 summarize.py 테스트를 도메인별로 분리한 테스트입니다."""

    def test_get_summarization_provider_defaults_to_openai(self) -> None:
        """요약 provider 기본값은 기존 OpenAI 경로입니다."""
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(summarize.get_summarization_provider(), "openai")

    def test_get_summarization_provider_accepts_claude(self) -> None:
        """환경 변수로 Claude 요약 provider를 선택할 수 있습니다."""
        with patch.dict(os.environ, {"SUMMARIZATION_PROVIDER": "claude"}, clear=True):
            self.assertEqual(summarize.get_summarization_provider(), "claude")

    def test_get_summarization_provider_rejects_unknown_provider(self) -> None:
        """지원하지 않는 요약 provider는 명확히 거절합니다."""
        with patch.dict(os.environ, {"SUMMARIZATION_PROVIDER": "unknown"}, clear=True):
            with self.assertRaisesRegex(ValueError, "Unsupported SUMMARIZATION_PROVIDER"):
                summarize.get_summarization_provider()

    def test_create_anthropic_client_requires_api_key(self) -> None:
        """Claude provider는 ANTHROPIC_API_KEY가 없으면 명확히 실패합니다."""
        claude_globals = summarize.create_anthropic_client.__globals__
        with patch.dict(os.environ, {}, clear=True), patch.dict(claude_globals, {"load_dotenv": Mock()}):
            with self.assertRaisesRegex(RuntimeError, "ANTHROPIC_API_KEY is missing"):
                summarize.create_anthropic_client()

    def test_get_structure_model_uses_env_override(self) -> None:
        """환경 변수로 구조 추출 모델명을 덮어쓸 수 있습니다."""
        with patch.dict(os.environ, {"OPENAI_STRUCTURE_MODEL": "custom-structure"}):
            self.assertEqual(summarize.get_structure_model(), "custom-structure")

    def test_get_summary_model_uses_env_override(self) -> None:
        """환경 변수로 회의록 생성 모델명을 덮어쓸 수 있습니다."""
        with patch.dict(os.environ, {"OPENAI_SUMMARY_MODEL": "custom-summary"}):
            self.assertEqual(summarize.get_summary_model(), "custom-summary")

    def test_get_claude_structure_model_uses_env_override(self) -> None:
        """환경 변수로 Claude 구조 추출 모델명을 덮어쓸 수 있습니다."""
        with patch.dict(os.environ, {"CLAUDE_STRUCTURE_MODEL": "custom-claude-structure"}):
            self.assertEqual(summarize.get_claude_structure_model(), "custom-claude-structure")

    def test_get_claude_summary_model_uses_env_override(self) -> None:
        """환경 변수로 Claude 회의록 생성 모델명을 덮어쓸 수 있습니다."""
        with patch.dict(os.environ, {"CLAUDE_SUMMARY_MODEL": "custom-claude-summary"}):
            self.assertEqual(summarize.get_claude_summary_model(), "custom-claude-summary")


if __name__ == "__main__":
    unittest.main()
