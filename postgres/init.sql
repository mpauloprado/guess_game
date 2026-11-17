-- Executado só na PRIMEIRA subida do Postgres (volume vazio).
-- Mesma tabela que repository/postgres.py cria com "CREATE TABLE IF NOT EXISTS".
-- Criar antes evita a corrida entre várias réplicas do backend tentando criar a
-- tabela ao mesmo tempo na primeira inicialização. O código do jogo não muda.
CREATE TABLE IF NOT EXISTS game (
    game_id  TEXT PRIMARY KEY,
    password TEXT,
    attempts INTEGER
);
