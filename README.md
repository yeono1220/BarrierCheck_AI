# BarrierCheck AI

**PSV(안전밸브) 정비 후 증빙 서류 교차검증 · Upstage Studio 워크플로 데모**
Cross-checks pressure safety valve (PSV) maintenance document packages against each other and against the approved design basis, then drafts the follow-up document for each decision.

> 2026 Aramco × 고려대학교 × Upstage AI Hackathon · Team 람코냥이
> Prototype for decision support. Results support engineering review; they do **not** certify equipment safety or authorize restart.

---

## 무엇을 하나 / What it does

PDF 1개(정비 건 1건)를 넣으면 Upstage Studio 워크플로가 다음을 수행합니다.

| 단계 | 내용 |
|---|---|
| 읽기 | Parse(OCR)로 스캔·회전·팩스 PDF 판독 |
| 분류 | Classify로 문서 종류 분류 (승인 설계 기준정보, 설비 사양서, 정비·교체 작업기록서, 시험·교정 성적서, 설치·승인 점검서 등) |
| 추출 | Extract로 태그, 일련번호, 설정압력, As-left, 교정 유효기간, 승인 서명, MOC 등 추출 |
| 대조 | 문서 정합성 R1~R7, 승인 요구조건 Q1~Q8을 충족 / 위반 / 확인 불가 / 해당 없음으로 평가 |
| 판정 | `document_consistency`, `approval_compliance` = PASS / FAIL / 검토 필요, `reason` |
| 후속 조치 | FAIL → 부적합·재작업 요청서, 검토 필요 → 보완 요청서, PASS → 종결 검토 기록 |

판정 규칙: 위반이 하나라도 있으면 FAIL, 위반은 없지만 확정할 수 없으면(서명 대기, 판독 불가, 미제출 서류, 비교 조건 누락) **검토 필요**, 나머지는 PASS. 기준값은 고정하지 않고 사례마다 첨부된 승인 설계 기준정보에서 읽습니다.

## 이 저장소 / This repository

로컬 데모 웹앱입니다. 판정 로직은 모두 Upstage Studio 워크플로 안에 있고, 이 앱은 결과를 **화면에 보여 주고 저장**하는 역할만 합니다.

| 파일 | 역할 |
|---|---|
| `index.html`, `style.css`, `app.js` | 프론트엔드 (업로드, 배치 큐, 규칙 체크리스트, 판정 카드, 후속 조치 보고서 미리보기·PDF 저장) |
| `adapter.js` | 같은 출처의 로컬 서버(`/api/review`)만 호출. 브라우저에 API 키 없음 |
| `server.py` | 로컬 브리지 서버 (127.0.0.1:8765). PDF를 Studio API로 보내고 07·08 노드 출력과 05 규칙 상태를 돌려줌 |
| `workflow_config.json` | 호출할 Studio 워크플로·설정 번호, 판정 노드(07)·보고서 노드(08) 이름 |
| `test_bridge.py` | 합성 데이터로 브리지 파싱 테스트 (`python -m unittest test_bridge`) |
| `START_WINDOWS.bat` | Windows 실행 스크립트 |

## 실행 / Run locally

요구 사항: Python 3.9+ (추가 패키지 없음), Upstage Studio API 키(워크플로가 있는 조직의 키).

```bash
# Windows: START_WINDOWS.bat 더블클릭
python server.py
# 키 입력 프롬프트가 뜹니다 (또는 환경 변수 UPSTAGE_API_KEY)
# Enter만 누르면 미리보기 모드(예시 데이터, API 호출 없음)
```

브라우저에서 `http://127.0.0.1:8765` → PDF 업로드 → `Run verification`.
결과 화면 → Next action → `View full draft →`(후속 조치 보고서 미리보기) / `Download draft ↓`(PDF 저장).

- API 키는 파일에 저장되지 않습니다. 저장소에 키를 커밋하지 마세요.
- 서버는 로컬 전용입니다. 그대로 인터넷에 공개하면 다른 사람이 키로 워크플로를 실행할 수 있습니다.
- 진단 파일(`diagnostics/`)은 문서 근거를 담을 수 있어 커밋하지 않습니다.

## 데이터 / Data

데모·평가용 문서는 KOSHA GUIDE 별지 서식, PHMSA Form 7 등 **공개 서식에 가상 값만 채운 문서**입니다. 실제 회사 자료, 로고, 직인, 개인정보는 없습니다. 승인 기준의 참고 표준(ASME XIII, API 520/521/527/576/510 등)은 가상 기준을 만들 때 참고한 것이며, 이 도구가 해당 표준에 따른 공식 판정을 한다는 뜻이 아닙니다.

## 한계 / Limitations

- 실제 현장 서류로 검증하지 않았습니다(공개 서식 기반 실현 가능성 단계).
- 경계값 근접 시 재시험 권고, 법정 기준과 사내 기준 자동 비교는 다음 단계 과제입니다.
- 범위: 스프링식 일반형, 기체·증기용 PSV의 정비·벤치 시험 뒤 재설치 전 서류 검토. 파일럿식·파열판·보일러 증기용은 범위 밖입니다.

## GitHub Pages (보기 전용 데모)

`gh-pages` 브랜치는 서버 없이 프론트엔드만 띄웁니다. API 호출이 없으므로 `Run verification`은 잠기고(미리보기 모드), 다음 두 가지로 화면을 볼 수 있습니다.

1. 첫 화면 아래 **Explore example results** 카드(예시 데이터)
2. **Import result JSON** → `samples/` 폴더의 실제 Studio 실행 결과(set01 FAIL, set02 검토 필요, set03 PASS)를 내려받아 불러오기 → 결과 화면 → Next action → `View full draft →`로 후속 조치 보고서 미리보기·PDF 저장

`samples/` 결과는 공개 서식에 가상 값을 채운 데이터셋으로 실행한 출력이며, reason 안의 【†N】은 Studio 인용 표시입니다.
