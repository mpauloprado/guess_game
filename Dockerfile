# =============================================================================
# Backend — Jogo de Adivinhação (Flask, Python 3.12)
# Build: docker compose build backend
# =============================================================================
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependências primeiro: camada reaproveitada enquanto requirements.txt não mudar.
# gunicorn = servidor WSGI de produção (o "flask run" é só para desenvolvimento);
# é infraestrutura, o código do jogo não muda.
COPY requirements.txt .
RUN pip install -r requirements.txt gunicorn==23.0.0

# Só o necessário para o backend rodar (sem testes, frontend etc.)
COPY run.py ./
COPY guess/ guess/
COPY repository/ repository/
COPY docker/backend-healthcheck.py /opt/healthcheck.py

# Não roda como root
RUN useradd --system --uid 10001 --no-create-home app
USER app

EXPOSE 5000

# Healthcheck que joga uma partida de verdade (testa a conexão da aplicação com o
# banco) e reinicia o container se a aplicação perdeu a conexão. Ver o script.
HEALTHCHECK --interval=10s --timeout=8s --start-period=20s --retries=3 \
    CMD ["python", "/opt/healthcheck.py"]

# 1 processo + 4 threads por container (equivalente ao servidor threaded do Flask);
# a escala horizontal é feita com mais réplicas do container, não com mais workers.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", \
     "--access-logfile", "-", "run:app"]
