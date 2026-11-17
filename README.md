# Jogo de Adivinhação com Docker Compose

Estrutura em Docker Compose para o [jogo de adivinhação](https://github.com/fams/guess_game)
(backend Flask + frontend React): **NGINX** servindo o frontend e balanceando a carga entre
**várias instâncias do backend**, **PostgreSQL** com volume persistente, reinício automático
de containers e atualização de cada componente apenas trocando a versão da imagem.

O código do jogo (`guess/`, `repository/`, `run.py`, `frontend/src/`) **não foi alterado**.
Tudo o que foi acrescentado é infraestrutura. A documentação original do jogo está em
[`docs/README_JOGO.md`](docs/README_JOGO.md).

## Como executar

Pré-requisitos: Docker com **Docker Compose v2** (`docker compose`, já incluso no Docker Desktop).

```bash
git clone https://github.com/mpauloprado/guess_game.git
cd guess_game
docker compose up -d --build
```

**Acesse: http://localhost**

A primeira subida leva alguns minutos (build do React e instalação das dependências Python).
Acompanhe com `docker compose ps`: quando os 5 containers estiverem `healthy`, o jogo está pronto.

> Se a porta 80 já estiver em uso na sua máquina, escolha outra:
> `HTTP_PORT=8080 docker compose up -d --build` e acesse http://localhost:8080.

### Como jogar

1. **Maker** (http://localhost/maker): digite uma palavra secreta e envie. Anote o `game_id`.
2. **Breaker** (http://localhost/breaker): informe o `game_id` e tente adivinhar a palavra.

### Comandos úteis

| Ação | Comando |
|---|---|
| Ver os containers e a saúde de cada um | `docker compose ps` |
| Logs (todos / só backends) | `docker compose logs -f` / `docker compose logs -f backend` |
| Parar mantendo os dados | `docker compose down` |
| Parar e **apagar** os dados | `docker compose down -v` |
| Mudar o número de backends | `BACKEND_REPLICAS=5 docker compose up -d` |

## Arquitetura

```
                 navegador
                     │  http://localhost  (porta 80)
                     ▼
        ┌────────────────────────┐   rede "web"
        │ nginx  (frontend React │
        │  + proxy reverso)      │   /        → arquivos do React
        └───────────┬────────────┘   /api/*   → backends (round-robin)
                    │                                       rede "app" (interna)
        ┌───────────┼─────────────┐
        ▼           ▼             ▼
   backend-1    backend-2    backend-3      Flask + gunicorn (réplicas da mesma imagem)
        └───────────┼─────────────┘
                    ▼
                   db  (PostgreSQL 16)  ── volume "db-data"
```

| Serviço | Imagem | Função |
|---|---|---|
| `nginx` | `guess-game-frontend:${FRONTEND_VERSION}` (build de `frontend/Dockerfile`) | Serve o build do React e faz proxy reverso + balanceamento para o backend |
| `backend` | `guess-game-backend:${BACKEND_VERSION}` (build de `Dockerfile`) | API Flask do jogo; **3 réplicas** por padrão |
| `db` | `postgres:${POSTGRES_VERSION}` | Armazena os jogos |

### Arquivos acrescentados

| Arquivo | Conteúdo |
|---|---|
| `docker-compose.yml` | Serviços, volume, redes, réplicas, reinício automático e versões parametrizadas |
| `Dockerfile` | Imagem do backend (Python 3.12 + gunicorn, usuário sem privilégios) |
| `frontend/Dockerfile` | Build multi-stage: Node 18 compila o React → imagem final NGINX |
| `nginx/nginx.conf` | Proxy reverso, balanceamento e failover |
| `postgres/init.sql` | Cria a tabela do jogo na primeira subida do banco |
| `docker/backend-healthcheck.py` | Healthcheck do backend que testa a conexão real com o banco |
| `.env.example` | Variáveis de versão, réplicas, porta e credenciais |
| `.dockerignore` / `.gitignore` | Ajustados para versionar os arquivos Docker e não enviar `.env` |

## Decisões de design

### Serviços e imagens

- **Backend:** `python:3.12-slim-bookworm`, conforme a versão do projeto. Usa **gunicorn**
  (servidor WSGI de produção) em vez do `flask run`, que é só para desenvolvimento. Roda com um
  processo e 4 threads por container. A escala é feita com mais réplicas, não com mais processos
  no mesmo container. O processo roda com usuário sem privilégios.
- **Frontend:** build multi-stage. A etapa `node:18` (versão do projeto) faz o `npm ci` e o
  `npm run build`. A imagem final tem só o NGINX e os arquivos estáticos, sem Node nem
  `node_modules`. O `npm ci --ignore-scripts` evita baixar o binário do Cypress (testes E2E),
  que não é usado no build.
- **URL do backend no frontend:** o React lê `REACT_APP_BACKEND_URL` no build. Ela é definida
  como `/api` (argumento de build no Compose). Assim o navegador chama o próprio NGINX, na
  mesma origem, sem CORS e sem IP fixo, e o NGINX encaminha para os backends.

### Balanceamento de carga

- O serviço `backend` tem `deploy.replicas: 3`. O DNS interno do Docker responde ao nome
  `backend` com o IP de **todas** as réplicas.
- No `nginx.conf`, o `upstream guess_backend` usa `server backend:5000 resolve`. O NGINX
  distribui as requisições em **round-robin** e consulta o DNS do Docker a cada 5 s. Com isso,
  ele acompanha réplicas que entram, saem ou mudam de IP após um reinício, e também a mudança
  do número de réplicas (`BACKEND_REPLICAS`), sem editar a configuração.
- **Failover:** `max_fails=2 fail_timeout=10s` tira da rotação uma réplica que falha, e
  `proxy_next_upstream` reenvia a requisição para outra réplica quando a conexão falha. O
  usuário não percebe a queda de uma instância.
- Cada resposta da API traz o cabeçalho `X-Upstream` com a réplica que atendeu, para observar
  o balanceamento.

### Volumes

- `db-data` (volume nomeado) guarda `/var/lib/postgresql/data`. Os jogos sobrevivem a
  `docker compose down`, à recriação de containers e à troca de versão das imagens.
- `postgres/init.sql` cria a tabela `game` (a mesma estrutura que o backend cria) na primeira
  subida. Isso evita a corrida entre réplicas tentando criar a tabela ao mesmo tempo.

### Redes

- `web`: única rede com porta publicada no host, usada só pelo NGINX.
- `app`: rede **interna** (`internal: true`) entre NGINX, backends e banco. Backend e banco
  não ficam expostos fora do Docker, e só o NGINX é ponto de entrada.

### Resiliência

- **Todos os serviços** usam `restart: unless-stopped`: se um container cair, o Docker o
  reinicia automaticamente.
- **Healthchecks:** o banco usa `pg_isready`, o NGINX usa `/nginx-health` e o backend usa o
  script descrito a seguir. O `depends_on` com `service_healthy` define a ordem de subida:
  banco, depois backends, depois NGINX.
- **Perda de conexão com o banco:** o backend abre uma conexão com o Postgres ao iniciar e
  não reconecta sozinho. Se o banco reiniciar, o processo continua vivo, mas toda jogada passa
  a retornar erro 500. Para resolver sem mexer no código, o healthcheck do backend
  (`docker/backend-healthcheck.py`) joga uma partida de monitoramento (`__healthcheck__`)
  pela API do container:
  - **jogada OK:** container saudável.
  - **banco fora do ar:** marca *unhealthy* e espera o banco voltar, porque reiniciar não
    ajudaria.
  - **banco no ar, mas a aplicação devolve 500:** a aplicação perdeu a conexão. O script
    encerra o processo, e o `restart` do Compose recria o container com conexão nova.

> `docker stop` e `docker kill` são paradas **manuais**: por definição do Docker, a política
> `unless-stopped` não reinicia o que o operador parou. Para simular uma falha, encerre o
> processo dentro do container (exemplo em [Testes realizados](#testes-realizados)).
> `docker compose up -d` recoloca as réplicas paradas.

## Atualização de componentes (troca de versão)

As versões das imagens são variáveis no `docker-compose.yml`, com valor padrão. Para atualizar
um componente, basta mudar a versão e rodar `docker compose up -d`. O Compose recria **apenas**
o serviço alterado, e os dados continuam no volume.

| Variável | Padrão | Componente |
|---|---|---|
| `BACKEND_VERSION` | `1.0.0` | imagem do backend |
| `FRONTEND_VERSION` | `1.0.0` | imagem do NGINX + frontend |
| `POSTGRES_VERSION` | `16.6-alpine` | imagem do PostgreSQL |
| `REGISTRY` | vazio | prefixo de registry, ex.: `ghcr.io/usuario/` |
| `BACKEND_REPLICAS` | `3` | quantidade de backends |
| `HTTP_PORT` | `80` | porta do host |

Recomendado: `cp .env.example .env` e editar as versões no `.env`.

**Backend**, depois de alterar o código ou as dependências:

```bash
# no .env: BACKEND_VERSION=1.0.1
docker compose up -d --build backend
```

**Frontend / NGINX**, depois de alterar o React ou o `nginx.conf`:

```bash
# no .env: FRONTEND_VERSION=1.0.1
docker compose up -d --build nginx
```

**PostgreSQL**, com uma nova versão de correção da mesma versão principal:

```bash
# no .env: POSTGRES_VERSION=16.8-alpine
docker compose up -d db
```

> Mudar a versão **principal** do Postgres (ex.: 16 → 17) exige migrar os dados com
> `pg_dump`/`pg_restore`, porque o formato do diretório de dados muda entre versões principais.

**Voltar à versão anterior (rollback):** volte a variável para o valor anterior e rode
`docker compose up -d <serviço>`. Como a imagem antiga continua no cache local, a volta é
imediata.

**Usando um registry:** com `REGISTRY` definido, `docker compose build` e
`docker compose push` publicam as imagens versionadas. Em outro servidor, basta
`docker compose pull` e `docker compose up -d` com as mesmas variáveis.

## Testes realizados

Executados em Docker 28.5.2 / Compose 2.40.3 (Linux), com a pilha completa:

| Teste | Como | Resultado |
|---|---|---|
| Jogo pelo NGINX | `POST /api/create` e `POST /api/guess/<id>` | Jogo criado. Palpite errado retornou a dica, e o certo retornou `Correct` |
| Rotas do frontend | `GET /`, `/maker`, `/breaker` | HTTP 200 (`text/html`) |
| Balanceamento | 12 requisições a `/api/health` | 4 para cada uma das 3 réplicas (cabeçalho `X-Upstream`) |
| Queda de um backend | `docker exec guess-game-backend-2 python -c "import os,signal; os.kill(1, signal.SIGTERM)"` | Container reiniciado automaticamente. As 40 jogadas feitas durante a queda retornaram 200 |
| Persistência | `docker compose down` e `docker compose up -d` | Jogo criado antes continuou acessível |
| Reinício do banco | `docker compose restart db` | Backends reiniciados pelo healthcheck. Jogadas voltaram em cerca de 4 s |
| Queda do banco | `pg_ctl stop -m immediate` dentro do container | Postgres reiniciado automaticamente. Jogadas voltaram em cerca de 5 s |
| Atualização | `BACKEND_VERSION=1.0.1` e `up -d --build backend` | Só os 3 backends foram recriados com a 1.0.1. NGINX e banco ficaram intactos |
| Rollback | voltar para `1.0.0` e `up -d backend` | Backends de volta à 1.0.0 |

Para reproduzir o teste de balanceamento:

```bash
for i in $(seq 9); do curl -s -D - -o /dev/null http://localhost/api/health | grep -i x-upstream; done
```

## Versões

Python 3.12 · Node 18.20.8 (somente build) · NGINX 1.28 · PostgreSQL 16.6 · gunicorn 23.0.0 ·
dependências Python conforme `requirements.txt` do projeto.
