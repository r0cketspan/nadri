# 17-voice — 테스트 설계 (test)

> spec.md와 짝. 절 번호 §n은 spec.md 기준. 작성 2026-11-21. 상태: 확정(2026-11-22).
> ① 자동 — A: pytest(OpenAI·ElevenLabs 목킹, DB는 04 테스트 컨테이너 마커 `db`, 실호출은 `integration`) / B: Vitest(녹음기·버튼, MediaRecorder 가짜) / C: Playwright(Chromium 가짜 마이크 파일 주입 + route 가짜 STT·TTS) ② HITL(실제 마이크·실제 재생 — Chrome webm, iOS Safari·PWA mp4).

---

## ① 자동 테스트

### 0. 실행
```bash
cd ~/code/myAgent/backend && uv run pytest -m "not integration"
cd ~/code/myAgent/backend && uv run pytest -m integration -k voice      # 실호출(키 필요, 비용 소량)
cd ~/code/myAgent/web && npm run test && npm run e2e -- voice
```
- 음성 샘플 파일(커밋, 각 수십 KB): `backend/tests/fixtures/audio/ko_hello.webm`(Chrome에서 녹음한 "경복궁 관람 시간 알려줘" 3초), `ko_hello.mp4`(iOS Safari 녹음, 같은 문장), `not_audio.txt`. 바이트 검사용 최소 바이트열은 테스트 안에서 만든다(`b"\x1a\x45\xdf\xa3" + …`, `b"\x00\x00\x00\x18ftypM4A " + …`). Playwright 가짜 마이크용 `web/e2e/fixtures/audio/ko_hello.wav`(Chromium `--use-file-for-fake-audio-capture`는 wav — **미확인**).
- 대역: `FakeStt(text | exc, model="gpt-transcribe")`(받은 바이트·형식 기록), `FakeTts(audio=b"ID3…" | exc, model="eleven_flash_v2_5")`(받은 글 기록), `httpx.MockTransport`(ElevenLabs), 가짜 `AsyncOpenAI`(`audio.transcriptions.create` 기록).

---

### A. pytest

#### A1. Provider·설정 — `tests/api/voice/test_providers.py`

| ID | 내용 | 기대 |
|---|---|---|
| U-VP-01 | `build_stt_provider(settings(STT_PROVIDER="openai"))` | `OpenAISttProvider`, `model == "gpt-transcribe"` |
| U-VP-02 | `Settings(STT_PROVIDER="faster_whisper")` | 설정 검증 오류(ValidationError) |
| U-VP-03 | `build_tts_provider`, 키·보이스 있음 | `ElevenLabsTtsProvider`, `model == "eleven_flash_v2_5"`, `media_type == "audio/mpeg"` |
| U-VP-04 | 키 또는 보이스 없음 | None + 경고 로그 1줄(키 값 없음) |
| U-VP-05 | 두 구현체가 Protocol을 만족(`isinstance` 검사용 `runtime_checkable` 대신 속성·메서드 존재 확인) | 통과 |
| U-VP-06 | `OpenAISttProvider.transcribe(b, "audio/webm")` (가짜 클라이언트) | `create(model="gpt-transcribe", file=("voice.webm", b, "audio/webm"), language="ko", response_format="text")`, 결과 strip |
| U-VP-07 | `"audio/mp4"` | 파일 이름 `voice.mp4` |
| U-VP-08 | 클라이언트가 `APITimeoutError` / `APIError` | `SttUnavailable`, 메시지에 바이트·글 없음 |
| U-VP-09 | `AsyncOpenAI` 생성 인자 | `max_retries=0`, `timeout=30.0` |
| U-VP-10 | ElevenLabs `synthesize("안녕")` (MockTransport 200 `audio/mpeg`) | 요청 `POST …/v1/text-to-speech/<voice>?output_format=mp3_44100_128`, 헤더 `xi-api-key`, 본문 `{"text":"안녕","model_id":"eleven_flash_v2_5"}`, 결과 바이트 |
| U-VP-11 | 401 / 429 / 500 / 시간 초과 / 200인데 `application/json` | `TtsUnavailable`, 로그에 키·글 없음 |

#### A2. 읽기용 글 변환 — `tests/api/voice/test_speech_text.py`

