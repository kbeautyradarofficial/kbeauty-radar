# K-Beauty Radar 자동화

매일 07:00(KST)에 K-뷰티 수출 뉴스를 모아 Claude가 **한국어/영어 브리프**를 쓰고,
무료 블로그(GitHub Pages)와 Threads에 올립니다. 매주 월요일 08:00에는 **주간 뉴스레터**(한/영)를
Kit으로 보냅니다. 모든 작업은 GitHub Actions(클라우드)에서 돌아가므로 PC를 켜둘 필요가 없습니다.

```
Google News RSS ─► Claude (한/영 작성 + 품질검사) ─► 블로그 글 파일 커밋 ─► GitHub Pages 사이트(한/영)
                                                  ├► Threads(한국어)
                                                  ├► output/ 기록 ─► 월요일 주간 뉴스레터(Kit 이메일)
                                                  └► 카카오톡 나에게 보내기(결과 알림)
```

**월 고정비: Claude API 사용료 약 $5~8 뿐** (GitHub, GitHub Pages, Kit 무료 플랜 모두 무료)

## 실행 모드 (`PUBLISH_MODE`)
| 모드 | 매일 브리프 | 주간 뉴스레터 | 언제 |
|---|---|---|---|
| `dry-run` | `output/`에 결과만 저장 | 결과만 저장 | 첫 테스트 |
| `draft` (기본값) | 블로그에만 게시 | Kit에 **초안** 저장 (직접 발송 버튼) | 처음 1~2주 품질 확인 |
| `auto` | 블로그 + Threads 게시 | 자동 발송 | 품질이 괜찮아진 뒤 |

---

## 설정 순서

> 🔒 API 키·토큰은 **채팅에 붙여넣지 말고** GitHub Secrets에만 넣으세요.

### 1. Anthropic API 키 (필수)
1. https://console.anthropic.com 가입 → **Billing**에서 크레딧 충전 (처음엔 $10이면 충분)
2. **Limits**에서 월 사용 한도를 $15 정도로 설정
3. **API Keys** → Create Key → 복사해 둠

### 2. GitHub 저장소 + 블로그 (필수)
1. GitHub → **New repository** → 이름 `kbeauty-radar`, **Public** 선택
   (무료 계정은 공개 저장소에서만 GitHub Pages가 됩니다. API 키는 Secrets에 들어가므로 공개돼도 안전합니다)
2. **uploading an existing file** → 이 폴더 안의 파일·폴더를 전부 드래그해 업로드
   (`.github` 폴더가 안 보이면 탐색기에서 "숨긴 항목 표시"를 켜세요)
3. **Settings → Pages** → Source: **Deploy from a branch** → Branch: `main`, 폴더: **`/docs`** → Save
   - 1~2분 후 `https://아이디.github.io/kbeauty-radar/` 에 사이트가 열립니다
4. **Settings → Secrets and variables → Actions**
   - **Secrets** 탭 → `ANTHROPIC_API_KEY` 추가
5. **Settings → Actions → General → Workflow permissions** → **Read and write permissions** 선택 → Save

### 3. 첫 테스트
1. **Actions** 탭 → 워크플로 활성화
2. **daily-brief → Run workflow → mode: `dry-run`** → 성공하면 `output/날짜.json` 에서 내용 확인
3. 다시 **mode: `draft`** 로 실행 → 2분 후 사이트에 한/영 글이 올라왔는지 확인

여기까지 하면 **매일 아침 블로그가 자동으로 갱신**됩니다.

### 4. Kit 뉴스레터 (주간 뉴스레터용)
1. https://kit.com 무료 가입 (구독자 1만 명까지 무료)
2. **Grow → Subscribers → 태그** 2개 생성: `ko`, `en`
   - 태그를 클릭했을 때 주소창 숫자가 태그 ID → 저장소 **Variables** 탭에 `KIT_TAG_KO`, `KIT_TAG_EN` 으로 추가
3. **Grow → Landing Pages & Forms** → 폼 2개(한국어/영어) 생성, 각각 구독 시 `ko` / `en` 태그가 붙도록 설정
   - 각 폼의 공유 URL → Variables에 `KIT_FORM_KO`, `KIT_FORM_EN` 추가 (블로그 글 하단 구독 버튼에 쓰임)
   - `docs/_config.yml` 의 `kit_form_ko / kit_form_en` 에도 같은 주소 입력 (사이트 첫 화면용)
