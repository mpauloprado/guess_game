# =============================================================================
# Frontend React + NGINX (proxy reverso e balanceador do backend)
# Build multi-stage: Node 18 compila o React; a imagem final é só o NGINX.
# Contexto de build = raiz do repositório (precisa de frontend/ e nginx/).
# =============================================================================
ARG NODE_VERSION=18.20.8
ARG NGINX_VERSION=1.28

# ---- Etapa 1: build do React ------------------------------------------------
FROM node:${NODE_VERSION}-alpine AS build
WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
# --ignore-scripts: não baixa o binário do Cypress nem roda scripts de pós-instalação,
# desnecessários para gerar o build de produção.
RUN npm ci --ignore-scripts --no-audit --no-fund

COPY frontend/ ./
# O frontend chama o backend em "${REACT_APP_BACKEND_URL}/create" e ".../guess/<id>".
# Com "/api", as chamadas vão para o próprio NGINX (mesma origem), que repassa
# aos backends. Valor embutido no build (variável do Create React App).
ARG REACT_APP_BACKEND_URL=/api
ENV REACT_APP_BACKEND_URL=${REACT_APP_BACKEND_URL}
RUN npm run build

# ---- Etapa 2: NGINX servindo o build e fazendo proxy ------------------------
FROM nginx:${NGINX_VERSION}-alpine
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/build /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/nginx-health || exit 1
