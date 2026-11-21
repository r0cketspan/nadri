# 17-voice — STT·TTS (Provider 인터페이스) (spec)

> 하네스 Phase 4 산출물 (spec-writer, 작성 2026-11-21). 상태: **확정(2026-11-22)** — 확인 질문은 모두 추천안대로 결정(마지막 절 표). 브랜치 `feat/17-voice`, 의존 작업 11-quota-usage, 15-web-chat.
> 근거: [PL]=program_list.md(G4 승인본) §2 표·§3 "17-voice"·§4.3(faster-whisper·Drama 3 구현은 범위 밖) · [A]=architecture.md(G3 재승인본) §1(STT/TTS)·§2.1 `voice`·§3.2·§4(Audio·ElevenLabs 실패 시)·§6.1·§9 비밀값 표·ADR-11(STT는 OpenAI SDK 직접)·§12 A13 · [R]=requirements.md FR-30·31·32, NFR-06·43·50·51, D-12·13 · [S]=S2(`gpt-transcribe`)·S20(`eleven_flash_v2_5`, 기본 보이스 1개, 1회 글자 수 상한) · [TS]=TECH_STACK.md §8.1(`SttProvider` 시그니처)·§8.2.
> **이어받는 확정 spec**: [02](`UsageRecord` TypedDict·`nginx client_max_body_size 10m`) · [04](`USAGE_KINDS`에 `stt`·`tts`) · [05](`require_active`·`CurrentUser`·`get_db`·`get_now`·`ApiError`·`too_many`·`RateRule`·`allow`·키 형식 `stt:user:{user_id}`·CSRF) · [09](`chat_messages`·`chat_sessions` 소유 확인 방식) · [11](`record_usage`·`STT_PRICE_PER_MIN{"gpt-transcribe"}`·`tts` 비용 0·`units` = stt 초/tts 글자) · [13](`load_owned_assistant`·`message_not_found` — 병합 순서에 따라 공유, 13-Q4) · [14](`apiFetch`·FormData 처리) · [15](`ChatView` 입력창·`MessageBubble.actions`).
> **미확인** = 문서·공식 자료로 확인하지 못한 사실.

---

## 1. 작업 목표

- **STT**(FR-30·31): 녹음 버튼 → MediaRecorder(Chrome `webm/opus`, iOS Safari `mp4/aac`, 60초 자동 종료) → `POST /api/stt`(multipart, 10MB, MIME·파일 앞 바이트 재검사, 분당 제한) → `SttProvider`(OpenAI `gpt-transcribe`, `language=ko`) → 텍스트를 **입력창에 채움** → 사용자가 고쳐서 보냄(보낼 때 15·08 입력 검사).
- **TTS**(FR-32): 답변 옆 스피커 버튼 → `POST /api/tts {message_id}` → 본인 assistant **저장된 최종본**만 → 마크다운·링크·인용 표기 제거, 1,500자 상한 → `TtsProvider`(ElevenLabs `eleven_flash_v2_5`, `.env`의 보이스 1개) → `audio/mpeg` 응답 → 재생.
- **교체 지점**(NFR-50): `SttProvider`·`TtsProvider` Protocol + 설정값 `STT_PROVIDER`·`TTS_PROVIDER`로 구현체 선택. 이번 구현체는 `openai`·`elevenlabs` 하나씩.
- 사용량(NFR-43): `usage_events`에 `stt`(초)·`tts`(글자) 1행씩.

### 1.1 넣지 않는 것
| 빠지는 것 | 이유 |
|---|---|
| `faster_whisper` 구현체·`stt-gpu` 컨테이너, Drama 3 등 다른 TTS 구현체 | [R] §5·[PL] §4.3 — v1.1 이후, 인터페이스만 |
| 실시간(스트리밍) 음성 인식, 누르고 있는 동안만 녹음 | D-12 비실시간 Push-to-talk |
| 음성 Moderation | 오디오 미지원([A] §3.2) — 전사 글이 전송 때 검사됨 |
| 보이스·속도 선택 화면 | S20 기본 보이스 1개 |
| TTS 결과 저장·캐시 | 요구사항 없음 |
| 자동 읽어 주기(답변 끝나면 바로 재생) | FR-32는 버튼 |
| 녹음 파형 표시 | 요구사항 없음 — 경과 시간만 |
| ffmpeg 변환 | A13 실패 시 **사용자 확인 후**([PL] §3) |
| STT·TTS를 일일 50회 한도에서 차감 | FR-62는 "질의" 한도 — 차감 안 함 |

---

## 2. 생성·수정 파일

경로의 `nadri/`는 `backend/src/nadri/`.

