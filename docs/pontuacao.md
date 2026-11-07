# Pontuação de potencial de tendência (Etapa 6)

    pontuação = 100 × Σ (peso_i × nota_i) / Σ peso_i        nota_i ∈ [0, 1]

Configuração: `config/pontuacao.toml`. Código: `radar_viral/scoring/`.

> A pontuação **resume sinais observados no passado**. Não é probabilidade
> nem garantia de viralização.

## Critérios

| Critério | Peso padrão | Como a nota (0–1) é calculada | Fonte hoje |
|---|---|---|---|
| velocidade | 25 | média de: crescimento % normalizado (−50%→0, +100%→1) e velocidade %/sem normalizada (−10→0, +20→1) | Google Trends |
| aceleracao | 15 | aceleração p.p./sem normalizada (−10→0, 0→0,5, +10→1) | Google Trends |
| persistencia | 15 | média de: consistência (fração de semanas subindo) e proximidade do pico (1 + queda%/100) | Google Trends |
| multiplataforma | 10 | fração das fontes em que a família está crescendo | **precisa de 2+ fontes** |
| engajamento | 10 | — | sem fonte |
| intencao_compra | 10 | — | sem fonte |
| concorrencia | 5 | — | sem fonte |
| sazonalidade | 5 | — | precisa de 2 anos |
| potencial_comercial | 5 | — | sem fonte |

Todos os indicadores usam a `janela_principal` (padrão 90 dias). Com dados
semanais, 14 dias = 2 pontos: sem velocidade/aceleração (precisam de 3).

## Critérios sem dados
- `neutro` (padrão): contam como 0,5. Com só o Google Trends, 55% do peso
  tem dados, então a pontuação fica entre **27,5 e 77,5**. Nota extrema exige
  evidência em muitos critérios — isso é intencional.
- `renormalizar`: ignorados; os pesos restantes são reescalados. A nota pode
  ir de 0 a 100 com pouca evidência — use junto com a confiança.

## Teto para pico passageiro
Pico passageiro (cresceu, mas o último valor está 40%+ abaixo do pico) tem
pontuação máxima de 40 (`[tetos]`). Foi escolhido teto em vez de subtrair
pontos fixos: no teste, um pico forte com −15 pontos (46,8) ainda ficava
acima de um produto estável (45,0).

## Confiança (0–100) — separada da pontuação
    confiança = 100 × cobertura × qualidade
- cobertura = peso dos critérios com dados ÷ peso total
- qualidade = suficiência (pontos ÷ 4×períodos da janela, máx. 1)
            × completude (1 − lacunas)
            × força do sinal (0,5 se base baixa)

A qualidade dos dados **não** aumenta a pontuação: dados ótimos de um
produto parado não o tornam promissor. Ela afeta só a confiança.

## Limitações
- Pesos, faixas e teto são escolhas iniciais, não calibradas: só serão
  avaliados com histórico real (quais produtos de fato cresceram depois).
- Com uma única fonte, a pontuação mede basicamente "interesse de busca
  crescente"; não diz nada sobre vendas, concorrência ou margem.
- Escalas relativas: a pontuação usa a exportação mais recente de cada família.
- Normalização linear com limites fixos: crescimentos acima de +100% recebem
  a mesma nota.
