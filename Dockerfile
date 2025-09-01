# 第一階段：安裝 poetry 並建立套件清單
FROM python:3.13-alpine AS builder

# 安裝 poetry
RUN pip install poetry poetry-plugin-export

# 將 pyproject.toml 和 poetry.lock(如果有) 複製到容器中
COPY pyproject.toml poetry.lock* ./

# 若 poetry.lock 不存在，則執行 poetry lock 建立
RUN if [ ! -f poetry.lock ]; then poetry lock; fi

# 建立依賴清單
RUN poetry export -f requirements.txt --output requirements.txt --without-hashes
RUN pip wheel --no-cache-dir --no-deps --wheel-dir wheels -r requirements.txt

# 第二階段：建立執行環境
FROM python:3.13-alpine AS runner

# 複製第一階段的 wheels 和 requirements.txt
COPY --from=builder wheels wheels
COPY --from=builder requirements.txt requirements.txt

# 安裝套件，並刪除 wheels 和 requirements.txt
RUN pip install --no-cache-dir --no-index --find-links=wheels -r requirements.txt && \
    rm -rf wheels requirements.txt

# 將 app.py 複製到容器中
COPY app.py app.py

# 使用 python 執行應用程式
ENTRYPOINT ["python", "app.py"]
CMD ["-u"]
