# Análise de crescimento (Etapa 5)

## Séries
Uma **série** = valores de uma família de produto, de uma fonte, país e
métrica, ao longo do tempo (`analysis/series.py`).

- Métrica analisada: `popularity_value` (com sua `popularity_metric`); se não
  houver, `search_volume`.
- **Métricas relativas** (`google_trends_0_100`): cada exportação é uma série
  separada, porque cada arquivo tem a sua própria escala. Por padrão a
  análise usa a exportação mais recente; `--todas-coletas` mostra todas.
- Termos da mesma família na mesma data são **somados** (válido no Trends só
  porque termos de uma mesma exportação compartilham a escala).
- Frequência inferida pela mediana do intervalo entre datas (1, 7 ou 30 dias).

## Janelas
7, 14, 30 e 90 dias, convertidas em períodos: com dados semanais,
7d = 1, 14d = 2, 30d = 4, 90d = 13 semanas. Janela menor que a frequência
(7d com dados mensais) não é calculada. Cada janela precisa de 2× o número
de períodos (janela atual + anterior).

## Indicadores (janela de N períodos)
| Indicador | Cálculo | Leitura |
|---|---|---|
| Crescimento (%) | (média atual − média anterior) / média anterior × 100 | quanto o nível subiu |
| Velocidade (%/sem) | inclinação da reta (mínimos quadrados) da janela atual ÷ média × 100, convertida para semana; ≥ 3 pontos | ritmo atual |
| Aceleração (p.p./sem) | velocidade atual − velocidade da janela anterior | está acelerando ou freando? |
| Consistência (0–1) | fração das variações período a período ≥ 0 | crescimento contínuo × aos saltos |
| Queda desde o pico (%) | (último − máximo da janela) / máximo | já passou do pico? |
| Base baixa | média anterior < 5 (Trends) ou < 1 (outras) | percentual não confiável |

## Classificação (janela principal, padrão 90d)
Aplicada nesta ordem — a primeira regra verdadeira vence:
1. `dados insuficientes` — menos de 2×N pontos.
2. `base baixa` — sinal fraco demais.
3. `surgiu do zero` — média anterior = 0.
4. `pico passageiro` — crescimento > 0, mas último valor ≥ 40% abaixo do pico.
5. `emergente` — crescimento ≥ 30%, consistência ≥ 0,6 e aceleração > 0.
6. `em crescimento` / `crescimento desacelerando` — crescimento ≥ 10%.
7. `em queda` — crescimento ≤ −10%.
8. `estável` — o resto.

Limites em `analysis/growth.py` (`RULES`, `MIN_BASE`). Valores iniciais,
a calibrar com dados reais.

## Limitações
- **Descreve o passado; não prevê.** "Emergente" não garante viralização.
- Crescimento ≠ viralização: um pico passageiro também "cresce".
- **Sazonalidade** não é calculada antes de 2 anos de dados: com 1 ano não se
  distingue Black Friday de tendência. Ex.: o "playstation" real tem pico em
  23/11/2025 — semana da Black Friday.
- Comparação **entre plataformas e países**: a estrutura separa séries por
  fonte e país, mas a comparação fica para quando houver uma segunda fonte.
- Escalas relativas de exportações diferentes não são comparadas entre si.
- Indicadores são calculados na hora (não armazenados); para comparar
  períodos, exporte com `--csv` e guarde o arquivo.
