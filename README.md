# Radar Viral

Plataforma para identificar produtos e tendências **emergentes** (crescimento
acelerado com potencial de expansão), começando pelo mercado brasileiro.

> Status: **Etapa 2 — Importação de CSV** concluída (sobre a Etapa 1 — Fundação).

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

Formato do arquivo: `docs/formato_csv.md`. Para testar com dados **simulados**:

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
| `radar_viral/collectors/csv_importer.py` | Lê, valida e grava arquivos CSV |
| `scripts/init_db.py` | Cria o banco |
| `scripts/import_csv.py` | Importa um CSV pela linha de comando |
| `docs/formato_csv.md` | Formato e regras do CSV |
| `tests/` | Testes automatizados (usam dados **simulados**) |
| `docs/arquitetura.md` | Visão de arquitetura e roadmap |
| `data/` | Banco SQLite local (não versionado) |

## Regras do projeto
- Credenciais só no `.env` (nunca no código ou no GitHub).
- Histórico é *append-only*: coletas antigas nunca são sobrescritas.
- Dados simulados sempre marcados com `is_simulated=True`.
