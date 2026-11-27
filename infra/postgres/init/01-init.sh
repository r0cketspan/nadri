#!/bin/bash
# PostgreSQL 첫 기동 초기화 — 롤 3개·DB 2개·vector 확장·접속 권한.
# 빈 pg-data 볼륨에서 처음 기동할 때만 실행된다. 나중에 .env 비밀번호를 바꿔도 반영되지 않는다
# (바꾸려면 ALTER ROLE 또는 볼륨 재생성).
# 테이블 단위 권한(nadri_tools의 SELECT)은 테이블이 생긴 뒤 Alembic 0001에서 부여한다.
set -euo pipefail

# 1) 필수 비밀번호 확인 — 하나라도 비면 즉시 실패
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD가 필요합니다}"
: "${TOOLS_DB_PASSWORD:?TOOLS_DB_PASSWORD가 필요합니다}"
: "${LIGHTRAG_DB_PASSWORD:?LIGHTRAG_DB_PASSWORD가 필요합니다}"

# 2) 비밀번호는 psql 변수로 넘기고 SQL 안에서 :'변수'로 인용한다(셸 문자열 조립 없음)
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  -v app_pw="$APP_DB_PASSWORD" -v tools_pw="$TOOLS_DB_PASSWORD" -v lightrag_pw="$LIGHTRAG_DB_PASSWORD" <<'SQL'
-- 3) 롤: 로그인만 가능(superuser·createdb·createrole 아님)
CREATE ROLE nadri_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_pw';
CREATE ROLE nadri_tools LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'tools_pw';
CREATE ROLE lightrag LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'lightrag_pw';

-- 4) DB: 앱용 nadri, LightRAG용 lightrag
CREATE DATABASE nadri OWNER nadri_app;
CREATE DATABASE lightrag OWNER lightrag;

-- 5) 접속 권한: PUBLIC 회수 후 필요한 롤만
REVOKE CONNECT ON DATABASE nadri FROM PUBLIC;
REVOKE CONNECT ON DATABASE lightrag FROM PUBLIC;
GRANT CONNECT ON DATABASE nadri TO nadri_app, nadri_tools;
GRANT CONNECT ON DATABASE lightrag TO lightrag;

-- 6) vector 확장(superuser로 각 DB에) + 7) nadri 스키마 사용 권한
\connect nadri
CREATE EXTENSION IF NOT EXISTS vector;
GRANT USAGE ON SCHEMA public TO nadri_tools;

\connect lightrag
CREATE EXTENSION IF NOT EXISTS vector;
SQL