| 파일 | 신규/수정 | 역할 |
|---|---|---|
| `nadri/api/voice/__init__.py`, `stt/__init__.py`, `tts/__init__.py` | 신규 | 빈 파일 |
| `nadri/api/voice/stt/base.py` | 신규 | `SttProvider` Protocol, `SttUnavailable`, `build_stt_provider` (§4.1) |
| `nadri/api/voice/stt/openai.py` | 신규 | `OpenAISttProvider`(OpenAI SDK, `gpt-transcribe`) (§4.2) |
| `nadri/api/voice/tts/base.py` | 신규 | `TtsProvider` Protocol, `TtsUnavailable`, `to_speech_text`, `build_tts_provider` (§5.1) |
| `nadri/api/voice/tts/elevenlabs.py` | 신규 | `ElevenLabsTtsProvider`(httpx 직접 호출) (§5.2) |
| `nadri/api/voice/router.py` | 신규 | `POST /api/stt`·`POST /api/tts`, 검사·제한·사용량 기록 (§6) |
| `nadri/core/config.py` | 수정 | 설정 (§3) |
| `nadri/agent/state.py` | 수정(02) | `UsageRecord.kind`에 `"stt"`, `"tts"` |
| `nadri/api/errors.py` | 수정(05) | 음성 오류 코드·문구 (§6.4) |
| `nadri/api/main.py` | 수정 | provider 생성(앱 상태), voice 라우터 등록 |
| `compose.yaml`, `.env.example` | 수정 | api에 `ELEVENLABS_API_KEY`·`ELEVENLABS_VOICE_ID`(+선택 `STT_PROVIDER`·`TTS_PROVIDER`) |
| `backend/pyproject.toml`, `uv.lock` | 수정 | `python-multipart`(FastAPI 파일 업로드에 필요 — 이미 있으면 그대로, **미확인**) |
| `web/lib/recorder.ts` | 신규 | 녹음기(포맷 선택·60초 자동 종료) (§7.1) |
| `web/components/chat/PttButton.tsx` | 신규 | 녹음 버튼 → 전사 → 입력창 채우기 (§7.2) |
| `web/components/chat/SpeakerButton.tsx` | 신규 | 답변 읽어 주기 (§7.3) |
| `web/lib/chat-api.ts` | 수정(15·16) | `transcribe`·`synthesize` 함수 (§7.4) |
| `web/components/chat/ChatView.tsx` | 수정(15·16) | 입력창 옆 `PttButton`, 답변 `actions`에 `SpeakerButton` |
| `backend/tests/...`, `web/tests/unit/*`, `web/e2e/voice.spec.ts`, `web/e2e/fixtures/audio/*` | 신규 | test.md |

> [PL] 파일 목록 밖: `__init__.py`들, `config.py`·`state.py`·`errors.py`·`main.py`·`compose.yaml`·`.env.example`·`pyproject.toml`(설정·등록·의존), `chat-api.ts`·`ChatView.tsx`(15 화면에 끼우기).
> 파일 이름 `stt/openai.py`: Python 3는 절대 import라 그 안의 `from openai import AsyncOpenAI`는 SDK를 가리킨다(같은 이름이지만 충돌 없음).

---

## 3. 설정 (환경변수)

| 이름 | 타입·기본값 | 용도 |
|---|---|---|
| `STT_PROVIDER` | `Literal["openai"] = "openai"` | 구현체 선택(NFR-50). 다른 값(`faster_whisper` 등)은 **기동 시 설정 오류**(구현체 없음) |
| `TTS_PROVIDER` | `Literal["elevenlabs"] = "elevenlabs"` | 〃 |
| `STT_MODEL` | `str = "gpt-transcribe"` | S2 |
| `STT_TIMEOUT_S` | `float = 30.0` | 전사 호출 제한 시간 |
| `TTS_MODEL` | `str = "eleven_flash_v2_5"` | S20 |
| `TTS_TIMEOUT_S` | `float = 30.0` | |
| `ELEVENLABS_API_KEY` | `SecretStr \| None = None` | 없으면 TTS 끔(§5.3) |
| `ELEVENLABS_VOICE_ID` | `str \| None = None` | 기본 보이스 1개(S20). 없으면 TTS 끔 |

상수(요구사항이 정한 값 — 코드 상수):
| 상수 | 위치 | 값 | 근거 |
|---|---|---|---|
| `MAX_AUDIO_BYTES` | `router.py` | `10 * 1024 * 1024` | FR-31 |
| `MAX_RECORD_S` | `router.py` | `60` | FR-31 (사용량 초 상한) |
| `ALLOWED_AUDIO` | `router.py` | `{"audio/webm": "webm", "audio/mp4": "mp4"}` | NFR-51 |
| `STT_RULE` | `router.py` | `RateRule(limit=10, window=timedelta(minutes=1))`, 키 `stt:user:{user_id}` | NFR-06(수치는 채팅과 같게 — 17-Q2) |
| `TTS_RULE` | `router.py` | `RateRule(limit=10, window=timedelta(minutes=1))`, 키 `tts:user:{user_id}` | ElevenLabs 크레딧 보호(17-Q3) |
| `TTS_MAX_CHARS` | `tts/base.py` | `1500` | [A] §3.2(가정), S20 "1회 글자 수 상한" |

