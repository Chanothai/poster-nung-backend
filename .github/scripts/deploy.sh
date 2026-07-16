#!/usr/bin/env bash
#
# Promote/deploy image sha เดิม ไป environment ที่ระบุ (sit|uat|production)
# "Build once, deploy many": ไม่ build ใหม่ — pull image tag = git sha ที่ build job สร้างไว้
#
# ⚠️ TEMPLATE — ต้องทำ manual steps เหล่านี้เองก่อนใช้จริง (repo ไม่ตั้งให้):
#   [ ] เลือกวิธีเข้าถึง target host: self-hosted runner บน host / docker context
#       (`docker context create` ชี้ ssh://user@host) แล้วตั้ง DEPLOY_TARGET = ชื่อ context นั้น
#   [ ] `docker login ghcr.io` บน target host (หรือ imagePullSecret) ให้ pull image ได้
#   [ ] provision ไฟล์ .env.<env> (secret ของ env นั้น) ไว้ที่ target host — จาก secret
#       manager / GitHub Environment secrets (repo ไม่มีไฟล์นี้ · gitignored)
#   [ ] ตั้ง GitHub Environments (sit/uat/production) + required reviewers เป็น gate promote
#
# สคริปต์นี้ fail-fast ทุก precondition ที่ขาด — ไม่มี exit 0 แบบแกล้งสำเร็จ
#
set -euo pipefail

ENV_NAME="${1:?usage: deploy.sh <sit|uat|production>}"

case "$ENV_NAME" in
  sit|uat|production) ;;
  *) echo "invalid environment: $ENV_NAME (ต้องเป็น sit|uat|production)" >&2; exit 1 ;;
esac

: "${IMAGE_REGISTRY:?ต้องตั้ง IMAGE_REGISTRY (เช่น ghcr.io/org/repo)}"
: "${IMAGE_TAG:?ต้องตั้ง IMAGE_TAG (= git sha ที่ promote — ห้าม build ใหม่)}"
# กัน deploy ลง docker ของ CI runner เองโดยไม่ตั้งใจ — ต้องชี้ target host ชัดเจน
: "${DEPLOY_TARGET:?ต้องตั้ง DEPLOY_TARGET = docker context ของ host ปลายทาง (กัน deploy ลง runner เอง)}"

# ให้ docker compose ทุกคำสั่งด้านล่างวิ่งไปที่ host ปลายทางผ่าน context นี้
export DOCKER_CONTEXT="$DEPLOY_TARGET"

ENV_FILE=".env.${ENV_NAME}"
OVERRIDE="docker-compose.${ENV_NAME}.yml"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ไม่พบ $ENV_FILE บน target host — ต้อง provision secret ของ $ENV_NAME ก่อน deploy" >&2
  exit 1
fi

echo "==> Deploying $IMAGE_REGISTRY:$IMAGE_TAG to $ENV_NAME"

# IMAGE_REGISTRY/IMAGE_TAG ส่งเข้า compose ผ่าน env (substitute ${IMAGE_*} ใน base compose)
export IMAGE_REGISTRY IMAGE_TAG

# pull sha ที่ระบุ แล้ว up ใหม่ โดย --no-build (ใช้ image ที่ build ครั้งเดียวเท่านั้น)
docker compose \
  -f docker-compose.yml \
  -f "$OVERRIDE" \
  --env-file "$ENV_FILE" \
  pull app

docker compose \
  -f docker-compose.yml \
  -f "$OVERRIDE" \
  --env-file "$ENV_FILE" \
  up -d --no-build

echo "==> $ENV_NAME now running $IMAGE_REGISTRY:$IMAGE_TAG"
