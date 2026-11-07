# Formato de importação CSV do Radar Viral

Modelo vazio: `docs/modelo_importacao.csv`. Exemplo (dados SIMULADOS):
`tests/fixtures/exemplo_simulado.csv`.

## Regras gerais
- Primeira linha = cabeçalho com os nomes das colunas abaixo (ordem livre,
  maiúsculas/minúsculas indiferentes).
- Separador `;` ou `,` (detectado automaticamente pela primeira linha).
- Codificação UTF-8 (com ou sem BOM) ou Windows-1252 (Excel).
- Datas: `AAAA-MM-DD` ou `DD/MM/AAAA`.
- Números: separador decimal `,` por padrão (`1.234,56`). Para `1,234.56`,
  use `--decimal .`.
- Célula vazia = informação indisponível (nunca preencha com valores inventados).
- Um arquivo = uma fonte e um país (definidos na linha de comando).
- Importação "tudo ou nada": qualquer erro impede a gravação do arquivo inteiro.
- O mesmo conteúdo não pode ser importado duas vezes com sucesso.

## Colunas

| Coluna | Obrigatória | Tipo | Exemplo |
|---|---|---|---|
| `data_referencia` | sim | data | `15/09/2025` |
| `termo` | sim | texto | `mini aspirador portátil` |
| `categoria_id` | não | texto | `casa_01` |
| `categoria` | não | texto | `Casa` |
| `posicao` | não | inteiro ≥ 1 | `3` |
| `volume_busca` | não | número ≥ 0 | `4.100` |
| `valor_popularidade` | não | número | `78` |
| `metrica_popularidade` | se houver valor | texto | `google_trends_0_100` |
| `preco` | não | número ≥ 0 | `45,00` |
| `moeda` | não | código ISO | `BRL` |
| `url` | não | http(s) | `https://...` |
| `id_externo` | não | texto | id do item na fonte |

## Códigos de fonte sugeridos
`google_trends_manual`, `tiktok_creative_center_manual`, `pinterest_trends_manual`,
`pesquisa_propria`. Use apenas letras minúsculas, números e `_`.

## Atenção com Google Trends
Os valores do Google Trends são **relativos (0–100)** dentro de cada consulta,
não quantidades de buscas. Registre-os em `valor_popularidade` com
`metrica_popularidade = google_trends_0_100`, nunca em `volume_busca`.
Valores de consultas diferentes não são diretamente comparáveis.