| ID | 입력 | 기대 |
|---|---|---|
| U-ST-01 | `"## 경복궁\n**09:00~18:00** 운영 (#126508)"` | `"경복궁\n09:00~18:00 운영"` |
| U-ST-02 | `"[홈페이지](https://www.royalpalace.go.kr/) 참고"` | `"홈페이지 참고"` |
| U-ST-03 | `"주소 https://x.org/a 에서"` | `"주소 에서"`(URL 제거 뒤 공백 정리) |
| U-ST-04 | `"![지도](https://x/y.png)사진"` | `"사진"` |
| U-ST-05 | 코드 블록 ```` ```\nprint(1)\n``` ```` + `"끝"` | `"끝"` |
| U-ST-06 | 표 `"|이름|시간|\n|---|---|\n|경복궁|9시|"` | 구분 줄 없음, `"이름 시간\n경복궁 9시"` |
| U-ST-07 | `"- 하나\n- 둘\n1. 셋"` | `"하나\n둘\n셋"` |
| U-ST-08 | `"<b>굵게</b>"` | `"굵게"` |
| U-ST-09 | 문장 여러 개 합계 3,000자 | 길이 ≤ 1500, 마지막 글자가 문장 끝(`.` `요` `다` 등) |
| U-ST-10 | 문장 끝 없는 1,600자 한 덩어리 | 정확히 1500자 |
| U-ST-11 | 코드 블록뿐 | `""` |

#### A3. 형식 검사 순수 함수 — `tests/api/voice/test_audio_checks.py`

| ID | 입력 | 기대 |
|---|---|---|
| U-AC-01 | `sniff_audio(b"\x1a\x45\xdf\xa3…")` | `"audio/webm"` |
| U-AC-02 | `b"\x00\x00\x00\x18ftypM4A …"` | `"audio/mp4"` |
| U-AC-03 | `b"RIFF…WAVE"`, `b"hello"`, `b""` | None |
| U-AC-04 | `base_mime("audio/webm;codecs=opus")`, `"Audio/MP4"`, `None` | `"audio/webm"`, `"audio/mp4"`, `""` |
| U-AC-05 | `stt_seconds(None)`, `(-5)`, `(0)`, `(2500)`, `(60000)`, `(999999)` | 60, 60, 1, 3, 60, 60 |

#### A4. API (마커 `db`) — `tests/api/voice/test_voice_api.py`

준비: 05 `app`·`client`·`login`·`post`, `app.state.stt = FakeStt("경복궁 관람 시간 알려줘")`, `app.state.tts = FakeTts()`, 09 `make_session(db_sf, alice.id, turns=1)` → assistant `a1`(본문 `"경복궁은 **09:00** 운영 (#126508) [홈](https://www.royalpalace.go.kr/)"`).

| ID | 요청 | 기대 |
|---|---|---|
| A-STT-01 | webm 바이트 + `audio/webm;codecs=opus` + `duration_ms=2500` | 200 `{"text":"경복궁 관람 시간 알려줘"}`, FakeStt가 받은 형식 `audio/webm`; `usage_events` 1행 kind stt·model gpt-transcribe·units 3·user_id alice·message_id NULL·cost_usd = 3/60×0.0045 |
| A-STT-02 | mp4 바이트 + `audio/mp4` | 200 |
| A-STT-03 | `audio/webm`인데 mp4 바이트 | 400 `unsupported_audio`, Stt 호출 0 |
| A-STT-04 | `audio/ogg` + ogg 바이트 / `text/plain` | 400 `unsupported_audio` |
| A-STT-05 | 0바이트 | 400 `invalid_audio` |
| A-STT-06 | 10MB + 1바이트 | 413 `audio_too_large`, Stt 호출 0 |
| A-STT-07 | 정확히 10MB(앞 바이트 webm) | 200 |
| A-STT-08 | `duration_ms` 없음 | units 60 |
| A-STT-09 | `duration_ms=abc` | 422 |
| A-STT-10 | 같은 분 11번째 | 429 `too_many_requests` + `Retry-After`, 키 `stt:user:<id>` |
| A-STT-11 | FakeStt가 `SttUnavailable` | 502 `stt_unavailable`, `usage_events` 0행 |
| A-STT-12 | CSRF 없음 / 로그인 없음 / pending | 403 `csrf_failed` / 401 / 403 `pending_approval` |
| A-STT-13 | 로그(caplog) | 전사 글·바이트 내용 없음, 바이트 수·형식만 |
| A-STT-14 | DB 전체 텍스트 덤프(09 `dump_text`) | `경복궁 관람 시간 알려줘` 없음(전사 글 저장 안 함) |
| A-TTS-01 | `{"message_id": a1}` | 200, `Content-Type: audio/mpeg`, `Cache-Control: no-store`, 본문 = FakeTts 오디오; FakeTts가 받은 글 `"경복궁은 09:00 운영 홈"`; `usage_events` kind tts·units = 그 글 길이·message_id a1·cost 0 |
| A-TTS-02 | bob의 메시지 / alice의 user 메시지 / 없는 id | 404 `message_not_found` |
| A-TTS-03 | `message_id: 0` / `"x"` | 422 |
| A-TTS-04 | 본문이 코드 블록뿐인 답변 | 400 `tts_empty`, Tts 호출 0 |
| A-TTS-05 | `app.state.tts = None` | 503 `tts_not_configured` |
| A-TTS-06 | FakeTts `TtsUnavailable` | 502 `tts_unavailable`, `usage_events` 0행 |
| A-TTS-07 | 같은 분 11번째 | 429 |
| A-TTS-08 | CSRF 없음 | 403 |

