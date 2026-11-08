# Rotina semanal (Etapa 9)

Tempo estimado: 10–20 minutos por semana.

## 1. Baixar os exports do Google Trends
Em https://trends.google.com.br, para cada grupo de produtos que você acompanha:
- país **Brasil**, período **Últimos 12 meses** (sempre o mesmo, para comparar);
- opcional: também **Últimos 30 dias**, para ver o movimento recente (janelas de 7 e 14 dias).
  O export de 7 dias aparece no gráfico, mas tem dias de menos para os indicadores;
- até 5 termos parecidos por consulta ("+ Comparar");
- no quadro "Interesse ao longo do tempo", clique no ícone de download.

Não renomeie nem abra no Excel. Os arquivos vão para a pasta Downloads.

## 2. Importar tudo de uma vez
    python scripts\import_pasta.py

(usa `EXPORTS_DIR` do `.env`; ou informe a pasta:
`python scripts\import_pasta.py C:\Users\SEU_USUARIO\Downloads`)

Com `--mover`, os arquivos resolvidos vão para a subpasta `importados`,
deixando na pasta só o que deu erro — útil para a semana seguinte começar limpa.

O comando:
- importa cada `time_series_*.csv` separadamente (um erro não para os outros);
- pula arquivos já importados (rodar duas vezes é seguro);
- ignora a última semana incompleta;
- agrupa as famílias no final.

## 3. Revisar famílias novas (quando houver)
    python scripts\families.py listar
    python scripts\families.py mover "termo" "família"

## 4. Abrir o painel
    streamlit run dashboard\app.py

Olhe as abas **Emergentes** e **Em crescimento**; para as famílias que
interessam, cadastre os links de compra em **Detalhes → Onde comprar**.

## Leitura dos resultados
| Status | Significado | O que fazer |
|---|---|---|
| IMPORTADO | gravado no banco | nada |
| JÁ IMPORTADO | mesmo conteúdo de um arquivo anterior | nada (pode apagar o arquivo) |
| ERRO | o arquivo não pôde ser lido | ler a mensagem; baixar de novo |

O comando termina com código de saída 1 se algum arquivo teve erro (útil se
um dia ele for agendado).

## Por que não automatizar o download
O Google Trends não oferece uma forma oficial de baixar esses arquivos
automaticamente, e automatizar o site violaria os termos de uso. Por isso o
download continua manual; tudo depois dele é automático.
