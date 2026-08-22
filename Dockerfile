FROM node:22-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-dev build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv "$VIRTUAL_ENV"

WORKDIR /usr/src/claude-code-karma

### ------------------ Dependencies ------------------ ###
COPY ./api/requirements.txt ./api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

COPY ./frontend/package.json ./frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci

### --------------------- Sources -------------------- ###
COPY . .

RUN pip install --no-cache-dir -e "./api[dev]"

RUN mkdir -p /home/node/.claude /home/node/.claude_karma \
    && chown -R node:node /usr/src/claude-code-karma /opt/venv /home/node

USER node

EXPOSE 8020/tcp 5180/tcp

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8020", "--app-dir", "api"]