`.env.example` 추가:
```
# ElevenLabs TTS — 없으면 음성 읽기 기능이 꺼진다
ELEVENLABS_API_KEY=
# 기본 보이스 1개(ElevenLabs Voice Library에서 한국어 샘플을 듣고 고른 voice_id)
ELEVENLABS_VOICE_ID=
```
`compose.yaml` api `environment`: `ELEVENLABS_API_KEY=${ELEVENLABS_API_KEY}`, `ELEVENLABS_VOICE_ID=${ELEVENLABS_VOICE_ID}`([A] §9 표 — api만).

---

## 4. STT

### 4.1 `stt/base.py`
```python
class SttProvider(Protocol):
    """음성 파일을 텍스트로 바꾸는 공통 인터페이스. 구현체는 STT_PROVIDER 설정으로 선택한다. ([TS] §8.1 그대로)"""
    model: str                                   # usage_events.model에 남길 모델 이름
    async def transcribe(self, audio: bytes, mime_type: str, language: str = "ko") -> str: ...

class SttUnavailable(Exception):
    """전사 서비스 오류·시간 초과. 메시지에 음성·전사 내용을 넣지 않는다."""

def build_stt_provider(settings: Settings) -> SttProvider:
    """STT_PROVIDER 값으로 구현체를 만든다. {"openai": OpenAISttProvider} 표에서 고른다."""
```
- 시그니처는 [TS] §8.1과 같다. 사용량에 필요한 모델 이름은 반환값을 바꾸지 않고 **속성 `model`** 로 둔다(17-Q1). `mime_type`은 라우터가 검사한 기본 형식(`audio/webm`·`audio/mp4`)만 넘긴다.

### 4.2 `stt/openai.py`
```python
class OpenAISttProvider:
    """OpenAI 전사 API(gpt-transcribe)로 한국어 음성을 글로 바꾼다. ADR-11 — OpenAI SDK 직접 호출."""
    def __init__(self, *, api_key: str, model: str, timeout_s: float, client: AsyncOpenAI | None = None) -> None: ...
    async def transcribe(self, audio: bytes, mime_type: str, language: str = "ko") -> str: ...
```
처리 순서:
1. 파일 이름 = `f"voice.{ALLOWED_AUDIO[mime_type]}"`(OpenAI는 확장자로 형식을 판단하는 것으로 알려짐 — **미확인**).
2. `await client.audio.transcriptions.create(model=self.model, file=(name, audio, mime_type), language=language, response_format="text")` — `AsyncOpenAI(api_key, timeout=timeout_s, max_retries=0)`.
3. 결과 문자열 `strip()` 반환(빈 문자열 가능).
4. `openai.APIError`·`APITimeoutError`·`httpx` 오류 → `SttUnavailable(클래스명)`.
- `gpt-transcribe`가 `language`·`response_format="text"`를 받는지, `webm`·`mp4`를 받는지 **미확인**(A13) — I-V-01에서 확인하고 다르면 이 절을 고친다.
- 키워드 힌트(`prompt`)는 넣지 않는다(요청 없음 — 관광지명 인식이 나쁘면 HITL 결과로 다시 제안).

---

## 5. TTS

