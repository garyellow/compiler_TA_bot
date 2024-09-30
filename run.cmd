@echo off
docker-compose down
docker image prune -f
docker-compose build
docker-compose up -d
