# whs4-tiny-secondhand-platform
WHS 4기 Secure Coding 과제 - Tiny Second-hand Shopping Platform 개발

## 로컬 실행

```bash
# 1. 가상환경 생성 (conda 예시 -- venv도 무방)
conda create -n secure-coding python=3.11
conda activate secure-coding

# 2. 의존성 설치
pip install -r requirements.txt

# 3. 환경변수 설정
cp .env.example .env
# .env를 열어 SECRET_KEY를 실제 랜덤 값으로 채우기 (비워두면 프로세스마다
# 랜덤 생성되어 재시작 시 세션이 끊김 -- 로컬 개발 편의를 위해 채워두는 걸 권장)

# 4. 서버 실행 (Flask-SocketIO 앱이라 `flask run`이 아니라 이 명령 사용)
python app.py
# -> http://127.0.0.1:5000
```

관리자 계정이 필요하면 서버를 한 번이라도 실행해서(위 4번, DB 테이블이 생성됨) DB 파일이 만들어진 뒤 아래 "관리자 계정 생성" 절차를 따르세요.

외부에 HTTPS로 데모(ngrok 등)할 때는 [배포 시 주의사항](#배포-시-주의사항)을 먼저 확인하세요.

## 테스트 실행법

```bash
python3 -m pytest tests/ -q
```

- `pytest`, `Flask-WTF`의 `WTF_CSRF_ENABLED=True`를 켠 상태로(폼 전송 시 CSRF 토큰까지 실제로 검증) 매 테스트마다 임시 SQLite DB를 새로 만들고 종료 시 삭제합니다. 로컬 `instance/app.db`에는 영향이 없습니다.
- 회원가입/로그인/세션, 마이페이지, 상품 CRUD(+사진 검증), 상품 검색, 채팅(전체+1:1, Socket.IO), 신고+자동차단, 송금+모의충전, 관리자, 프로필 조회, 판매 상태 변경까지 기능별 테스트 파일로 나뉘어 있으며 총 129개입니다(`tests/test_*.py`).
- 특정 파일/케이스만 돌리려면 `python3 -m pytest tests/test_chat.py -v` 처럼 경로를 지정하세요.

## 배포 시 주의사항

- `SESSION_COOKIE_SECURE`는 기본값이 `true`(프로덕션 기준)입니다. 로컬 `http://localhost` 개발 환경에서만 `.env`에 `SESSION_COOKIE_SECURE=false`를 설정하세요. **ngrok 등으로 외부에 HTTPS로 배포/데모할 때는 이 오버라이드를 반드시 제거(또는 `true`로 설정)해야 세션 쿠키에 `Secure` 플래그가 적용됩니다.**
- `FLASK_DEBUG`도 기본값이 `false`(프로덕션 기준)입니다. Flask 디버그 모드가 켜져 있으면 에러 발생 시 스택 트레이스/소스코드/원격 코드 실행 콘솔까지 그대로 노출됩니다. 로컬에서 인터랙티브 디버깅이 필요할 때만 `.env`에 `FLASK_DEBUG=true`를 임시로 추가하고, 배포/데모 시에는 반드시 제거하세요.

## 관리자(admin) 계정 생성

회원가입 폼으로는 `role`을 절대 `admin`으로 만들 수 없습니다 (폼에 해당 필드 자체가 없고, 서버에서도 항상 기본값 `user`로 생성). 관리자 계정은 아래 두 방법 중 하나로만 만들 수 있습니다.

**방법 1: CLI 명령 (권장)**

```bash
flask create-admin <username> <password>
```

- 아이디가 이미 존재하면 해당 계정을 admin으로 승격
- 존재하지 않으면 admin 계정을 새로 생성

**방법 2: `flask shell`**

```bash
flask shell
```
```python
>>> from extensions import db
>>> from models import User, UserRole
>>> user = User.query.filter_by(username="기존아이디").first()
>>> user.role = UserRole.ADMIN
>>> db.session.commit()
```

## 보안 체크리스트 요약

과제 스펙(슬라이드 31p 형식) 30개 항목을 기능별로 대조한 결과입니다. 전 항목 확인 완료(✅), 미구현 항목 없음.

### 회원가입 및 프로필 관리
- ✅ 서버측 입력 검증(아이디/비밀번호 형식), Jinja2 autoescape로 XSS 1차 방어(`|safe` 미사용)
- ✅ 모든 POST 폼에 Flask-WTF CSRF 토큰
- ✅ bcrypt + 고유 salt로 비밀번호 해시 저장(평문/가역 암호화 없음)
- ✅ 세션 쿠키 `HttpOnly` + `Secure`(배포 기준 기본값, 로컬 개발 시에만 `.env`로 해제)
- ✅ 세션 30분 유휴 만료, 비밀번호 변경 시 현재 비밀번호 재확인
- ✅ 로그인 5회 실패 시 15분 계정 잠금
- ✅ `debug=False` 기본값, 에러 페이지에 스택 트레이스/DB 오류 미노출

### 상품 등록 및 관리
- ✅ 상품명/설명/가격 서버측 검증(길이 제한, 가격 0 이상)
- ✅ XSS 방어(autoescape), 등록/수정 모두 로그인 필요
- ✅ 소유자 확인(IDOR) — 수정/삭제/판매상태 변경 시 서버에서 `seller_id` 재검증, 위조 요청은 403
- ✅ 사진 업로드 — 확장자 화이트리스트 + Pillow로 실제 이미지 내용 검증(위장 실행파일 차단), 파일명 UUID 재생성(경로 조작 방지), 5MB 용량 제한, **등록 시 사진 필수**(수정 시엔 기존 사진 유지 가능)
- ✅ 판매 상태(sale_status) — 소유자만 변경 가능(서버측 재검증), enum(`on_sale`/`reserved`/`sold`) 외 임의 값은 폼 검증 단계에서 거부(SQLi 페이로드 포함 실제 테스트로 확인)

### 실시간 채팅 및 메시징
- ✅ 메시지 길이 1~1000자 DB 제약 + 서버측 검증, autoescape로 XSS 방어
- ✅ Socket 연결 시 인증 확인(미인증 연결 거부)
- ✅ 1:1 채팅방(상품별 ChatThread)은 서버가 실제 참여자(구매자/판매자)로부터만 room을 도출 — 클라이언트가 room/thread_id를 임의 지정해 다른 대화를 엿볼 수 없음(실제 공격 시도로 확인)
- ✅ 유저별 Rate limiting으로 도배 방지

### 안전 거래 및 신고
- ✅ 신고 대상/사유 서버측 검증 및 길이 제한, 로그인 필요
- ✅ 동일 유저의 동일 대상 중복 신고 차단, 신고 누적 시 상품 자동 차단·유저 자동 휴면(임계값 5회)

### 송금 기능
- ✅ 잔액 부족/음수/0 이하 송금 거부, 본인 송금 차단, 로그인 필요
- ✅ 송금 처리는 commit/rollback으로 원자적 처리
- ✅ 모의 충전 — 1회 100만원 한도, "실제 결제 미연동" UI 문구 명시
- ✅ 총 보유 잔액 상한(1,000만원) — 송금/충전 양쪽 서버측 검증 + DB CHECK 제약 이중 방어(정확히 상한에서 멈추고 그 이상은 거부되는지 실제 테스트로 확인)

### 관리자 기능
- ✅ `role` 컬럼 기반 서버측 권한 검증(프론트 숨김에 의존하지 않음), 비인가 접근 403
- ✅ 관리자 계정은 회원가입 폼으로 생성 불가(role 필드 자체가 없음), CLI(`flask create-admin`)/`flask shell`로만 생성
- ✅ 관리자의 강제 삭제/차단 해제 등 주요 작업은 `AdminActionLog`에 감사 로그로 기록

### 환경 및 배포 보안
- ✅ `SECRET_KEY` 등 민감 값은 `.env`로 분리, 하드코딩된 기본값 없음
- ✅ `.db`, `instance/`, 가상환경, `__pycache__`, 업로드 파일 등 `.gitignore` 반영

개발 중 자체 발견 후 수정한 항목(취약점/원인/수정 방식은 커밋 메시지에 상세 기록): `SECRET_KEY` 하드코딩 기본값 제거, 세션 쿠키 `Secure` 기본값 강화, 세션 유휴 만료 추가, 로그인 실패 잠금 추가, 파일 업로드 콘텐츠 검증 추가, 상품 등록 시 사진 미필수였던 폼 검증 버그 수정.
