###
### Stage 1 — Build the marketing website (Vite + React + TS)
### Output: /build/dist consumed by the Python runtime stage below
###
FROM node:20-slim AS website-builder

WORKDIR /build

# Cache deps layer: only re-runs when package-lock.json changes
COPY website/package.json website/package-lock.json ./
RUN npm ci --no-audit --no-fund

# Now copy the rest of the website sources and build
COPY website/ ./
RUN npm run build

# ── 牆 O CLIENTE DO JOGO, PRE-COMPILADO (FORMA, 2026-09-04) ───────────────────
#
# Ate aqui o `miniapp/` nao construia NADA: os tres ficheiros de JSX cru eram
# servidos como estao e o TELEMOVEL DO JOGADOR compilava-os, com um
# @babel/standalone de 3.137.752 bytes descarregado so' para isso. MEDIDO:
# 1026 ms de compilacao por abertura num desktop de 16 cores (4-6x isso num
# telemovel), e first-contentful-paint de 1988 ms -> 440 ms depois deste passo.
#
# Corre AQUI porque esta stage ja' tem node + o `npm ci` feito (o esbuild vem
# do Vite, ja' instalado) — nao ha uma segunda arvore de dependencias nem uma
# imagem nova.
#
# ⚠️ Se este passo desaparecer, o jogo NAO parte: o `index.html` pede
# `/miniapp/dist/bundle.js`, leva 404 e cai sozinho no caminho velho do Babel.
# Fica lento, nunca branco. Foi assim desenhado precisamente porque um mini-app
# que EXIGISSE build seria tela branca para 248 pessoas no primeiro deploy que
# o esquecesse.
COPY miniapp/ /miniapp/
COPY scripts/build_miniapp.mjs ./build_miniapp.mjs
RUN node build_miniapp.mjs /miniapp

###
### Stage 2 — Python runtime (the bot + aiohttp webserver)
###
FROM python:3.11-slim

WORKDIR /app

# Force unbuffered output — CRITICAL for seeing logs before OOM/crash kills
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# curl + wget for healthchecks (Coolify's UI healthcheck uses wget by default;
# our HEALTHCHECK below uses curl. Install both so either works.)
RUN apt-get update && apt-get install -y --no-install-recommends curl wget && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the bot source
COPY . .

# Drop-in the built website (replaces any stale committed dist/)
COPY --from=website-builder /build/dist ./website/dist

# E o cliente do jogo ja' compilado. Nao esta' no git (`dist/` e' ignorado):
# nasce aqui, em cada build, a partir de `miniapp/components/*.js`.
COPY --from=website-builder /miniapp/dist ./miniapp/dist

# Health check port for Coolify/Docker
EXPOSE 8080

# Generous start-period so migrations + seeds have time to run before Docker
# starts counting healthcheck failures. The HTTP server itself answers
# immediately once post_init kicks in.
HEALTHCHECK --interval=30s --timeout=10s --start-period=180s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8080/healthz || exit 1

# Use -u flag as extra insurance for unbuffered output
CMD ["python", "-u", "main.py"]
