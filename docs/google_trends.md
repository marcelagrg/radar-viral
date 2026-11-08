# Google Trends — importação manual

## Como exportar
1. https://trends.google.com.br → pesquise o(s) termo(s) (até 5 com "+ Comparar").
2. Escolha país e período.
3. No quadro "Interesse ao longo do tempo", clique no ícone de download.
4. NÃO renomeie nem abra/salve no Excel: o nome do arquivo informa país e
   período, e o Excel pode alterar o conteúdo.

## Como importar
    python scripts\import_google_trends.py C:\Users\...\Downloads\time_series_BR_....csv

## Formatos confirmados com arquivos reais
| Período no site | Formato | Exemplo | Tratamento |
|---|---|---|---|
| Últimos 12 meses | semanal | `"2025-11-02",59` | 1 valor por semana |
| Últimos 30 dias | diário | `"2026-10-10",76` | 1 valor por dia |
| Últimos 7 dias | a cada 4 horas, em UTC | `"2026-11-01T12:00:00Z",81` | **média por dia**, no fuso do país (BR: horário de Brasília); dias incompletos descartados |

## O que cada export permite analisar
Cada janela precisa de 2× o seu tamanho em dados (janela atual + anterior):
| Export | Janelas que funcionam | Uso recomendado |
|---|---|---|
| 12 meses | 7, 14, 30 e 90 dias | **principal**: pontuação e tendência |
| 30 dias | 7 e 14 dias | movimento recente (painel com janela 7 ou 14) |
| 7 dias | nenhuma (≈ 6 dias completos) | só para ver no gráfico; não alimenta indicadores |

Uma família pode ter exports de frequências diferentes: o sistema guarda o
mais recente de CADA frequência e usa todos na pontuação.

## Como interpretar — limitações
- **Escala relativa 0–100**: 100 é o pico DENTRO daquela consulta. Não é número
  de buscas. Gravado em `popularity_value` com `popularity_metric = google_trends_0_100`.
- **Exportações diferentes não se comparam diretamente**: se você baixar
  "playstation" de novo daqui a um mês, a mesma semana pode ter outro valor,
  porque o pico do período mudou. Cada arquivo é uma coleta separada; a análise
  (Etapa 5) compara valores dentro da mesma coleta.
- **Termos comparados juntos** compartilham a mesma escala — é a forma correta
  de comparar dois produtos.
- **Última semana parcial** é ignorada por padrão (parece uma queda falsa).
  `--incluir-parcial` a importa mesmo assim.
- Export de 7 dias: o 1º e o último dia costumam ser incompletos e são ignorados.
- **`<1`** (interesse muito baixo) é gravado como 0,5; o texto original fica em
  `raw_payload`. Não confirmado em export real até agora.
- Formato com vários termos: suportado, mas confirmado apenas com 1 termo.
