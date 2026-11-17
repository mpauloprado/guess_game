"""
Healthcheck do backend (infraestrutura; o código do jogo não muda).

Problema: o backend abre UMA conexão com o Postgres ao iniciar e não reconecta.
Se o banco reiniciar, o processo continua vivo, mas toda jogada retorna HTTP 500,
e o Docker não percebe (o /health original não consulta o banco).

Solução: testar o caminho real da aplicação, jogando uma partida de monitoramento.
  1. Conexão NOVA ao banco: garante que a partida "__healthcheck__" existe.
     Se o banco estiver fora, só marca unhealthy e espera (reiniciar não ajudaria).
  2. Jogada pela API do próprio container (usa a conexão da aplicação).
     - 200          -> saudável
     - sem resposta -> aplicação ainda subindo: unhealthy
     - 5xx          -> banco OK mas a aplicação perdeu a conexão: encerra o processo
                       principal (SIGTERM no PID 1); a política "restart" do Compose
                       recria o container, que volta com conexão nova.
"""
import base64
import json
import os
import signal
import sys
import urllib.error
import urllib.request

import psycopg2

GAME_ID = "__healthcheck__"
SENHA = "healthcheck"


def banco_ok() -> bool:
    try:
        conn = psycopg2.connect(
            dbname=os.environ.get("FLASK_DB_NAME"),
            user=os.environ.get("FLASK_DB_USER"),
            password=os.environ.get("FLASK_DB_PASSWORD"),
            host=os.environ.get("FLASK_DB_HOST"),
            port=os.environ.get("FLASK_DB_PORT", "5432"),
            connect_timeout=2,
        )
        with conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO game (game_id, password, attempts) VALUES (%s, %s, 0) "
                "ON CONFLICT (game_id) DO NOTHING",
                (GAME_ID, base64.b64encode(SENHA.encode()).decode()),
            )
        conn.close()
        return True
    except Exception as exc:  # banco fora ou ainda subindo
        print(f"banco indisponivel: {exc}", file=sys.stderr)
        return False


def main() -> int:
    if not banco_ok():
        return 1

    req = urllib.request.Request(
        f"http://127.0.0.1:5000/guess/{GAME_ID}",
        data=json.dumps({"guess": SENHA}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            return 0 if resp.status == 200 else 1
    except urllib.error.HTTPError as exc:
        if exc.code >= 500:
            print("aplicacao sem conexao com o banco: reiniciando o container", file=sys.stderr)
            os.kill(1, signal.SIGTERM)
        return 1
    except Exception as exc:  # aplicação ainda não está ouvindo
        print(f"aplicacao indisponivel: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
