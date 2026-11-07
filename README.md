# Radar Viral

Plataforma para identificar produtos e tendências **emergentes** (crescimento
acelerado com potencial de expansão), começando pelo mercado brasileiro.

> Status: **Etapa 7 — Painel (Streamlit)** concluída.

Requer **Python 3.11+** (`python --version`).

## Instalação (Windows / PowerShell, na pasta do projeto)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python scripts\init_db.py
python -m pytest -v
```

## Importar dados (CSV)

```powershell
python scripts\import_csv.py caminho\dados.csv --fonte google_trends_manual
```

Google Trends (arquivo baixado do site, sem renomear) — ver `docs/google_trends.md`:

```powershell
python scripts\import_google_trends.py C:\Users\voce\Downloads\time_series_BR_....csv
```

Formato padrão: `docs/formato_csv.md`.

## Famílias de produtos

```powershell
python scripts\families.py agrupar
python scripts\families.py listar
```

Detalhes e limitações: `docs/familias.md`.

## Indicadores de crescimento

```powershell
python scripts\analyze.py --detalhe
python scripts\analyze.py --janela 30 --csv data\indicadores.csv
```

Fórmulas, regras e limitações: `docs/analise.md`.

## Pontuação de potencial (0–100)

```powershell
python scripts\score.py --detalhe
```

Pesos em `config/pontuacao.toml`; explicação em `docs/pontuacao.md`.

## Painel

```powershell
streamlit run dashboard\app.py
```

Abre no navegador em http://localhost:8501. Detalhes: `docs/painel.md`. Para testar com dados **simulados**:

```powershell
python scripts\import_csv.py tests\fixtures\exemplo_simulado.csv --fonte teste_manual --simulado
```

## Estrutura atual

| Caminho | Finalidade |
|---|---|
| `radar_viral/config.py` | Lê e valida configurações do `.env` |
| `radar_viral/models.py` | `ObservationIn`: formato comum que todo coletor produz |
| `radar_viral/storage/schema.py` | Tabelas do banco |
| `radar_viral/storage/database.py` | Conexão (engine) e criação das tabelas |
| `radar_viral/storage/repository.py` | Funções de leitura/escrita |
| `radar_viral/collectors/file_import.py` | Partes comuns a toda importação (hash, duplicação, gravação) |
| `radar_viral/collectors/csv_importer.py` | CSV no formato padrão |
| `radar_viral/collectors/google_trends_csv.py` | CSV exportado do Google Trends |
| `radar_viral/processing/text_normalizer.py` | Normalização de texto (regras) |
| `radar_viral/processing/product_families.py` | Agrupamento em famílias (TF-IDF) |
| `radar_viral/analysis/series.py` | Monta séries temporais por família |
| `radar_viral/analysis/growth.py` | Indicadores e classificação |
| `radar_viral/analysis/report.py` | Tabela final (DataFrame) |
| `radar_viral/scoring/config.py` | Lê e valida `config/pontuacao.toml` |
| `radar_viral/scoring/scorer.py` | Critérios, pesos, confiança e ranking |
| `config/pontuacao.toml` | Pesos e parâmetros da pontuação (editável) |
| `radar_viral/ui/data.py` | Prepara os dados do painel (testável sem navegador) |
| `dashboard/app.py` | Painel visual (Streamlit) |
| `.streamlit/config.toml` | Tema do painel |
| `scripts/init_db.py` | Cria o banco |
| `scripts/score.py` | Ranking de potencial |
| `scripts/analyze.py` | Mostra/exporta os indicadores |
| `scripts/families.py` | Agrupar, listar e corrigir famílias |
| `scripts/import_csv.py` | Importa um CSV padrão |
| `scripts/import_google_trends.py` | Importa um export do Google Trends |
| `docs/formato_csv.md` | Formato e regras do CSV |
| `tests/` | Testes automatizados (usam dados **simulados**) |
| `docs/arquitetura.md` | Visão de arquitetura e roadmap |
| `data/` | Banco SQLite local (não versionado) |

## Regras do projeto
- Credenciais só no `.env` (nunca no código ou no GitHub).
- Histórico é *append-only*: coletas antigas nunca são sobrescritas.
- Dados simulados sempre marcados com `is_simulated=True`.
