# Famílias de produtos (Etapa 4)

Agrupa termos diferentes que representam o mesmo produto, para que a análise
some os sinais de "mini aspirador portátil" e "mini aspiradores portáteis".

## Como funciona — três camadas
1. **Regras** (`processing/text_normalizer.py`): minúsculas, sem acentos, sem
   pontuação, sem palavras de enchimento (`kit`, `promoção`, `de`, `para`...).
   Termos com **números de modelo diferentes** nunca se juntam (PS4 ≠ PS5).
2. **Similaridade de texto** (`processing/product_families.py`): TF-IDF de
   pedaços de 3–5 letras + similaridade de cosseno + agrupamento hierárquico
   (average linkage). Dois termos ficam juntos quando a similaridade média do
   grupo é ≥ `FAMILY_SIMILARITY_THRESHOLD` (padrão 0,45).
3. **Correção manual** (`scripts/families.py mover`): sempre vence o automático.

## Comandos
    python scripts\families.py agrupar            # termos novos
    python scripts\families.py agrupar --refazer  # recalcula o automático
    python scripts\families.py listar
    python scripts\families.py mover "termo" "família"
    python scripts\families.py renomear "nome atual" "novo nome"

## Regras de comportamento
- **Incremental**: termos já agrupados não mudam de família; o id da família é
  estável (importante para pontuação e painel nas próximas etapas).
- `--refazer` recalcula só famílias **sem** correção manual. Uma família que
  você corrigiu fica congelada inteira.
- Termos simulados ficam de fora, a menos que use `--incluir-simulados`.

## Limitações (medidas com exemplos, não suposições)
| Caso | Similaridade | Resultado |
|---|---|---|
| mini aspirador portátil × Mini Aspiradores Portáteis | 0,62 | junta ✔ |
| mini aspirador portátil × aspirador portátil para teclado | 0,68 | junta ✔ |
| mini aspirador portátil × aspirador de mesa USB | 0,37 | separa ✘ (mesmo produto) |
| aspirador de mesa USB × aspirador de pó vertical | 0,35 | separa ✔ |
| playstation 4 × playstation 5 | 0,94 | separa ✔ (regra de números) |
| controle ps5 × playstation 5 | ~0 | separa (abreviação desconhecida) |

- Compara **letras, não significado**: sinônimos e descrições diferentes do
  mesmo produto ("mesa USB" × "mini portátil") não são reconhecidos.
- Não reconhece **outros idiomas** ("vacuum cleaner" × "aspirador") — relevante
  para comparar países no futuro.
- A similaridade depende do conjunto de termos (o IDF é recalculado a cada vez).
- Memória cresce com N² termos: adequado até alguns milhares de termos.

## Quando usar outras técnicas
| Técnica | Quando | Custo |
|---|---|---|
| Regras / dicionário de sinônimos (`ps5 → playstation 5`) | poucos casos recorrentes | zero |
| Embeddings (modelos que representam significado) | muitos sinônimos ou vários idiomas | grátis local, mas modelo de centenas de MB |
| IA generativa | revisar casos ambíguos | pago por uso |

A decisão deve vir de **medição com termos reais**: quantas famílias você
precisou corrigir manualmente.
