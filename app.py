"""Streamlit UI for the Meeting Summarizer internal tool."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from tempfile import mkdtemp
from typing import Any, NamedTuple

import streamlit as st
import streamlit.components.v1 as components

from summarize import summarize_transcript
from transcribe import transcribe_audio
from utils import cleanup_temp_files, ensure_audio_file, SUPPORTED_AUDIO_EXTENSIONS


APP_TITLE = "회의록 생성기"
LOGO_PATH = Path("assets/logo.png")

# 앱 전반에서 반복 사용하는 색상은 한곳에 모아 테마 변경 시 실수를 줄입니다.
COLOR_PRIMARY = "#6B3FA0"
COLOR_PRIMARY_DARK = "#5A4D8B"
COLOR_PRIMARY_DARKER = "#4D407D"
COLOR_SIDEBAR = "#2D1B69"
COLOR_TEXT = "#1A1A2E"
COLOR_MUTED = "#667085"
COLOR_BORDER = "#D7D2E8"
COLOR_BORDER_NEUTRAL = "#D0D5DD"
COLOR_SURFACE = "#FFFFFF"
COLOR_SURFACE_PURPLE = "#F4F3F8"
COLOR_DISABLED = "#F2F2F4"
COLOR_DISABLED_TEXT = "#8A8A96"

# 업로드 파일은 처리 중에만 /private/tmp 아래에 저장하고, 처리 후 즉시 삭제합니다.
UPLOAD_TEMP_DIR_PREFIX = "meeting_summarizer_upload_"

# API 호출 없이 UI 흐름을 확인하는 테스트 모드용 가상 파일명입니다.
MOCK_AUDIO_FILENAME = "테스트_회의.m4a"

# summarize.py가 생성하는 상위 섹션명입니다. 이 섹션들은 결과 화면에서 별도 영역으로 배치합니다.
TOP_RESULT_SECTIONS = ("확인 필요", "빠른 요약", "액션 아이템", "전체 회의록")

# 팀 이름/용어/클라이언트 정보를 LLM에 전달하기 위한 컨텍스트 파일 템플릿입니다.
TEAM_CONTEXT_TEMPLATE = """
## 팀원
홍길동 (홍팀장) - 데이터팀장

## 프로젝트/용어
VIP 프로젝트: 주요 클라이언트 프로젝트명