### 5.1 `tts/base.py`
```python
class TtsProvider(Protocol):
    """글을 음성(mp3)으로 바꾸는 공통 인터페이스. 구현체는 TTS_PROVIDER 설정으로 선택한다."""
    model: str
    media_type: str                               # 응답 Content-Type, 예: "audio/mpeg"
    async def synthesize(self, text: str) -> bytes: ...

class TtsUnavailable(Exception):
    """음성 합성 서비스 오류·시간 초과."""

def to_speech_text(markdown: str, *, max_chars: int = TTS_MAX_CHARS) -> str:
    """답변 마크다운을 읽기용 글로 바꾼다(순수 함수). 아래 규칙 순서대로."""

def build_tts_provider(settings: Settings) -> TtsProvider | None:
    """TTS_PROVIDER 값으로 구현체를 만든다. 키·보이스가 없으면 None(TTS 끔 — 기동은 정상, 경고 로그 1줄)."""
```
`to_speech_text` 규칙:
1. 코드 블록(```` ``` ````로 감싼 부분) 통째로 제거, 인라인 코드는 백틱만 제거.
2. 이미지 `![alt](url)` → 제거. 링크 `[글](url)` → `글`.
3. 맨 URL(`https?://\S+`) → 제거.
4. 인용 표기 `(#숫자)` → 제거(02 출처 형식).
5. 줄 머리 `#`·`>`·목록 기호(`-`·`*`·`+`·`1.`) 제거, 강조 기호 `**`·`__`·`*`·`_`·`~~` 제거, 표의 `|`는 공백으로, 표 구분 줄(`---|---`) 제거.
6. 남은 HTML 태그 모양(`<…>`) 제거.
7. 공백·줄바꿈을 정리(줄마다 연속 공백 1개·앞뒤 공백 제거, 빈 줄 제거), 전체 앞뒤 공백 제거.
8. `max_chars` 초과면 앞 `max_chars`자 안에서 마지막 문장 끝(`.`·`?`·`!`·`요`·`다` 뒤 공백 또는 줄바꿈) 위치까지 자른다. 그런 위치가 앞 절반 안에 없으면 그냥 `max_chars`에서 자른다.

### 5.2 `tts/elevenlabs.py`
```python
class ElevenLabsTtsProvider:
    """ElevenLabs Text-to-Speech API를 httpx로 호출해 mp3를 받는다(SDK 의존 추가 없음)."""
    media_type = "audio/mpeg"
    def __init__(self, *, api_key: str, voice_id: str, model: str, timeout_s: float,
                 transport: httpx.AsyncBaseTransport | None = None) -> None: ...
    async def synthesize(self, text: str) -> bytes: ...
```
- 요청: `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128`, 헤더 `xi-api-key: <키>`, `Accept: audio/mpeg`, 본문 `{"text": text, "model_id": self.model}`. (경로·`output_format` 값은 공개 문서 기준, **미확인** — I-V-02에서 확인.)
- 200이고 Content-Type이 `audio/mpeg` → 본문 바이트. 그 밖(4xx·5xx·시간 초과·다른 형식) → `TtsUnavailable(상태 코드 또는 클래스명)`. 오류 본문·키·텍스트는 로그에 넣지 않는다.
- 스트리밍 엔드포인트 대신 한 번에 받는다(17-Q4): 1,500자 상한이라 크기·지연이 작고 오류를 응답 시작 전에 알 수 있다.

### 5.3 키가 없을 때
- `build_tts_provider`가 None → `app.state.tts = None`. `/api/tts` → 503 `tts_not_configured`. api 기동은 정상(06 메일 설정 없음과 같은 방식).

---

## 6. API (`api/voice/router.py`)

모두 `require_active`, POST → 05 CSRF 미들웨어 적용. 오류 본문 05 형식.

### 6.1 엔드포인트
| 메서드·경로 | 요청 | 성공 | 실패 |
|---|---|---|---|
| `POST /api/stt` | multipart: `audio`(파일, 필수), `duration_ms`(정수 글, 선택) | 200 `{"text": str}` | 400 `invalid_audio`·`unsupported_audio` / 413 `audio_too_large` / 429 `too_many_requests` / 502 `stt_unavailable` / 401·403 |
| `POST /api/tts` | JSON `{"message_id": int(≥1, ≤2^63−1)}` | 200 `audio/mpeg` 바이트, `Cache-Control: no-store` | 404 `message_not_found` / 400 `tts_empty` / 429 / 502 `tts_unavailable` / 503 `tts_not_configured` / 422 / 401·403 |

```python
@router.post("/api/stt")
async def stt(request: Request, audio: UploadFile = File(...), duration_ms: int | None = Form(None),
              cu: CurrentUser = Depends(require_active), db: AsyncSession = Depends(get_db),
              now: datetime = Depends(get_now)) -> dict: ...

class TtsIn(BaseModel):
    message_id: int = Field(ge=1, le=2**63 - 1)

@router.post("/api/tts")
async def tts(body: TtsIn, request: Request, cu: CurrentUser = Depends(require_active),
              db: AsyncSession = Depends(get_db), now: datetime = Depends(get_now)) -> Response: ...

def sniff_audio(data: bytes) -> str | None:
    """파일 앞 바이트로 형식을 판단한다: 1A 45 DF A3(EBML) → 'audio/webm', 4~8바이트가 b'ftyp' → 'audio/mp4', 그 밖 None."""
def base_mime(content_type: str | None) -> str:
    """'audio/webm;codecs=opus' → 'audio/webm' (소문자, 매개변수 제거)."""
def stt_seconds(duration_ms: int | None) -> int:
    """사용량 초: None·음수·이상값이면 MAX_RECORD_S, 아니면 ceil(min(duration_ms, 60000)/1000), 최소 1."""
```

### 6.2 STT 처리 순서
1. `allow(db, f"stt:user:{uid}", STT_RULE, now)` → 커밋 → 거부면 429 `too_many_requests`(+`Retry-After`).
2. `data = await audio.read(MAX_AUDIO_BYTES + 1)` → `len > MAX_AUDIO_BYTES`면 413 `audio_too_large`. `len == 0`이면 400 `invalid_audio`.
3. `declared = base_mime(audio.content_type)`; `declared not in ALLOWED_AUDIO` 또는 `sniff_audio(data) != declared` → 400 `unsupported_audio`.
4. `t0`; `text = await request.app.state.stt.transcribe(data, declared, "ko")`. `SttUnavailable` → 502 `stt_unavailable`(사용량 기록 없음 — 11 "성공한 호출만").
5. 성공 → `record_usage(db, [UsageRecord(kind="stt", model=stt.model, input_tokens=None, cached_tokens=None, cache_write_tokens=None, output_tokens=None, units=stt_seconds(duration_ms), ms=경과)], user_id=uid, message_id=None)` → 커밋.
6. 200 `{"text": text}`.
- **음성·전사 글은 저장·로그하지 않는다**(전사 글에 개인정보가 있을 수 있음 — 가리기는 전송 때 08이 함). 로그 1줄: `stt` 이벤트 이름, 바이트 수, 형식, 소요 ms, 글자 수만.
- 비용 기준 초는 브라우저가 보낸 `duration_ms`(60초 상한)로 셈(17-Q1) — 응답에 길이 정보가 있는지 **미확인**(I-V-01에서 응답 `usage` 확인, 있으면 그 값으로 바꿈).

### 6.3 TTS 처리 순서
1. `app.state.tts is None` → 503 `tts_not_configured`.
2. `allow(db, f"tts:user:{uid}", TTS_RULE, now)` → 커밋 → 거부면 429.
3. 본인 assistant 메시지 확인: 13의 `load_owned_assistant(db, message_id, uid)`와 같은 조건(`chat_messages ⋈ chat_sessions`, `role='assistant'`, `user_id`) + `content` 조회 → 없으면 404 `message_not_found`.
4. `speech = to_speech_text(content)` → 빈 문자열이면 400 `tts_empty`.
5. `audio = await tts.synthesize(speech)`. `TtsUnavailable` → 502 `tts_unavailable`.
6. `record_usage(…, kind="tts", model=tts.model, units=len(speech), message_id=message_id)` → 커밋.
7. `Response(content=audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})`.
- 읽는 글은 **DB에 저장된 최종본**(링크 강등·좌표 지우기 끝난 본문, 09) — 화면에 잠깐 보였던 초안이 아니다.

### 6.4 사용자에게 보이는 문구 (`errors.py`에 추가)
| code | HTTP | 상수 | 문구 |
|---|---|---|---|
| `invalid_audio` | 400 | `MSG_INVALID_AUDIO` | 녹음된 소리가 없어요. 다시 녹음해 주세요. |
| `unsupported_audio` | 400 | `MSG_UNSUPPORTED_AUDIO` | 지원하지 않는 녹음 형식이에요. 다른 브라우저로 시도하거나 직접 입력해 주세요. |
| `audio_too_large` | 413 | `MSG_AUDIO_TOO_LARGE` | 녹음 파일이 너무 커요. 60초 안으로 다시 녹음해 주세요. |
| `stt_unavailable` | 502 | `MSG_STT_UNAVAILABLE` | 음성을 글로 바꾸지 못했어요. 다시 시도하거나 직접 입력해 주세요. |
| `message_not_found` | 404 | `MSG_MESSAGE_NOT_FOUND` | (13과 같은 상수 — 13-Q4) 답변을 찾을 수 없어요. 삭제된 대화일 수 있어요. |
| `tts_empty` | 400 | `MSG_TTS_EMPTY` | 읽어 줄 내용이 없어요. |
| `tts_unavailable` | 502 | `MSG_TTS_UNAVAILABLE` | 음성을 만들지 못했어요. 잠시 후 다시 시도해 주세요. |
| `tts_not_configured` | 503 | `MSG_TTS_NOT_CONFIGURED` | 음성 읽기 기능이 아직 설정되지 않았어요. |

---

## 7. 화면

### 7.1 녹음기 (`web/lib/recorder.ts`)
```ts
export const MAX_RECORD_MS = 60_000;
export const MIME_CANDIDATES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4;codecs=mp4a.40.2", "audio/mp4"] as const;

/** 이 브라우저가 녹음할 수 있는 첫 형식(없으면 null). */
export function pickMimeType(isSupported?: (t: string) => boolean): string | null;

export type RecordResult = { blob: Blob; mimeType: string; durationMs: number };
export type RecorderDeps = { getUserMedia: (c: MediaStreamConstraints) => Promise<MediaStream>;
  MediaRecorderCtor: typeof MediaRecorder; now: () => number; setTimeout: typeof setTimeout; clearTimeout: typeof clearTimeout };

/**
 * Push-to-talk 녹음기. start → (stop 또는 60초) → RecordResult.
 * 녹음이 끝나면 마이크 트랙을 모두 멈춰 브라우저 마이크 표시를 끈다.
 */
export class PushToTalkRecorder {
  constructor(opts?: { deps?: Partial<RecorderDeps>; onAutoStop?: (r: RecordResult) => void });
  readonly state: "idle" | "requesting" | "recording" | "stopping";
  /** 마이크 권한을 받고 녹음을 시작한다. @throws RecorderError("unsupported" | "denied" | "failed") */
  start(): Promise<void>;
  /** 녹음을 끝내고 결과를 돌려준다(recording이 아니면 RecorderError("not_recording")). */
  stop(): Promise<RecordResult>;
  /** 결과 없이 버린다(화면을 떠날 때). */
  cancel(): void;
}
export class RecorderError extends Error { constructor(public readonly reason: "unsupported" | "denied" | "failed" | "not_recording") }
```
- `start`: `MediaRecorder`가 없거나 `pickMimeType()`이 null → `unsupported`. `getUserMedia({audio: true})` 실패 → `NotAllowedError`면 `denied`, 그 밖 `failed`. `new MediaRecorder(stream, {mimeType})` → `start()`(타임슬라이스 없음 — 끝날 때 조각 1개 이상) → `MAX_RECORD_MS` 타이머.
- 타이머 만료 → 내부 `stop()` → `onAutoStop(result)`.
- `stop`: `ondataavailable` 조각 모아 `Blob(type = recorder.mimeType || 고른 형식)`, `durationMs = now() − 시작`, 트랙 `stop()`, 타이머 해제.
- 업로드 형식은 `blob.type`의 기본 형식(`audio/webm`·`audio/mp4`). 서버가 둘만 받는다.

### 7.2 `PttButton`
```tsx
/**
 * 입력창 옆 녹음 버튼. 눌러서 시작, 다시 눌러서 끝(또는 60초 자동 종료) → 서버 전사 → onText로 글을 넘긴다.
 * @param onText - 전사 글(입력창에 덧붙임 — 사용자가 고친 뒤 직접 전송)
 */
export function PttButton(props: { onText: (text: string) => void }): JSX.Element | null;
```
상태 전이:
```
idle ─누름─▶ requesting ─권한 OK─▶ recording(경과 "0:12 / 1:00") ─누름 또는 60초─▶ uploading ─200─▶ idle(onText)
  │              └─denied/unsupported/failed─▶ idle + 안내 글
  └ (MediaRecorder·형식 미지원 브라우저면 버튼 자체를 그리지 않음)
uploading ─ApiError─▶ idle + 서버 문구 / 200인데 text=="" ─▶ idle + "음성을 알아듣지 못했어요. 다시 녹음하거나 직접 입력해 주세요."
```
- 업로드: `FormData{ audio: File([blob], "voice.webm"|"voice.mp4", {type}), duration_ms: String(durationMs) }` → `transcribe()`.
- 안내 글: `denied` → "마이크 권한이 없어요. 브라우저 설정에서 허용해 주세요." / `failed` → "마이크를 열지 못했어요."
- 녹음 중 화면을 떠나면 `cancel()`. 녹음 중에는 버튼이 빨간 "■ 끝내기".
- 전사 글 처리(`ChatView`): 입력창이 비었으면 그 글로, 아니면 끝에 공백 하나 + 글. **자동 전송하지 않는다**(FR-30). 1,000자 넘으면 15 `maxLength` 규칙대로 잘림.
- 답변 스트리밍 중에도 녹음은 가능(입력창만 채움).

### 7.3 `SpeakerButton`
```tsx
/** 저장된 답변을 읽어 준다. 한 번에 하나만 재생(다른 버튼을 누르면 앞 재생을 멈춤). */
export function SpeakerButton(props: { messageId: number }): JSX.Element;
```
- 클릭 처리 순서:
  1. 모듈 공용 `HTMLAudioElement` 하나를 첫 클릭 때 만들고 이후 계속 재사용한다. iOS Safari는 사용자 동작 밖(비동기 응답 뒤)에서 시작한 재생을 막을 수 있는 것으로 알려져 있다(**미확인**) — HITL-2에서 확인하고 막히면 §10 대안(`<audio controls>`로 사용자가 직접 재생).
  2. 재생 중인 같은 버튼 → 멈춤(`pause`, `currentTime=0`) → 끝.
  3. 상태 `loading` → `synthesize(messageId)`(Blob) → `URL.createObjectURL` → `audio.src` → `await audio.play()` → 상태 `playing`.
  4. `ended`·멈춤 → `URL.revokeObjectURL`, 상태 `idle`.
  5. `ApiError` → 버튼 아래 작은 글로 서버 문구(3초), `play()` 거부(`NotAllowedError`) → "재생하지 못했어요. 다시 눌러 주세요."
- 표시: 🔊(idle) / 빙글(loading) / ■(playing). `aria-label` "답변 읽어 주기"/"읽기 멈추기".
- `ChatView`: 답변 `actions`에 `<SpeakerButton messageId={m.id} />`를 16의 `FeedbackButtons` 옆에(같은 조건 — `phase=="done"`, `id != null`).

### 7.4 API 함수 (`web/lib/chat-api.ts`에 추가)
```ts
/** POST /api/stt (multipart) → 전사 글. */
export function transcribe(blob: Blob, durationMs: number): Promise<string>;
/** POST /api/tts {message_id} → mp3 Blob. */
export function synthesize(messageId: number): Promise<Blob>;
```

---

## 8. 엣지케이스

| 상황 | 동작 |
|---|---|
| 60초 넘게 녹음 | 60초에 자동 종료 → 바로 전사 |
| 0.3초 녹음(거의 빈 파일) | 서버로 보냄 → 빈 글이면 "알아듣지 못했어요" |
| 0바이트 업로드 | 400 `invalid_audio` |
| `Content-Type: audio/webm`인데 내용이 mp4 / wav / 텍스트 | 400 `unsupported_audio` |
| `audio/webm;codecs=opus` | 기본 형식 `audio/webm`로 판단 — 통과 |
| `audio/ogg`(Firefox 일부) | 400 `unsupported_audio`(NFR-51은 두 형식 — Firefox는 webm을 먼저 고르므로 대개 해당 없음) |
| 10MB + 1바이트 | 413(api). 그보다 크면 nginx가 먼저 413(HTML) → 화면은 14 `server_error` 문구 |
| `duration_ms` 없음·`abc`·음수·`999999` | 없음·음수·이상값 → 60초로 셈(비용 과대 쪽), `abc` → 422(Form 정수 검사) |
| 분당 11번째 STT | 429 |
| OpenAI 장애·30초 초과 | 502 `stt_unavailable`, 사용량 기록 없음 |
| 마이크 권한 거부 | 안내 글, 버튼 그대로 |
| iOS PWA에서 마이크 | A13 HITL로 확인(**미확인**) |
| 남의 메시지·user 메시지 TTS | 404 |
| `security_replaced` 답변 TTS | 고정 안전 문구를 읽음 |
| 답변이 표·코드뿐 | 코드 제거 후 남은 글, 비면 400 `tts_empty` |
| 3,000자 답변 | 1,500자 안 마지막 문장까지 |
| ElevenLabs 키·보이스 없음 | 503 `tts_not_configured` |
| ElevenLabs 401·429·5xx·시간 초과 | 502 `tts_unavailable`, 사용량 기록 없음 |
| 재생 중 다른 답변 🔊 | 앞 재생 멈추고 새 재생 |
| `STT_PROVIDER=faster_whisper` | api 기동 실패(설정 검증 — 구현체 없음, 한국어 메시지) |

---

## 9. 앞 작업과 달라지는 점 · 앞 작업 테스트 수정

| # | 내용 | 대상 | 처리 |
|---|---|---|---|
| 1 | `UsageRecord.kind`에 `stt`·`tts` | 11 U-US(Literal ⊆ `USAGE_KINDS` 대조) | 그대로 통과(04에 이미 있음) |
| 2 | 앱 상태에 `stt`·`tts` provider | 05·09 등 `create_app`으로 앱을 만드는 테스트 | 수정 없음(provider 생성은 네트워크 호출 없음, TTS 키 없으면 None) |
| 3 | `errors.py` 코드 추가 | 05 문구 목록 테스트(있으면) | 목록에 추가 |
| 4 | 답변 `actions`에 스피커 버튼 | 15·16 컴포넌트 테스트(actions 내용을 정확히 비교하면) | 기대에 스피커 버튼 추가 |
| 5 | `message_not_found`·소유 확인 | 13 | 13이 먼저 병합됐으면 재사용(중복 정의 금지) |

상위 문서와의 차이(구현 판단):
1. `SttProvider`·`TtsProvider`에 속성 `model`(사용량 기록용) — [TS] §8.1 메서드 시그니처는 그대로(17-Q1).
2. STT 사용량 초는 브라우저가 보낸 녹음 길이(60초 상한) — 전사 응답에 길이가 있는지 **미확인**(17-Q1).
3. TTS에도 분당 10회 제한(17-Q3) — NFR-06 목록엔 없음.
4. TTS는 스트리밍 대신 한 번에 받아 돌려줌(17-Q4).
5. ElevenLabs는 SDK 대신 httpx 직접(의존성 최소).

---

## 10. 가정 판정 — A13

| 항목 | 내용 |
|---|---|
| 가정 | `gpt-transcribe`가 Chrome `webm/opus`와 iOS Safari `mp4/aac`를 모두 전사하고, iOS 홈 화면 PWA에서 마이크(getUserMedia)가 동작 |
| 확인 | I-V-01(두 형식 샘플 파일 실호출) + HITL-1(Chrome PC·Android Chrome·iOS Safari 탭·iOS PWA 실제 녹음) |
| 통과 | 두 형식 모두 한국어 문장이 의미 있게 전사, iOS PWA에서 녹음 시작·종료·전사 성공 |
| 실패 시 | 형식 하나가 안 되면 **멈추고 사용자에게**: 대안 ffmpeg 변환(api 이미지에 ffmpeg 추가 — 이미지 크기·의존 증가). iOS PWA만 안 되면 "iOS는 Safari 탭에서만 음성 입력" 기록 후 사용자 확인. TTS 재생이 iOS에서 막히면 `<audio controls>`를 보여 사용자가 직접 재생하는 방식으로(코드 소폭) |
| 결과 | (구현 시 기록 + `PROGRESS.md` 결정 로그) |

---

## 11. 완료 기준 (DoD)

1. pytest(`cd ~/code/myAgent/backend && uv run pytest -m "not integration"`) 통과: Provider 선택, 크기·MIME·앞 바이트 거부, 분당 제한, 타인 메시지 TTS 거부, 읽기용 글 변환, 사용량 기록(목킹).
2. Vitest: 녹음기 상태·60초 자동 종료·형식 선택, 버튼 상태. Playwright: Chromium 가짜 마이크 파일로 녹음 → (route 가짜 STT) → 입력창 채움, 스피커 → (route 가짜 TTS) 재생 상태.
3. I-V-01·02 실호출 결과 기록, HITL-1·2 결과 보고, A13 판정 기록.
4. 음성·전사 글이 DB·로그에 남지 않음(테스트).
5. `faster_whisper`·Drama 3 구현체 없음(인터페이스·선택 표만).
6. 한국어 docstring·JSDoc·단계 주석([CL]). 커밋 `feat/17-voice`, `[Feat] …` + 작업 목록 + `Author:`, AI 공동작성 표기 없음. `dev` 병합은 G5 후. `PROGRESS.md` 갱신.

---

## 12. 확인 질문

| # | 질문 | 추천안 | 대안 |
|---|---|---|---|
| 17-Q1 | [TS] §8.1 `transcribe(...) -> str`는 사용량(모델·길이)을 돌려주지 않는데 11은 STT를 "초" 단위로 기록한다. 어떻게 셀까 | **결정(2026-11-22): 추천안대로** — **시그니처는 그대로, provider에 `model` 속성 + 초는 브라우저가 보낸 녹음 길이(60초 상한, 없으면 60초로)** — 비용 기록용이라 근사 허용, 전사 응답에 길이가 있으면(I-V-01) 그 값으로 바꿈 | 시그니처를 `-> SttResult(text, seconds, model)`로 바꿈([TS] 문서 수정) / 서버가 파일을 해석해 길이 계산(ffmpeg 등 의존 추가) |
| 17-Q2 | STT 분당 제한 수치(NFR-06은 대상만, 수치 없음) | **결정(2026-11-22): 추천안대로** — **분당 10회**(채팅과 같게) | 분당 5회 |
| 17-Q3 | TTS에도 요청 제한을 둘까(NFR-06 목록엔 없음) | **결정(2026-11-22): 추천안대로** — **분당 10회**(ElevenLabs 크레딧 보호, 같은 `ratelimit` 재사용 1줄) | 제한 없음(요구사항 그대로) |
| 17-Q4 | TTS를 스트리밍으로 흘릴까 | **결정(2026-11-22): 추천안대로** — **한 번에 받아 응답**(1,500자 상한이라 작음, 오류를 응답 전에 알 수 있음) | ElevenLabs 스트리밍 엔드포인트를 그대로 중계(첫 소리가 빠름, 중간 오류 처리 어려움) |
| 17-Q5 | ElevenLabs 키가 없을 때 | **결정(2026-11-22): 추천안대로** — **api는 정상 기동, `/api/tts`만 503 + 화면 문구**(06 메일과 같은 방식) | 기동 실패 |
| 17-Q6 | 녹음 방식 | **결정(2026-11-22): 추천안대로** — **눌러서 시작·다시 눌러서 끝(토글)** — 모바일에서 누르고 있기 불편 | 누르고 있는 동안만 녹음 |
| 17-Q7 | 전사 글을 입력창에 어떻게 넣을까 | **결정(2026-11-22): 추천안대로** — **비었으면 그 글로, 있으면 끝에 덧붙임**(자동 전송 없음 — FR-30) | 항상 입력창 내용을 바꿔 씀 |
| 17-Q8 | ElevenLabs 보이스 고르기 | **결정(2026-11-22): 추천안대로** — **사용자가 Voice Library에서 한국어 샘플 2~3개를 듣고 `ELEVENLABS_VOICE_ID`에 넣음**(S20 그대로, HITL-2 전) | 에이전트가 기본 보이스 하나를 골라 둠 |
