# Radar Viral

Plataforma para identificar produtos e tendências **emergentes** (crescimento
acelerado com potencial de expansão), começando pelo mercado brasileiro.

> Status: **Etapa 1 — Fundação** (estrutura, configuração e banco histórico).

## Instalação (Windows / PowerShell, na pasta do projeto)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python scripts\init_db.py
python -m pytest -v
```

## Estrutura atual

| Caminho | Finalidade |
|---|---|
| `radar_viral/config.py` | Lê e valida configurações do `.env` |
| `radar_viral/models.py` | `ObservationIn`: formato comum que todo coletor produz |
| `radar_viral/storage/schema.py` | Tabelas do banco |
| `radar_viral/storage/database.py` | Conexão (engine) e criação das tabelas |
| `radar_viral/storage/repository.py` | Funções de leitura/escrita |
| `scripts/init_db.py` | Cria o banco |
| `tests/` | Testes automatizados (usam dados **simulados**) |
| `docs/arquitetura.md` | Visão de arquitetura e roadmap |
| `data/` | Banco SQLite local (não versionado) |

## Regras do projeto
- Credenciais só no `.env` (nunca no código ou no GitHub).
- Histórico é *append-only*: coletas antigas nunca são sobrescritas.
- Dados simulados sempre marcados com `is_simulated=True`.
