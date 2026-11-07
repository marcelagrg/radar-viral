# Radar Viral

Plataforma para identificar produtos e tendências **emergentes** (crescimento
acelerado com potencial de expansão), começando pelo mercado brasileiro.

> Status: **Etapa 4 — Famílias de produtos** concluída.

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

Detalhes e limitações: `docs/familias.md`. Para testar com dados **simulados**:

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
| `scripts/init_db.py` | Cria o banco |
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