## 클라이언트
클라이언트명 - 담당자 이름
""".strip()


class ProcessResult(NamedTuple):
    """Meeting minutes generation result for UI storage."""

    meeting_minutes: str
    download_filename: str
    timings: dict[str, float]


class ProcessTimings(NamedTuple):
    """Elapsed processing times in seconds."""

    stt_seconds: float
    summary_seconds: float
    total_seconds: float

    def as_dict(self) -> dict[str, float]:
        """Return timings as a session-state friendly dictionary."""
        return {
            "stt_seconds": self.stt_seconds,
            "summary_seconds": self.summary_seconds,
            "total_seconds": self.total_seconds,
        }


class ResultSections(NamedTuple):
    """Meeting minutes sections used by the result preview UI."""

    warnings: str
    quick_summary: str
    action_items: str
    full_minutes: str
    decisions: str
    speaker_notes: str


def configure_page() -> None:
    """Configure Streamlit page metadata and base layout."""
    # Streamlit 전역 설정은 가장 먼저 호출해야 합니다.
    st.set_page_config(page_title=APP_TITLE, layout="centered")
    render_app_styles()
    st.markdown(f'<h1 class="main-title">{APP_TITLE}</h1>', unsafe_allow_html=True)
    st.caption("회의 녹음 파일을 업로드하면 음성을 텍스트로 변환하고 회의록을 작성합니다.")
    st.divider()
    render_streamlit_korean_labels()


def render_app_styles() -> None:
    """Render small CSS refinements for a more balanced Streamlit UI."""
    # Streamlit 기본 컴포넌트의 여백과 버튼 높이를 앱 테마에 맞게 보정합니다.
    st.markdown(f"<style>{build_app_styles()}</style>", unsafe_allow_html=True)


def build_app_styles() -> str:
    """Build the complete CSS payload for Streamlit component refinements."""
    return "\n".join(
        [
            build_layout_styles(),
            build_sidebar_styles(),
            build_card_styles(),
            build_uploader_styles(),
            build_input_styles(),
            build_button_styles(),
            build_result_anchor_styles(),
        ]
    )


def build_layout_styles() -> str:
    """Build CSS for the main page title and high-level spacing."""
    return f"""
        .main-title {{
            color: {COLOR_PRIMARY};
            font-size: 2.75rem;
            line-height: 1.15;
            font-weight: 800;
            margin: 0 0 0.5rem 0;
        }}
    """


def build_sidebar_styles() -> str:
    """Build CSS that keeps the sidebar dark regardless of Streamlit theme colors."""
    return f"""
        section[data-testid="stSidebar"] {{
            background-color: {COLOR_SIDEBAR};
        }}

        section[data-testid="stSidebar"],
        section[data-testid="stSidebar"] * {{
            color: {COLOR_SURFACE} !important;
        }}

        section[data-testid="stSidebar"] button {{
            border-color: rgba(255, 255, 255, 0.35);
            background: rgba(255, 255, 255, 0.08);
        }}

        section[data-testid="stSidebar"] button:hover {{
            border-color: {COLOR_SURFACE};
            background: rgba(255, 255, 255, 0.16);
        }}
    """


def build_card_styles() -> str:
    """Build CSS for bordered Streamlit containers used as cards."""
    return f"""
        div[data-testid="stVerticalBlockBorderWrapper"] {{
            background: {COLOR_SURFACE} !important;
        }}

        div[data-testid="stVerticalBlockBorderWrapper"] * {{
            color: {COLOR_TEXT} !important;
        }}

        div[data-testid="stVerticalBlock"] > div:has(div[data-testid="stFileUploader"]) {{
            gap: 0.75rem;
        }}
    """


def build_uploader_styles() -> str:
    """Build CSS for the file uploader dropzone and nested text layers."""
    return f"""
        div[data-testid="stFileUploaderDropzone"],
        div[data-testid="stFileUploaderDropzone"] > div,
        div[data-testid="stFileUploaderDropzone"] section,
        div[data-testid="stFileUploaderDropzone"] label {{
            min-height: 86px;
            border-radius: 8px;
            background: {COLOR_SURFACE_PURPLE} !important;
            background-color: {COLOR_SURFACE_PURPLE} !important;
            border-color: {COLOR_BORDER} !important;
        }}

        div[data-testid="stFileUploaderDropzone"],
        div[data-testid="stFileUploaderDropzone"] *,
        div[data-testid="stFileUploaderDropzoneInstructions"],
        div[data-testid="stFileUploaderDropzoneInstructions"] * {{
            color: {COLOR_TEXT} !important;
            opacity: 1 !important;
        }}

        div[data-testid="stFileUploaderDropzone"] p,
        div[data-testid="stFileUploaderDropzone"] span,
        div[data-testid="stFileUploaderDropzone"] small,
        div[data-testid="stFileUploaderDropzone"] div {{
            color: {COLOR_TEXT} !important;
            text-shadow: none !important;
        }}

        div[data-testid="stFileUploaderDropzone"] svg {{
            color: {COLOR_PRIMARY} !important;
            fill: none !important;
        }}

        div[data-testid="stFileUploaderDropzone"] button {{
            background: {COLOR_SURFACE_PURPLE} !important;
            border: 1px solid {COLOR_BORDER} !important;
            color: {COLOR_TEXT} !important;
        }}

        div[data-testid="stFileUploaderDropzoneInstructions"] {{
            min-width: 0;
        }}

        div[data-testid="stFileUploaderDropzoneInstructions"] span,
        div[data-testid="stFileUploaderDropzoneInstructions"] small {{
            white-space: normal;
        }}
    """


def build_input_styles() -> str:
    """Build CSS that keeps text inputs readable on the purple app theme."""
    return f"""
        div[data-baseweb="textarea"],
        div[data-baseweb="input"] {{
            background: {COLOR_SURFACE} !important;
        }}

        div[data-baseweb="textarea"] > div,
        div[data-baseweb="input"] > div {{
            background: {COLOR_SURFACE} !important;
            border-color: {COLOR_BORDER} !important;
        }}

        textarea,
        input,
        div[data-baseweb="textarea"] textarea,
        div[data-baseweb="input"] input {{
            background: {COLOR_SURFACE} !important;
            color: {COLOR_TEXT} !important;
            border-color: {COLOR_BORDER} !important;
            caret-color: {COLOR_PRIMARY} !important;
        }}

        textarea::placeholder,
        input::placeholder {{
            color: {COLOR_MUTED} !important;
            opacity: 1 !important;
        }}

        textarea {{
            line-height: 1.55 !important;
        }}

        label, p, span, small {{
            color: inherit;
        }}
    """


def build_button_styles() -> str:
    """Build CSS for Streamlit buttons."""
    return f"""
        button[kind="primary"], button[kind="secondary"] {{
            min-height: 42px;
            border-radius: 7px;
        }}

        button[kind="primary"]:not(:disabled) {{
            background-color: {COLOR_PRIMARY} !important;
            border-color: {COLOR_PRIMARY} !important;
            color: {COLOR_SURFACE} !important;
        }}

        button[kind="primary"]:disabled {{
            background-color: {COLOR_DISABLED} !important;
            border-color: {COLOR_BORDER_NEUTRAL} !important;
            color: {COLOR_DISABLED_TEXT} !important;
        }}
    """


def build_result_anchor_styles() -> str:
    """Build CSS for the invisible result scroll target."""
    return """
        #meeting-minutes-result {
            scroll-margin-top: 32px;
        }
    """


def render_streamlit_korean_labels() -> None:
    """Replace Streamlit uploader default English labels with Korean labels."""
    # 파일 업로더의 일부 문구는 Streamlit 옵션으로 바꿀 수 없어 DOM 텍스트만 치환합니다.
    components.html(build_uploader_localization_script(), height=0)


def build_uploader_localization_script() -> str:
    """Build JavaScript that localizes Streamlit uploader labels to Korean."""
    return """
        <script>
        const replacements = new Map([
          ["Browse files", "파일 선택"],
          ["Drag and drop file here", "파일을 여기에 끌어다 놓거나"],
          ["Limit 200MB per file", "파일당 최대 200MB"],
        ]);

        function localizeTextNodes(root) {
          const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
          const nodes = [];
          while (walker.nextNode()) {
            nodes.push(walker.currentNode);
          }

          for (const node of nodes) {
            const original = node.nodeValue.trim();
            if (replacements.has(original)) {
              node.nodeValue = node.nodeValue.replace(original, replacements.get(original));
            }
          }
        }

        function localizeParentDocument() {
          try {
            localizeTextNodes(window.parent.document.body);
          } catch (error) {
            localizeTextNodes(document.body);
          }
        }

        localizeParentDocument();
        setInterval(localizeParentDocument, 500);
        </script>
    """


def scroll_to_result_section() -> None:
    """Scroll the browser viewport to the meeting minutes result section."""
    components.html(build_scroll_to_result_script(), height=0)


def build_scroll_to_result_script() -> str:
    """Build JavaScript that scrolls the parent browser to the result section."""
    return """
        <script>
        const target = window.parent.document.getElementById("meeting-minutes-result");
        if (target) {
          target.scrollIntoView({ behavior: "smooth", block: "start" });
        }
        </script>
    """


def initialize_session_state() -> None:
    """Initialize Streamlit session state values used by the app."""
    # 결과/히스토리는 서버 저장 없이 현재 브라우저 세션 안에서만 유지합니다.
    st.session_state.setdefault("history", [])
    st.session_state.setdefault("meeting_minutes", "")
    st.session_state.setdefault("edited_minutes", "")
    st.session_state.setdefault("download_filename", "회의록.txt")
    st.session_state.setdefault("active_history_index", None)
    st.session_state.setdefault("timings", {})


def get_supported_upload_types() -> list[str]:
    """Return supported audio extensions in Streamlit uploader format."""
    return sorted(extension.lstrip(".") for extension in SUPPORTED_AUDIO_EXTENSIONS)


def save_uploaded_audio(uploaded_file: Any, temp_dir: Path) -> Path:
    """Save a Streamlit uploaded file to a temporary audio file path."""
    # 브라우저가 보낸 파일명에서 경로 요소를 제거해 임시 디렉터리 밖으로 나가지 않게 합니다.
    safe_filename = Path(uploaded_file.name).name
    if not safe_filename:
        safe_filename = "uploaded_audio"

    temp_audio_path = temp_dir / safe_filename
    temp_audio_path.write_bytes(uploaded_file.getbuffer())
    ensure_audio_file(temp_audio_path)
    return temp_audio_path


def cleanup_upload_temp_files(temp_audio_path: Path | None, temp_dir: Path | None) -> None:
    """Delete the uploaded temporary audio file and its temporary directory."""
    # STT 내부에서 생성한 청크는 transcribe.py가 정리하고, 여기서는 업로드 원본만 정리합니다.
    if temp_audio_path is not None:
        cleanup_temp_files([temp_audio_path])

    if temp_dir is not None:
        try:
            if temp_dir.exists():
                temp_dir.rmdir()
        except Exception as exc:
            st.warning(f"임시 폴더 정리에 실패했습니다: {exc}")


def build_transcript_context(transcript: str, attendees: str) -> str:
    """Add optional attendee context before summarization."""
    # 참석자 정보는 모델이 액션 아이템 담당자를 추론할 때 참고하는 보조 맥락입니다.
    cleaned_attendees = attendees.strip()
    if not cleaned_attendees:
        return transcript

    return f"""
