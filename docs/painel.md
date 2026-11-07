# Painel (Etapa 7)

    streamlit run dashboard/app.py

Abre em http://localhost:8501. Para parar: `Ctrl+C` no terminal.

## Organização
- `dashboard/app.py` — só interface (Streamlit).
- `radar_viral/ui/data.py` — prepara as tabelas; testável sem navegador.
- `.streamlit/config.toml` — tema (azul, claro e escuro).

## O que o painel mostra
| Área | Conteúdo |
|---|---|
| Barra lateral | janela (7/14/30/90 dias), simulados, país, fonte, classificação, categoria, pontuação e confiança mínimas, busca |
| Ranking | todas as famílias por pontuação, com confiança, crescimento, último dado e link da fonte |
| Emergentes / Em crescimento / Em desaceleração | o ranking filtrado por classificação (desaceleração inclui queda e pico passageiro) |
| Categorias | famílias por categoria — só aparece se alguma fonte informa categoria (o Google Trends não informa) |
| Detalhes | métricas, gráfico com período ajustável e tooltip, dados em tabela, comparação entre janelas, cálculo da pontuação, link da consulta original, exportações anteriores |

## Decisões
- **Uma série por gráfico.** Exportações diferentes do Google Trends têm escalas
  diferentes e nunca são desenhadas no mesmo eixo; as antigas ficam num bloco
  separado, com aviso.
- **Cache de 5 minutos** (`st.cache_data`): o Streamlit reexecuta o script a cada
  clique; o cache evita recalcular tudo. Botão "Recarregar dados" limpa o cache
  depois de uma importação.
- **Azul como cor principal**: vermelho (padrão do Streamlit) sugere alerta.
- Dados simulados só aparecem com o interruptor ligado, com aviso fixo no topo.

## Limitações conhecidas
- Na coluna Crescimento do ranking, valores ausentes aparecem como "None"
  (comportamento da tabela do Streamlit; manter a coluna numérica preserva a
  ordenação correta).
- Clicar numa linha do ranking escolhe a família, mas a troca para a aba
  Detalhes é manual (o Streamlit não muda de aba por código).
- Horários em UTC.