#### A5. 통합 (`@pytest.mark.integration`) — `tests/integration/test_voice_live.py`

| ID | 내용 | 통과 기준 / 기록 |
|---|---|---|
| I-V-01 | 실제 `OpenAISttProvider`로 `ko_hello.webm`·`ko_hello.mp4` | 두 형식 모두 "경복궁"이 들어간 한국어 글. `language`·`response_format="text"` 수용 여부, 응답에 길이·사용량 정보가 있는지(있으면 17-Q1대로 교체 기록), 소요 시간 |
| I-V-02 | 실제 ElevenLabs로 "경복궁은 오전 9시에 문을 열어요." | 200 `audio/mpeg`, 바이트 > 1KB, 응답 헤더에 글자 비용 정보가 있는지 기록, 소요 시간 |

---

### B. Vitest

#### B1. `tests/unit/recorder.test.ts` (§7.1) — 가짜 `MediaRecorder`·`getUserMedia`·시계·타이머(`vi.useFakeTimers`)

| ID | 준비 | 동작 | 기대 |
|---|---|---|---|
| V-RC-01 | 지원: webm;opus만 | `pickMimeType` | `"audio/webm;codecs=opus"` |
| V-RC-02 | 지원: mp4만(iOS 흉내) | 〃 | `"audio/mp4;codecs=mp4a.40.2"` 또는 `"audio/mp4"`(첫 지원 형식) |
| V-RC-03 | 아무것도 지원 안 함 | 〃 | null |
| V-RC-04 | 정상 | `start` → 시계 12초 → `stop` | 상태 idle→requesting→recording→stopping→idle, `durationMs 12000`, Blob 1개, 트랙 `stop()` 호출 |
| V-RC-05 | 정상 | `start` → 60초 경과 | 자동 종료, `onAutoStop` 1회(`durationMs 60000`), 트랙 정지 |
| V-RC-06 | `MediaRecorder` 없음 | `start` | `RecorderError("unsupported")`, getUserMedia 호출 0 |
| V-RC-07 | getUserMedia `NotAllowedError` | `start` | `RecorderError("denied")` |
| V-RC-08 | getUserMedia 기타 오류 | `start` | `"failed"` |
| V-RC-09 | 녹음 안 하는 중 | `stop` | `"not_recording"` |
| V-RC-10 | 녹음 중 | `cancel` | 트랙 정지, 결과 없음, 타이머 해제(60초 지나도 onAutoStop 없음) |

#### B2. `tests/unit/ptt-button.test.tsx` (§7.2)

| ID | 동작 | 기대 |
|---|---|---|
| V-PT-01 | MediaRecorder 미지원 브라우저 | 버튼 없음 |
| V-PT-02 | 누름 → 누름(5초) → STT 200 "경복궁" | `POST /api/stt` FormData에 `audio`(type `audio/webm`)·`duration_ms "5000"`, CSRF 헤더, `onText("경복궁")` |
| V-PT-03 | 녹음 중 표시 | "0:05 / 1:00"(1초마다 갱신), 버튼 "■ 끝내기" |
| V-PT-04 | 권한 거부 | "마이크 권한이 없어요…", 요청 0 |
| V-PT-05 | STT 502 | 서버 문구, `onText` 호출 0, idle |
| V-PT-06 | STT 200 `""` | "음성을 알아듣지 못했어요…" |
| V-PT-07 | 업로드 중 | 버튼 비활성 |

#### B3. `tests/unit/speaker-button.test.tsx` (§7.3) — 가짜 `HTMLAudioElement.play/pause`, `URL.createObjectURL`

| ID | 동작 | 기대 |
|---|---|---|
| V-SP-01 | 클릭 → TTS 200 | `POST /api/tts {"message_id":11}`, `play` 호출, 상태 playing(■) |
| V-SP-02 | 재생 중 같은 버튼 클릭 | `pause`, idle, URL revoke |
| V-SP-03 | 버튼 A 재생 중 버튼 B 클릭 | A 멈춤 → B 재생(공용 요소 1개) |
| V-SP-04 | 503 `tts_not_configured` | 서버 문구 3초 |
| V-SP-05 | `play()`가 `NotAllowedError` | "재생하지 못했어요. 다시 눌러 주세요." |
| V-SP-06 | `ended` 이벤트 | idle, revoke |

#### B4. `tests/unit/chat-view-voice.test.tsx`