참석자 참고 정보:
{cleaned_attendees}

Transcript:
{transcript}
""".strip()


def build_download_filename(uploaded_filename: str) -> str:
    """Build a meeting minutes download filename from the uploaded audio name."""
    # 현재 정책은 원본명과 무관하게 날짜 기반 파일명으로 저장합니다.
    _ = uploaded_filename
    return f"회의록_{get_compact_date_label()}.txt"


def build_meeting_title(uploaded_filename: str) -> str:
    """Build a dated meeting minutes title from the uploaded audio name."""
    audio_stem = Path(uploaded_filename).stem.strip()
    today = get_korean_date_label()
    if audio_stem:
        return f"# {audio_stem} 회의록 ({today})"
    return f"# 회의록 ({today})"


def get_korean_date_label() -> str:
    """Return today's date in Korean display format."""
    now = datetime.now()
    return f"{now.year}년 {now.month}월 {now.day}일"


def get_compact_date_label() -> str:
    """Return today's date in compact filename format."""
    return datetime.now().strftime("%Y%m%d")


def get_korean_time_label() -> str:
    """Return current time in Korean 12-hour display format."""
    now = datetime.now()
    meridiem = "오전" if now.hour < 12 else "오후"
    hour = now.hour % 12 or 12
    return f"{meridiem} {hour}시 {now.minute}분"


