# Tipos de tendência (Etapa 11)

Configuração: `config/tendencias.toml`. Código: `radar_viral/analysis/trend_types.py`.

| Tipo | Definição (valores padrão) | Fases |
|---|---|---|
| **Tendência sustentada** | em alta (≥ 50% acima da linha de base) há **≥ 8 semanas** | **em alta**: último valor no máximo 30% abaixo do pico (a sua definição) · **perdendo força**: caiu mais que isso |
| **Alta súbita** | chegou a **≥ 2× a linha de base em até 3 semanas** e está em alta há **< 8 semanas** | **em alta** · **já caindo**: ≥ 40% abaixo do pico (inclui picos que já voltaram à base) |
| **Sazonal** | *pendente*: precisa de exports de 5 anos (formato ainda não confirmado) | — |
| sem tendência definida | nenhum dos anteriores | — |

Uma alta súbita que se mantém por 8 semanas passa a ser tendência sustentada:
acompanhar essa mudança semana a semana é um dos sinais mais valiosos.

## Como a linha de base é calculada
Para cada semana candidata a "início da alta": linha de base = **mediana das 12
semanas anteriores**; o período até hoje conta como "alta" se a semana de início
e ≥ 80% das seguintes estão ≥ 50% acima da base (tolera semanas de queda).
Fica o início **mais antigo** válido = há quanto tempo está em alta.

Mediana em vez de média: não é puxada por uma semana fora do padrão.
Base mínima de 5 (Google Trends): de 1 para 3 é "3×", mas é ruído.

## Dados necessários
- Export de 12 meses (semanal): suficiente.
- Export de 30 dias (diário): insuficiente (a base sozinha exige 12 semanas).
- O tipo usa a série mais longa da família.

## Tipo × pontuação
São perguntas diferentes:
- **Pontuação** (Etapa 6): está acelerando AGORA (janela atual × anterior)?
- **Tipo**: qual o FORMATO da alta ao longo do ano?

Uma tendência sustentada que já se estabilizou num patamar alto "parou de
acelerar" e pode ter pontuação média — use a aba **Sustentadas** para vê-las.

## Limitações
- Valores iniciais, não calibrados com casos reais.
- Uma alta que começou antes do início do export (há mais de ~40 semanas num
  export de 12 meses) não tem linha de base: o produto aparece como estável.
- Sem sazonalidade ainda: um pico de Black Friday aparece como "alta súbita".
