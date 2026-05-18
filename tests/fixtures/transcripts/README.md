# Synthetic Transcript Fixtures

이 디렉터리의 transcript는 모두 가상 데이터입니다. 실제 고객명, 회사명, 개인 정보는 포함하지 않았습니다.

## short_clear_meeting.txt

- 목적: 짧고 명확한 direct mode 회의의 baseline 확인
- 예상 strategy: direct
- 기대 action item 수: 약 3개
- 기대 decision 수: 약 2개
- imperfect 요소: `데쉬보드` 오인식, `이번주... 아니` self-correction, 중간 filler
- 테스트 포인트: 담당자와 기한이 명확한 action item 추출, source_quote grounding, public result shape 유지

## medium_project_meeting.txt

- 목적: direct와 chunk 경계 근처의 프로젝트 회의 검증
- 예상 strategy: chunk 가능성이 높음(70 utterance 이상)
- 기대 action item 수: 8개 이상
- 기대 decision 수: 6개 이상
- imperfect 요소: `디더블유에이치`, `이티엘`, `피오씨`, `데쉬보드`, 띄어쓰기 흔들림, self-correction
- 테스트 포인트: 일부 애매한 기한 정정 처리, 리스크와 후속 확인 분리, standard/medium 크기 transcript profiling

## long_action_heavy_meeting.txt

- 목적: conditional chunk mode, overlap, merge, action item recall 검증
- 예상 strategy: chunk(180개 이상 utterance, deep 기준 220개 미만)
- 기대 action item 수: 20개 이상
- 기대 decision 수: 10개 이상
- imperfect 요소: `디더블유에이치`, `이티엘`, `에이피아이`, `피오씨`, `데쉬보드`, `데이터마트/데이터 마트`, 반복 재언급
- 테스트 포인트: chunk별 extraction 후 merge 중복 제거, 반복 action item 보존/병합, 긴 회의에서 action item 누락 방지

## ambiguous_owner_due_date_meeting.txt

- 목적: 애매한 담당자와 기한에 대한 warning quality 검증
- 예상 strategy: direct
- 기대 action item 수: 4개 이상
- 기대 decision 수: 2개 이상
- imperfect 요소: `제가 한번 볼게요`, `다음에`, `이번 주 안에는`, `그 그거`, self-correction
- 테스트 포인트: low confidence action item, 담당자/기한 warning, validation과 user-facing warning 품질

## decision_action_overlap_meeting.txt

- 목적: decision과 action item이 같은 문장에 겹치는 케이스 검증
- 예상 strategy: direct
- 기대 action item 수: 6개 이상
- 기대 decision 수: 4개 이상
- imperfect 요소: 중간 filler, 담당자 정정, `이번 주 안으로`, `에이피아이`, `디더블유에이치`
- 테스트 포인트: `~하기로 했다` 문장이 decision과 action item 모두로 잡히는지, 담당자 없는 확정 작업 warning association

## no_action_items_meeting.txt

- 목적: 공유 중심 회의에서 action item false positive 방지
- 예상 strategy: direct
- 기대 action item 수: 0개
- 기대 decision 수: 0~1개
- imperfect 요소: `음`, `로그포맷`, `디더블유에이치`, `이티엘`
- 테스트 포인트: 현황 공유와 참고 사항을 action item으로 과추출하지 않는지, 명확한 결정 없음 처리
