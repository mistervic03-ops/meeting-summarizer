# Meeting Summarizer Agent Guide

BigxData 내부 회의록 도구입니다. 오디오 업로드, STT, transcript 검토, 요약, 렌더링/내보내기를 한 저장소에서 제공합니다.

## 문서 맵

- `README.md`: GitHub 첫 화면용 프로젝트 개요, 기술 스택, 실행 방법.
- `docs/ARCHITECTURE.md`: 현재 디렉터리 구조와 audio upload -> STT -> transcript review -> summarization -> result 데이터 흐름.
- `docs/SUMMARIZATION_ENGINE.md`: 요약 엔진 구조, pipeline 단계, prompt/validation/rendering 작업 기준.
- `docs/DEPLOYMENT_SPARK.md`: Spark/GB10 Docker Compose 배포와 local GPU overlay 기준.
- `docs/DEAD_CODE.md`: 현재 Spark production deployment에서 비활성인 legacy/abandoned code 목록.

## 필수 작업 규칙

- 작업 시작 전 변경 범위와 관련된 `docs/` 파일을 먼저 읽습니다.
- 코드 변경 후 영향받은 `docs/` 파일을 업데이트하고 응답에서 업데이트 여부를 명시합니다.
- frontend 변경 시 commit 전 `npm run tsc -b`를 실행합니다.
- pipeline 또는 summarization 변경 시 `docs/SUMMARIZATION_ENGINE.md`를 업데이트합니다.
- deployment config 변경 시 `docs/DEPLOYMENT_SPARK.md`를 업데이트합니다.
- API endpoint 변경 시 `docs/ARCHITECTURE.md`와 이 파일의 데이터 흐름 관련 지침을 함께 업데이트합니다.

## 브랜치와 배포

- feature branch는 `gpu-whisper-runtime`에서 분기합니다.
- Spark 배포에서 local GPU mode는 plain compose가 아니라 overlay 명령으로 활성화합니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.local-gpu.yml up -d --build
```

## Live vs Dead Code

현재 production에서 쓰는 경로와 남아 있는 legacy 경로를 혼동하지 마세요. 작업 전 `docs/DEAD_CODE.md`를 확인하고, dead code를 건드리거나 제거할 때는 해당 문서도 갱신합니다.
