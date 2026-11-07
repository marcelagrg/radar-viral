# Google Trends — importação manual

## Como exportar
1. https://trends.google.com.br → pesquise o(s) termo(s) (até 5 com "+ Comparar").
2. Escolha país e período.
3. No quadro "Interesse ao longo do tempo", clique no ícone de download.
4. NÃO renomeie nem abra/salve no Excel: o nome do arquivo informa país e
   período, e o Excel pode alterar o conteúdo.

## Como importar
    python scripts\import_google_trends.py C:\Users\...\Downloads\time_series_BR_....csv

## Formato confirmado (export real de 07/11/2026)
    nome: time_series_BR_20251107-0805_20261107-0805.csv
    "Time","playstation"
    "2025-11-02",59

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
- **`<1`** (interesse muito baixo) é gravado como 0,5; o texto original fica em
  `raw_payload`. Não confirmado em export real até agora.
- Formato com vários termos: suportado, mas confirmado apenas com 1 termo.