4. **Settings → Developer → API Keys(V4)** → 키 생성 → Secrets에 `KIT_API_KEY` 추가
5. **weekly-newsletter → Run workflow → `draft`** 로 테스트 → Kit의 Broadcasts에 초안이 생기는지 확인
   - 무료 플랜에서 API가 막혀 있으면 실패 알림이 옵니다 → 그때 대안으로 바꿉니다

### 5. Threads 연동 (auto 모드 전 필요)
1. 인스타그램 앱 → 설정 → **프로페셔널 계정으로 전환**
2. https://developers.facebook.com → 개발자 등록 → **앱 만들기** → 사용 사례 **"Threads API 액세스"**
3. 권한 `threads_basic`, `threads_content_publish` 추가
4. **앱 역할 → Threads 테스터**에 본인 스레드 계정 추가 → 스레드 앱 설정 → 웹사이트 권한에서 초대 수락
5. **Graph API Explorer(Threads)** 에서 사용자 토큰 발급 → **장기 토큰(60일)** 으로 교환
6. `me?fields=id` 호출로 사용자 ID 확인
7. Secrets 추가: `THREADS_USER_ID`, `THREADS_ACCESS_TOKEN`
   - 토큰은 60일마다 갱신 필요 (만료 10일 전부터 카톡으로 알려줍니다)

### 6. 카카오톡 알림 (선택)
1. https://developers.kakao.com → 앱 생성 → **카카오 로그인** 활성화, 동의항목 **"카카오톡 메시지 전송"** 체크
2. Redirect URI에 `https://localhost` 등록
3. 브라우저에서 아래 주소 접속 후 로그인 → 주소창의 `code=` 값 복사
   `https://kauth.kakao.com/oauth/authorize?client_id=REST_API_KEY&redirect_uri=https://localhost&response_type=code&scope=talk_message`
4. 토큰 발급 (PowerShell):
   ```
   Invoke-RestMethod -Method Post https://kauth.kakao.com/oauth/token -Body @{grant_type="authorization_code"; client_id="REST_API_KEY"; redirect_uri="https://localhost"; code="복사한코드"}
   ```
5. Secrets 추가: `KAKAO_REST_API_KEY`, `KAKAO_REFRESH_TOKEN` (+ 클라이언트 시크릿을 켰다면 `KAKAO_CLIENT_SECRET`)
   - refresh token 유효기간은 약 2개월이라 주기적으로 다시 발급해야 합니다

### 7. 완전 자동으로 전환
**Variables** 탭 → `PUBLISH_MODE` = `auto` 추가. 이후 사람 손 없이 매일 발행됩니다.

---

## 설정값 요약
| 종류 | 이름 | 필수 |
|---|---|---|
| Secret | `ANTHROPIC_API_KEY` | ✅ |
| Secret | `KIT_API_KEY` | 뉴스레터 |
| Secret | `THREADS_USER_ID`, `THREADS_ACCESS_TOKEN` | Threads |
| Secret | `KAKAO_REST_API_KEY`, `KAKAO_REFRESH_TOKEN`, (`KAKAO_CLIENT_SECRET`) | 알림 |
| Variable | `PUBLISH_MODE` (`draft`/`auto`) | 선택 |
| Variable | `KIT_TAG_KO`, `KIT_TAG_EN`, `KIT_FORM_KO`, `KIT_FORM_EN` | 뉴스레터 |
| Variable | `SITE_URL` (개인 도메인 연결 시에만) | 선택 |

## 운영 메모
- **주 1회 15분 점검**: 카톡 알림, 사이트, Kit 통계(구독자·오픈율)만 보면 됩니다.
- 검색어 변경: `radar/config.py` 의 `QUERIES_KO / QUERIES_EN`
- 글 스타일 변경: `radar/generate.py` 의 `SYSTEM` 프롬프트
- 실패 시: 카톡 알림 + GitHub 실패 메일 → Actions 탭에서 로그 확인
- 기사 원문을 복사하지 않고 요약·링크만 합니다. AI 작성 고지 문구가 자동으로 붙습니다.
- 애드센스는 개인 도메인(연 1~2만 원)이 있어야 승인이 쉬우니, 글이 30개 이상 쌓인 뒤 진행합니다.
- LinkedIn 자동 게시는 2단계로 추가 예정 (`linkedin_en` 문구는 매일 생성되어 `output/`에 저장됨)
