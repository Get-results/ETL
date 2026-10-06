FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Trace du commit construit, lue par src/version.py (log de démarrage et /health).
# Dokploy construit depuis un clone git : .dockerignore ne laisse passer de .git que
# HEAD, refs/ et packed-refs, juste de quoi résoudre le SHA, puis on les retire de
# l'image. GIT_SHA peut aussi être forcé (`--build-arg GIT_SHA=...`, cf. CI).
ARG GIT_SHA=""
RUN set -eu; sha="$GIT_SHA"; \
    if [ -z "$sha" ] && [ -f .git/HEAD ]; then \
        ref=$(sed -n 's/^ref: //p' .git/HEAD); \
        if [ -z "$ref" ]; then sha=$(cat .git/HEAD); \
        elif [ -f ".git/$ref" ]; then sha=$(cat ".git/$ref"); \
        elif [ -f .git/packed-refs ]; then sha=$(awk -v r="$ref" '$2 == r { print $1 }' .git/packed-refs); fi; \
    fi; \
    printf '%s\n' "${sha:-unknown}" > GIT_SHA; rm -rf .git; echo "GIT_SHA=$(cat GIT_SHA)"

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

CMD ["python", "-m", "run_daily_scraping"]