# Arquitetura do Radar Viral

## Fluxo de dados

```
Fontes externas ─► collectors/ ─► ObservationIn ─► storage/ (histórico)
                                                     │
                     processing/ (normalização, famílias de produtos)
                                                     │
                     analysis/ (indicadores 7/14/30/90 dias) ─► scoring/ (0–100)
                                                     │
                     ai/ (relatórios com evidências)   dashboard/ (Streamlit)
```

## Estrutura-alvo (pastas criadas somente quando a etapa chegar)

```
radar_viral/
  config.py, models.py
  storage/      schema, conexão, repositório         (Etapa 1)
  collectors/   base.py + um módulo por fonte        (Etapa 2+)
  processing/   limpeza de texto, famílias           (Etapa 4)
  analysis/     crescimento, aceleração, persistência (Etapa 5)
  scoring/      pontuação com pesos em config/        (Etapa 6)
  ai/           resumos e relatórios                  (Etapa 9)
dashboard/      app Streamlit                         (Etapa 7)
config/         scoring_weights.yaml                  (Etapa 6)
scripts/  tests/  docs/  data/
```

## Esquema do banco (Etapa 1)

- `sources` — catálogo de fontes.
- `collection_runs` — cada execução de coleta (início, fim, status, total, erro).
- `observations` — uma linha por item por coleta; nunca é sobrescrita.
  Guarda `raw_payload` (resposta original) para reprocessar no futuro.

## Decisões
- **SQLAlchemy Core** (e não sqlite3 puro): o mesmo código funciona em SQLite e
  PostgreSQL. Não usamos o ORM por enquanto para manter o SQL visível.
- **UTC** em todas as datas.
- **Migrações (Alembic)** só quando precisarmos alterar tabelas existentes.