def prepend_meeting_title(meeting_minutes: str, uploaded_filename: str) -> str:
    """Add a dated title to the top of generated meeting minutes."""
    title = build_meeting_title(uploaded_filename)
    return f"{title}\n\n{meeting_minutes.strip()}"


def format_duration(seconds: float) -> str:
    """Format elapsed seconds for display."""
    if seconds < 60:
        return f"{seconds:.1f}초"

    minutes = int(seconds // 60)
    remaining_seconds = seconds % 60
    return f"{minutes}분 {remaining_seconds:.1f}초"


def render_inputs() -> tuple[Any, str, str, bool, bool]:
    """Render upload and option inputs for the meeting summarizer."""
    # 입력 영역은 실제 처리와 테스트 처리 모두에서 공유합니다.
    uploaded_file, team_context = render_upload_section()
    attendees = render_meeting_info_section()
    process_requested, mock_requested = render_process_buttons(uploaded_file is not None)
    return uploaded_file, attendees, team_context, process_requested, mock_requested


def render_upload_section() -> tuple[Any, str]:
    """Render context/audio upload controls and return uploaded inputs."""
    with st.container(border=True):
        st.subheader("파일 업로드")
        context_file = st.file_uploader(
            "팀 컨텍스트 파일 (선택)",
            type=["md", "txt"],
            accept_multiple_files=False,
            key="team_context_file",
        )
        st.download_button(
            "팀 컨텍스트 템플릿 다운로드",
            data=TEAM_CONTEXT_TEMPLATE,
            file_name="팀_컨텍스트_템플릿.md",
            mime="text/markdown",
            use_container_width=True,
        )
        uploaded_file = st.file_uploader(
            "오디오 파일",
            type=get_supported_upload_types(),
            accept_multiple_files=False,
        )
        return uploaded_file, read_uploaded_text_file(context_file)


def read_uploaded_text_file(uploaded_file: Any) -> str:
    """Read an optional uploaded text file as UTF-8 context."""
    if uploaded_file is None:
        return ""

    try:
        # 내부 컨텍스트 파일은 사람이 작성한 Markdown/Text 문서이므로 UTF-8 텍스트로 처리합니다.
        return uploaded_file.getvalue().decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise RuntimeError("팀 컨텍스트 파일은 UTF-8로 저장된 .md 또는 .txt 파일이어야 합니다.") from exc


def render_meeting_info_section() -> str:
    """Render optional meeting metadata inputs."""
    with st.container(border=True):
        st.subheader("회의 정보")
        attendees = st.text_area(
            "참석자 이름 (선택)",
            placeholder="예: 김민수, 이서연, 박지훈 (쉼표로 구분)",
            height=96,
        )
        st.caption("입력하면 액션 아이템 담당자 자동 매핑")
        return attendees


def render_process_buttons(has_uploaded_file: bool) -> tuple[bool, bool]:
    """Render real and mock process buttons in a balanced row."""
    process_column, test_column = st.columns(2)
    with process_column:
        process_requested = st.button(
            "처리 시작",
            type="primary",
            disabled=not has_uploaded_file,
            use_container_width=True,
        )
    with test_column:
        mock_requested = st.button(
            "테스트 실행",
            use_container_width=True,
        )

    return process_requested, mock_requested


def process_meeting_audio(uploaded_file: Any, attendees: str, team_context: str) -> ProcessResult:
    """Run STT and summarization for an uploaded audio file."""
    temp_dir: Path | None = None
    temp_audio_path: Path | None = None

    try:
        # 전체 시간은 임시 파일 저장부터 요약 완료까지 사용자 체감 구간으로 측정합니다.
        total_started_at = time.perf_counter()
        temp_dir = Path(mkdtemp(prefix=UPLOAD_TEMP_DIR_PREFIX, dir="/private/tmp"))
        temp_audio_path = save_uploaded_audio(uploaded_file, temp_dir)

        progress = st.progress(0, text="오디오 파일 준비 중")
        with st.status("회의록 생성 중", expanded=True) as status:
            status.write("오디오 파일 검증 완료")
            transcript, stt_elapsed = run_stt_step(temp_audio_path, progress, status)
            meeting_minutes, summary_elapsed = run_summary_step(transcript, attendees, team_context, progress)
            total_elapsed = time.perf_counter() - total_started_at
            complete_progress(progress, status, summary_elapsed, total_elapsed)

        download_filename = build_download_filename(uploaded_file.name)
        titled_meeting_minutes = prepend_meeting_title(meeting_minutes, uploaded_file.name)
        timings = ProcessTimings(stt_elapsed, summary_elapsed, total_elapsed)
        return ProcessResult(titled_meeting_minutes, download_filename, timings.as_dict())
    finally:
        cleanup_upload_temp_files(temp_audio_path, temp_dir)


def run_stt_step(temp_audio_path: Path, progress: Any, status: Any) -> tuple[str, float]:
    """Transcribe the uploaded audio and return the transcript with elapsed time."""
    progress.progress(15, text="음성을 텍스트로 변환하는 중...")

    # STT 시간은 요약 시간과 별도로 보여줘 병목을 바로 확인할 수 있게 합니다.
    stt_started_at = time.perf_counter()
    transcript = transcribe_audio(temp_audio_path)
    stt_elapsed = time.perf_counter() - stt_started_at
    status.write(f"음성 변환 완료: {format_duration(stt_elapsed)}")
    return transcript, stt_elapsed


def run_summary_step(transcript: str, attendees: str, team_context: str, progress: Any) -> tuple[str, float]:
    """Summarize the transcript and return meeting minutes with elapsed time."""
    progress.progress(70, text="회의록을 작성하는 중...")
    transcript_context = build_transcript_context(transcript, attendees)

    summary_started_at = time.perf_counter()
    summary = summarize_transcript(transcript_context, context=team_context)
    summary_elapsed = time.perf_counter() - summary_started_at
    return summary["minutes"], summary_elapsed


def complete_progress(progress: Any, status: Any, summary_elapsed: float, total_elapsed: float) -> None:
    """Mark the progress UI as complete and show final timing messages."""
    progress.progress(100, text="완료")
    # 요약 시간은 이 함수 호출 전에도 기록하지만, 완료 상태 근처에도 한 번 더 명시합니다.
    status.write(f"회의록 작성 완료: {format_duration(summary_elapsed)}")
    status.write(f"전체 처리 시간: {format_duration(total_elapsed)}")
    status.update(label="회의록 생성 완료", state="complete")


def process_mock_meeting_audio(attendees: str) -> ProcessResult:
    """Return dummy meeting minutes without calling external APIs."""
    # UI 검수용 경로이므로 OpenAI API와 오디오 파일 처리를 호출하지 않습니다.
    timings = render_mock_progress()
    meeting_minutes = build_mock_meeting_minutes(attendees)
    titled_minutes = prepend_meeting_title(meeting_minutes, MOCK_AUDIO_FILENAME)
    download_filename = build_download_filename(MOCK_AUDIO_FILENAME)
    return ProcessResult(titled_minutes, download_filename, timings.as_dict())


def render_mock_progress() -> ProcessTimings:
    """Render progress UI for dummy processing and return fake timings."""
    progress = st.progress(0, text="테스트 데이터를 준비하는 중")
    with st.status("테스트 회의록 생성 중", expanded=True) as status:
        status.write("더미 오디오 파일 검증 완료")
        progress.progress(15, text="음성을 텍스트로 변환하는 중...")
        time.sleep(0.2)
        stt_elapsed = 1.8
        status.write(f"음성 변환 완료: {format_duration(stt_elapsed)}")

        progress.progress(70, text="회의록을 작성하는 중...")
        time.sleep(0.2)
        summary_elapsed = 2.4
        total_elapsed = stt_elapsed + summary_elapsed
        status.write(f"회의록 작성 완료: {format_duration(summary_elapsed)}")
        status.write(f"전체 처리 시간: {format_duration(total_elapsed)}")
        progress.progress(100, text="완료")
        status.update(label="테스트 회의록 생성 완료", state="complete")

    return ProcessTimings(stt_elapsed, summary_elapsed, total_elapsed)


def build_mock_meeting_minutes(attendees: str) -> str:
    """Build a realistic dummy meeting minutes body for UI testing."""
    cleaned_attendees = attendees.strip() or "김민수, 이서연, 박지훈"

    return f"""
## 회의 요약
- 신규 회의록 생성 도구의 내부 배포 방향을 검토했습니다.
- 사용자는 오디오 파일 업로드 후 회의록을 편집하고 저장할 수 있어야 합니다.
- 초기 버전은 Streamlit으로 빠르게 배포하고, 사용량이 늘면 API 서버 분리를 검토하기로 했습니다.
- 참석자 정보는 액션 아이템 담당자 매핑 정확도를 높이는 보조 정보로 활용합니다.

## 주요 결정사항
- 내부 테스트용 UI에는 실제 API 호출 없이 동작하는 테스트 실행 버튼을 제공하기로 했습니다.
- 회의록 결과는 사용자가 직접 수정한 뒤 저장할 수 있게 유지합니다.
- 세션 히스토리는 현재 브라우저 세션 안에서만 보관합니다.

## 액션 아이템
- 담당자: 김민수
  기한: 이번 주 금요일
  할 일: Streamlit 배포 환경에서 API 키와 ffmpeg 설정을 확인
- 담당자: 이서연
  기한: 미정
  할 일: 실제 회의 녹음 샘플로 품질 검수
- 담당자: 박지훈
  기한: 다음 회의 전
  할 일: 내부 사용자 피드백 항목 정리

## 주요 발언 요약
- {cleaned_attendees}: 회의록 생성 결과를 바로 편집하고 저장하는 흐름이 중요하다고 논의했습니다.
- 제품 관점에서는 테스트 모드가 있어야 배포 전 UI 검수가 쉽다는 의견이 있었습니다.
- 운영 관점에서는 업로드 파일과 임시 파일을 처리 후 삭제하는 정책을 유지해야 한다는 점이 강조되었습니다.
""".strip()


def store_result(uploaded_filename: str, result: ProcessResult) -> None:
    """Store a generated result in session state and history."""
    # 편집 영역의 초기값도 새 결과로 맞춰 다운로드가 수정본 기준으로 동작하게 합니다.
    st.session_state["meeting_minutes"] = result.meeting_minutes
    st.session_state["edited_minutes"] = result.meeting_minutes
    st.session_state["download_filename"] = result.download_filename
    st.session_state["timings"] = result.timings
    add_history_entry(uploaded_filename, result)
    st.session_state["scroll_to_result"] = True


def add_history_entry(uploaded_filename: str, result: ProcessResult) -> None:
    """Append a generated meeting minutes result to session history."""
    # 최신 변환 결과가 사이드바 상단에 오도록 앞쪽에 추가합니다.
    history_entry = {
        "uploaded_filename": uploaded_filename,
        "title": build_meeting_title(uploaded_filename).lstrip("# "),
        "meeting_minutes": result.meeting_minutes,
        "download_filename": result.download_filename,
        "timings": result.timings,
        "created_at": get_korean_time_label(),
    }
    st.session_state["history"].insert(0, history_entry)
    st.session_state["active_history_index"] = 0


def load_history_entry(index: int) -> None:
    """Load a session history item into the current preview."""
    # 히스토리를 열면 편집 중이던 내용도 해당 회의록으로 교체합니다.
    history_entry = st.session_state["history"][index]
    st.session_state["meeting_minutes"] = history_entry["meeting_minutes"]
    st.session_state["edited_minutes"] = history_entry["meeting_minutes"]
    st.session_state["download_filename"] = history_entry["download_filename"]
    st.session_state["timings"] = history_entry["timings"]
    st.session_state["active_history_index"] = index


def render_history_sidebar() -> None:
    """Render generated meeting minutes history in the sidebar."""
    render_sidebar_logo()
    st.sidebar.header("세션 히스토리")
    st.sidebar.caption("이번 세션에서 변환한 회의록")
    history = st.session_state.get("history", [])

    if not history:
        st.sidebar.caption("이번 세션에서 변환한 파일이 없습니다.")
        return

    for index, history_entry in enumerate(history):
        filename = Path(history_entry["uploaded_filename"]).name
        label = f"{filename}\n{history_entry['created_at']}"
        if st.sidebar.button(label, key=f"history_{index}", use_container_width=True):
            load_history_entry(index)


def render_sidebar_logo() -> None:
    """Render the company logo at the top of the sidebar when available."""
    if LOGO_PATH.exists():
        st.sidebar.image(str(LOGO_PATH), width=180)


def render_timing_summary() -> None:
    """Render processing time metrics for the current result."""
    timings = st.session_state.get("timings") or {}
    if not timings:
        return

    st.caption(
        " · ".join(
            [
                f"음성 변환 {format_duration(timings.get('stt_seconds', 0.0))}",
                f"회의록 작성 {format_duration(timings.get('summary_seconds', 0.0))}",
                f"전체 {format_duration(timings.get('total_seconds', 0.0))}",
            ]
        )
    )


def render_result_actions(edited_minutes: str, download_filename: str) -> None:
    """Render result action buttons in a horizontal layout."""
    # 복사와 저장 버튼은 같은 HTML/CSS 안에서 렌더링해 높이와 간격을 맞춥니다.
    components.html(build_result_actions_html(edited_minutes, download_filename), height=52)


def build_result_actions_html(edited_minutes: str, download_filename: str) -> str:
    """Build HTML for copy and save action buttons."""
    return f"""
    <style>{build_result_actions_styles()}</style>
    {build_result_actions_markup()}
    {build_result_actions_script(edited_minutes, download_filename)}
    """


def build_result_actions_styles() -> str:
    """Build CSS for copy and save action buttons."""
    return f"""
    .action-row {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      width: 100%;
      padding-top: 2px;
    }}

    .meeting-action {{
      height: 42px;
      border-radius: 7px;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: background 120ms ease, border-color 120ms ease, color 120ms ease;
    }}

    .copy-action {{
      background: {COLOR_SURFACE};
      border: 1px solid {COLOR_BORDER_NEUTRAL};
      color: {COLOR_TEXT};
    }}

    .copy-action:hover {{
      border-color: {COLOR_PRIMARY_DARK};
      color: {COLOR_PRIMARY_DARK};
    }}

    .save-action {{
      background: {COLOR_PRIMARY_DARK};
      border: 1px solid {COLOR_PRIMARY_DARK};
      color: {COLOR_SURFACE};
    }}

    .save-action:hover {{
      background: {COLOR_PRIMARY_DARKER};
      border-color: {COLOR_PRIMARY_DARKER};
    }}
    """


def build_result_actions_markup() -> str:
    """Build HTML markup for result action buttons."""
    return """
    <div class="action-row">
      <button id="copy-minutes" class="meeting-action copy-action">회의록 복사</button>
      <button id="save-minutes" class="meeting-action save-action">회의록 저장</button>
    </div>
    """


def build_result_actions_script(edited_minutes: str, download_filename: str) -> str:
    """Build JavaScript for clipboard copy and text-file download actions."""
    return f"""
    <script>
    const text = {json.dumps(edited_minutes)};
    const filename = {json.dumps(download_filename)};
    const copyButton = document.getElementById("copy-minutes");
    const saveButton = document.getElementById("save-minutes");

    copyButton.addEventListener("click", async () => {{
      try {{
        await navigator.clipboard.writeText(text);
        copyButton.innerText = "복사 완료";
        setTimeout(() => copyButton.innerText = "회의록 복사", 1600);
      }} catch (error) {{
        copyButton.innerText = "복사 실패";
        setTimeout(() => copyButton.innerText = "회의록 복사", 1600);
      }}
    }});

    saveButton.addEventListener("click", () => {{
      const blob = new Blob([text], {{ type: "text/plain;charset=utf-8" }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }});
    </script>
    """


def get_korean_error_message(error: Exception) -> str:
    """Return a Korean user-facing error message for known failure cases."""
    error_text = str(error)

    if "OPENAI_API_KEY" in error_text:
        return "OpenAI API 키가 설정되지 않았습니다. 서버의 환경 변수를 확인해 주세요."
    if "ffmpeg" in error_text.lower():
        return "오디오 처리를 위한 ffmpeg가 설치되어 있지 않습니다. 서버 환경을 확인해 주세요."
    if "Unsupported audio file extension" in error_text:
        return "지원하지 않는 오디오 파일 형식입니다. 다른 오디오 파일을 선택해 주세요."
    if "Audio file does not exist" in error_text:
        return "업로드한 오디오 파일을 찾을 수 없습니다. 다시 업로드해 주세요."
    if "Transcript is empty" in error_text:
        return "음성에서 변환된 텍스트가 없습니다. 녹음 상태를 확인해 주세요."

    return "처리 중 문제가 발생했습니다. 파일 형식, 네트워크 상태, API 설정을 확인해 주세요."


def split_top_result_sections(minutes_text: str) -> dict[str, str]:
    """Split generated minutes into top-level app display sections."""
    sections: dict[str, list[str]] = {}
    current_section: str | None = None

    for line in minutes_text.splitlines():
        section_title = parse_markdown_heading_title(line)
        if should_start_top_result_section(current_section, section_title):
            current_section = section_title
            sections.setdefault(current_section, [])
            continue

        if current_section is not None:
            sections[current_section].append(line)

    return {title: "\n".join(lines).strip() for title, lines in sections.items()}


def should_start_top_result_section(current_section: str | None, section_title: str | None) -> bool:
    """Return whether a Markdown heading starts one of the app's top preview sections."""
    return current_section != "전체 회의록" and section_title in TOP_RESULT_SECTIONS


def parse_markdown_heading_title(line: str) -> str | None:
    """Return a normalized Markdown heading title without leading emoji markers."""
    match = re.match(r"^\s*#{1,6}\s+(?P<title>.+?)\s*$", line)
    if not match:
        return None

    title = match.group("title").strip()
    # Streamlit 화면 배치용 비교에서는 이모지와 장식 문자를 제외하고 제목만 봅니다.
    return re.sub(r"^[^\w가-힣]+", "", title).strip()


def extract_markdown_section(markdown_text: str, title: str) -> str:
    """Extract one Markdown section body by heading title."""
    lines: list[str] = []
    collecting = False

    for line in markdown_text.splitlines():
        heading_title = parse_markdown_heading_title(line)
        if heading_title:
            if collecting:
                break
            collecting = heading_title == title
            continue

        if collecting:
            lines.append(line)

    return "\n".join(lines).strip()


def build_result_display_sections(minutes_text: str) -> ResultSections:
    """Build all sections needed for the result preview UI."""
    top_sections = split_top_result_sections(minutes_text)
    full_minutes = top_sections.get("전체 회의록") or minutes_text

    return ResultSections(
        warnings=top_sections.get("확인 필요", ""),
        quick_summary=top_sections.get("빠른 요약") or extract_markdown_section(full_minutes, "회의 요약"),
        action_items=top_sections.get("액션 아이템") or extract_markdown_section(full_minutes, "액션 아이템"),
        full_minutes=full_minutes,
        decisions=extract_markdown_section(full_minutes, "주요 결정사항"),
        speaker_notes=extract_markdown_section(full_minutes, "주요 발언 요약"),
    )


def render_markdown_section(title: str, content: str, empty_text: str = "내용 없음") -> None:
    """Render a titled Markdown preview section."""
    st.markdown(f"#### {title}")
    if content.strip():
        st.markdown(content.strip())
    else:
        st.caption(empty_text)


def render_result_preview_sections(sections: ResultSections) -> None:
    """Render always-visible and expandable meeting minutes sections."""
    render_markdown_section("📋 빠른 요약", sections.quick_summary, "요약 없음")
    render_action_items_preview(sections.action_items)

    with st.expander("📝 전체 회의록", expanded=False):
        st.markdown(sections.full_minutes.strip() or "회의록 없음")

    with st.expander("주요 결정사항", expanded=False):
        st.markdown(sections.decisions.strip() or "주요 결정사항 없음")

    with st.expander("주요 발언 요약", expanded=False):
        st.markdown(sections.speaker_notes.strip() or "주요 발언 요약 없음")


def render_action_items_preview(action_items_text: str) -> None:
    """Render action items with row-level missing-owner/deadline labels."""
    st.markdown("#### ✅ 액션 아이템")
    if not action_items_text.strip():
        st.caption("액션 아이템 없음")
        return

    rendered_items = [render_action_item_line(line) for line in action_items_text.splitlines() if line.strip()]
    st.markdown("<ul>" + "".join(rendered_items) + "</ul>", unsafe_allow_html=True)


def render_action_item_line(line: str) -> str:
    """Render one action item line, highlighting only missing fields in gray."""
    parsed_item = parse_action_item_line(line)
    if parsed_item is None:
        return f"<li>{escape_html(line.lstrip('- ').strip())}</li>"

    owner_label = build_missing_field_label("담당자 미지정") if is_missing_field(parsed_item["owner"]) else escape_html(
        parsed_item["owner"]
    )
    due_date_label = build_missing_field_label("기한 미정") if is_missing_field(parsed_item["due_date"]) else escape_html(
        parsed_item["due_date"]
    )
    task = escape_html(parsed_item["task"] or "내용 미정")

    return f"<li>담당자: {owner_label} / 기한: {due_date_label} / 할 일: {task}</li>"


def parse_action_item_line(line: str) -> dict[str, str] | None:
    """Parse the structured action item line produced by summarize.py."""
    normalized_line = line.lstrip("- ").replace("⚠️", "").strip()
    match = re.match(
        r"담당자:\s*(?P<owner>.*?)\s*/\s*기한:\s*(?P<due_date>.*?)\s*/\s*할 일:\s*(?P<task>.*)$",
        normalized_line,
    )
    if not match:
        return None
    return {key: value.strip() for key, value in match.groupdict().items()}


def is_missing_field(value: str) -> bool:
    """Return whether an action-item field should be displayed as missing."""
    return value.strip() in {"", "미정", "None", "null"}


def build_missing_field_label(label: str) -> str:
    """Build a muted inline label for missing action-item fields."""
    return f'<span style="color:#8A8A96; font-weight:600;">{label}</span>'


def escape_html(value: str) -> str:
    """Escape text before rendering small HTML snippets in Streamlit."""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def render_result() -> None:
    """Render meeting minutes preview and download controls."""
    meeting_minutes = st.session_state.get("meeting_minutes")
    download_filename = st.session_state.get("download_filename", "회의록.txt")

    if not meeting_minutes:
        return

    # 자동 스크롤 target을 결과 카드 바로 위에 둡니다.
    st.divider()
    st.markdown('<div id="meeting-minutes-result"></div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.subheader("회의록 미리보기")
        render_timing_summary()
        if not st.session_state.get("edited_minutes"):
            st.session_state["edited_minutes"] = meeting_minutes

        edited_minutes = st.session_state.get("edited_minutes", meeting_minutes)
        render_result_preview_sections(build_result_display_sections(edited_minutes))
        render_result_actions(edited_minutes, download_filename)


def main() -> None:
    """Render the Streamlit app and handle user actions."""
    configure_page()
    initialize_session_state()
    uploaded_file, attendees, team_context, process_requested, mock_requested = render_inputs()
    result_placeholder = st.empty()

    if process_requested and uploaded_file is not None:
        try:
            # 실제 실행은 기존 STT/요약 모듈을 그대로 사용합니다.
            store_result(uploaded_file.name, process_meeting_audio(uploaded_file, attendees, team_context))
        except Exception as exc:
            st.error(f"회의록 생성 중 오류가 발생했습니다. {get_korean_error_message(exc)}")

    if mock_requested:
        # 테스트 실행은 API 비용 없이 동일한 결과 UI 흐름만 확인합니다.
        store_result(MOCK_AUDIO_FILENAME, process_mock_meeting_audio(attendees))

    # 처리 결과를 session_state에 저장한 뒤 사이드바를 그려야 방금 만든 회의록이 즉시 보입니다.
    render_history_sidebar()

    with result_placeholder.container():
        render_result()

    if st.session_state.pop("scroll_to_result", False):
        scroll_to_result_section()


if __name__ == "__main__":
    main()