| ID | 동작 | 기대 |
|---|---|---|
| V-CVV-01 | 입력창 빈 상태에서 전사 "경복궁" | 입력창 = "경복궁", 전송 요청 0(자동 전송 없음) |
| V-CVV-02 | 입력창 "내일" 상태에서 전사 "경복궁" | "내일 경복궁" |
| V-CVV-03 | `pass.txt` 완료 답변 | 👍/👎 옆에 🔊 |
| V-CVV-04 | 차단·오류 답변 | 🔊 없음 |

---

### C. Playwright — `web/e2e/voice.spec.ts`

`chromium` 프로젝트에 이 파일만 launch 옵션: `--use-fake-ui-for-media-stream`, `--use-fake-device-for-media-stream`, `--use-file-for-fake-audio-capture=<abs>/e2e/fixtures/audio/ko_hello.wav`. 로그인·세션은 15 route 가짜.

| ID | 시나리오 | 기대 |
|---|---|---|
| P-VO-01 | 녹음 버튼 → 3초 → 끝내기, `/api/stt` route가 요청을 검사하고 `{"text":"경복궁 관람 시간 알려줘"}` | 요청이 multipart, `audio` 파트 Content-Type `audio/webm`(Chromium), `duration_ms` 약 3000, 입력창에 글, 메시지 POST 없음 |
| P-VO-02 | 녹음 시작 후 61초 기다림(`page.clock`으로 시간 빨리 감기 — 가능하면, 아니면 `MAX_RECORD_MS`를 테스트 빌드에서 줄이지 않고 이 항목은 Vitest V-RC-05로 대신) | 자동 종료 → STT 요청 1회 |
| P-VO-03 | `pass.txt` 답변의 🔊, `/api/tts` route가 작은 mp3 픽스처 | 요청 본문 `{"message_id":11}`, 버튼이 ■로 바뀜(재생 시작). Chromium의 mp3 재생 지원은 **미확인** — 재생 실패면 이 항목은 "요청·상태 전이까지"로 기록 |
| P-VO-04 | 권한 없는 컨텍스트(가짜 UI 플래그 없이 `permissions: []`) | "마이크 권한이 없어요…" |

### 통과 기준
- A(`integration` 제외)·B·C 전부 통과. I-V-01·02는 G5 전 1회 실행 결과를 보고.

---

## ② HITL

전제: 17 적용 compose, 터널 주소 `<HOST>`(마이크는 HTTPS 필요 — localhost 제외), active 계정, `.env`에 `ELEVENLABS_API_KEY`·`ELEVENLABS_VOICE_ID`(17-Q8: 사용자가 보이스를 골라 넣음).

### HITL-1 음성 입력 (A13)
기기별로 같은 문장 3개를 말한다: ① "경복궁 관람 시간 알려줘" ② "제주 성산일출봉 가는 버스 있어?" ③ "다음 주 토요일 서울에서 하는 축제 알려줘".
1. **PC Chrome**(webm): 녹음 → 끝내기 → 입력창 글 확인 → 고쳐서 전송 → 답변.
2. **Android Chrome**(14 PWA 앱으로): 같은 절차, 마이크 권한 창이 뜨는지.
3. **iOS Safari 탭**(mp4): 같은 절차.
4. **iOS 홈 화면 PWA**(mp4): 같은 절차 — 마이크 권한·녹음 시작 여부가 핵심.
5. 60초 넘게 말하기(1개 기기) → 60초에 자동으로 멈추고 전사되는지.
6. 사용량: `docker compose exec postgres psql -U postgres -d nadri -c "select kind, model, units, cost_usd from usage_events where kind in ('stt','tts') order by id desc limit 10"`.

### HITL-2 음성 읽기 (FR-32)
1. 답변 옆 🔊 → 한국어로 읽히는지, 링크 주소·`(#126508)`·`**` 같은 기호를 읽지 않는지.
2. 읽는 중 ■ → 멈춤. 다른 답변 🔊 → 앞 재생 멈추고 새로.
3. iOS Safari·iOS PWA에서 🔊 → 소리가 나는지(무음 모드 스위치 끄고). 안 나면 화면 문구 기록 → spec §10 대안 사용자 확인.
4. 긴 답변(일정 짜기) → 중간쯤 문장 끝에서 끊기는지(1,500자).

### HITL 결과 보고 양식
| 항목 | PC Chrome | Android Chrome/PWA | iOS Safari | iOS PWA |
|---|---|---|---|---|
| 마이크 권한·녹음 시작 | | | | |
| 문장 ①②③ 전사 정확도(맞음/일부 틀림 — 틀린 단어) | | | | |
| 60초 자동 종료 | | | | |
| 🔊 재생·기호 안 읽음 | | | | |
| 재생 멈춤·전환 | | | | |
- `usage_events` stt·tts 행(units·비용), 업로드 형식(webm/mp4), A13 판정(통과/실패 + 실패 시 제안한 대안), 선택한 ElevenLabs 보이스 이름.
