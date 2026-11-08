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
  collectors/   csv_importer.py (Etapa 2); APIs futuras, um módulo por fonte
  processing/   text_normalizer, product_families     (Etapa 4)
  analysis/     series, growth, report               (Etapa 5)
  scoring/      config + scorer                       (Etapa 6)
  ai/           resumos e relatórios                  (Etapa 9)
dashboard/      app.py (Streamlit) + radar_viral/ui/data.py  (Etapa 7)
config/         pontuacao.toml (TOML: lido sem dependência extra)  (Etapa 6)
scripts/  tests/  docs/  data/
```

## Esquema do banco (Etapa 1)

- `sources` — catálogo de fontes.
- `collection_runs` — cada execução de coleta (início, fim, status, total, erro).
- `observations` — uma linha por item por coleta; nunca é sobrescrita.
  Guarda `raw_payload` (resposta original) para reprocessar no futuro.
  `reference_date` (Etapa 2) = data a que o valor se refere; `collected_at` = quando entrou no banco.
- `product_links` (Etapa 8): links de compra por família; famílias com links ficam protegidas.
- `product_families` / `term_families` (Etapa 4): família de cada termo; `method=manual` marca correções suas.
- `collection_runs.file_sha256` (Etapa 2) impede importar o mesmo arquivo duas vezes.

## Decisões
- **SQLAlchemy Core** (e não sqlite3 puro): o mesmo código funciona em SQLite e
  PostgreSQL. Não usamos o ORM por enquanto para manter o SQL visível.
- **UTC** em todas as datas.
- **Migrações (Alembic)** só quando precisarmos alterar tabelas existentes.

## Fontes
- Mercado Livre: descartado (API exige OAuth; documentação e API recusaram acesso a partir da nuvem).
- Etapa 2: importação manual de CSV, sem dependência de API ou scraping.
- Etapa 3: conversor do export do Google Trends (`docs/google_trends.md`).
- Etapa 8: Amazon, Shopee e Mercado Livre entram só como links inseridos manualmente (sem coleta de dados).
