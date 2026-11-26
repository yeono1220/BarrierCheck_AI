# Cloudflare Worker 프록시 (API 키 숨기기)

GitHub Pages 데모가 **키 입력 없이** 실시간으로 돌게 하는 중계 서버입니다. API 키는 Cloudflare의 비밀 변수에만 있고, 이 저장소나 페이지 코드에는 없습니다.

## 설정 (약 5분)

1. https://dash.cloudflare.com 가입/로그인 → **Workers & Pages → Create → Create Worker** → 이름 예: `barriercheck-proxy` → Deploy
2. **Edit code** → 기본 코드를 지우고 `worker.js` 내용을 붙여 넣기 → **Deploy**
3. Worker → **Settings → Variables and Secrets** 에서 추가

| 이름 | 종류 | 값 |
|---|---|---|
| `UPSTAGE_API_KEY` | **Secret** | 워크플로가 있는 조직의 Upstage API 키 |
| `PROJECT_ID` | Text | `proj_...` (workflow_config.json의 project_id) |
| `WORKFLOW_ID` | Text | `agt_...` (workflow_config.json의 workflow_id) |
| `CONFIG_ID` | Text | `4` 같은 설정 번호 |
| `ALLOWED_ORIGIN` | Text | `https://yeono1220.github.io` |
| `LABEL` | Text (선택) | 화면에 보일 이름 |
| `ACCESS_CODE` | Secret (선택) | 지금 버전 페이지는 이 값을 보내지 않으므로 비워 두세요 |

4. Worker 주소(예: `https://barriercheck-proxy.<계정>.workers.dev`)를 `gh-pages` 브랜치의 `workflow_config.json` → `"proxy_url"`에 넣고 커밋 → 1분 뒤 Pages 새로고침 → 키 입력 상자 없이 바로 `Run verification` 가능.

## 막아 둔 것

- `ALLOWED_ORIGIN`(우리 Pages)에서 온 브라우저 요청만 통과. 다른 사이트에서 부르면 403.
- 통과 경로는 업로드·상태 조회·작업 생성·결과 조회 4개뿐. 작업 생성 때 워크플로·설정 번호는 Worker가 고정(브라우저가 바꿀 수 없음).
- 업로드 30 MB 제한.

## 한계

- Origin 검사는 브라우저 기준입니다. 주소를 아는 사람이 스크립트로 Origin을 꾸며 부르면 막지 못합니다. 대회가 끝나면 Worker를 지우거나 키를 재발급하세요.
- 실행마다 키의 크레딧이 쓰입니다.
