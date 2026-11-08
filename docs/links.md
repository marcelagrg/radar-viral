# Links de compra (Etapa 8)

Para cada família de produto, você cadastra links da Amazon, Shopee e
Mercado Livre (inclusive links de afiliado). Eles aparecem no painel, na aba
**Detalhes → Onde comprar**, e a quantidade aparece no ranking.

## Pelo painel
Detalhes → escolha a família → **Adicionar link de produto** → marketplace,
link e descrição opcional → **Salvar link**. Para apagar: **Remover**.

## Pelo terminal
    python scripts\links.py adicionar "playstation" shopee "https://shopee.com.br/..." --rotulo "PS5 Slim"
    python scripts\links.py listar
    python scripts\links.py listar --familia playstation
    python scripts\links.py remover 3
    python scripts\links.py buscar "mini aspirador"     # só mostra links de busca

## Regras
- Só `https://` e só domínios do marketplace escolhido (e subdomínios):
  Amazon `amazon.com.br`, `amzn.to`; Shopee `shopee.com.br`;
  Mercado Livre `mercadolivre.com.br`, `mercadolivre.com`.
  Imitações como `amazon.com.br.golpe.com` são recusadas.
  Para aceitar outro domínio, edite `MARKETPLACES` em `radar_viral/marketplaces.py`.
- O mesmo link não pode ser cadastrado duas vezes na mesma família.
- Uma família com links fica **protegida**: `families.py agrupar --refazer` não a
  desfaz (os links seriam perdidos).
- Os links são da família, não de um termo: renomear a família não os afeta.

## Links de busca
O painel também mostra "Buscar na Amazon/Shopee/Mercado Livre" com o nome da
família. São apenas endereços de busca abertos no seu navegador: o Radar não
acessa nem lê esses sites.

## Limitações
- O sistema não verifica se o link funciona, nem preço ou estoque.
- Links quebram quando o anúncio sai do ar; revise de tempos em tempos.
