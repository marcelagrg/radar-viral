"""Painel do Radar Viral (Streamlit).

Rodar (na raiz do projeto):   streamlit run dashboard/app.py

Este arquivo só cuida da INTERFACE. Os cálculos ficam em radar_viral/
(ui/data.py prepara as tabelas). O Streamlit executa este script de cima a
baixo a cada interação; por isso os dados ficam em cache (st.cache_data).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from radar_viral.config import load_settings  # noqa: E402
from radar_viral.marketplaces import MARKETPLACES, save_link, search_links  # noqa: E402
from radar_viral.storage import repository as repo  # noqa: E402
from radar_viral.analysis.trend_types import SUBITA, SUSTENTADA, TrendConfigError, load_trend_config  # noqa: E402
from radar_viral.scoring.config import ScoringConfigError, load_scoring_config  # noqa: E402
from radar_viral.storage.database import SchemaOutdatedError, get_engine, init_db  # noqa: E402
from radar_viral.ui import data as ui  # noqa: E402

LABELS = {
    "velocidade": "Velocidade", "aceleracao": "Aceleração", "persistencia": "Persistência",
    "multiplataforma": "Multiplataforma", "engajamento": "Engajamento",
    "intencao_compra": "Intenção de compra", "concorrencia": "Concorrência",
    "sazonalidade": "Sazonalidade", "potencial_comercial": "Potencial comercial",
}
DISCLAIMER = "A pontuação resume sinais observados no passado. **Não é previsão nem garantia de viralização.**"

st.set_page_config(page_title="Radar Viral", page_icon="📡", layout="wide")


# ------------------------------------------------------------------ dados

@st.cache_resource
def engine_for(url: str):
    engine = get_engine(url)
    init_db(engine)
    return engine


@st.cache_data(ttl=300, show_spinner="Calculando indicadores...")
def cached_dashboard(url: str, window: int, include_simulated: bool):
    # Os argumentos formam a "chave" do cache: mudou a janela, recalcula.
    return ui.load_dashboard(engine_for(url), load_scoring_config(), window, include_simulated)


def as_text(df, formats: dict[str, str]):
    """Converte colunas numéricas em texto formatado, com '—' nos vazios.

    A tabela do Streamlit escreve 'None' em qualquer valor ausente (testamos
    NaN e o Styler do Pandas, sem efeito). Em tabelas pequenas, que ninguém
    ordena, texto formatado resolve. NÃO use no ranking: a ordenação ao clicar
    no cabeçalho passaria a ser alfabética ("9" > "10").
    """
    df = df.copy()
    for col, fmt in formats.items():
        df[col] = df[col].map(lambda v: "—" if v is None or v != v else fmt.format(v))
    return df


def link_count(counts: dict[int, int], family_id) -> int:
    """family_id vem do Pandas: pode ser float (ex.: 3.0) ou NaN quando o termo não tem família."""
    if family_id is None or pd.isna(family_id):
        return 0
    return counts.get(int(family_id), 0)


def fmt_pct(v):
    return "—" if v is None or v != v else f"{v:+.1f}%"


# ------------------------------------------------------------------ gráfico

def line_chart(df, title: str, y_title: str):
    """Linha de 2px + linha-guia e tooltip no ponto mais próximo do cursor."""
    nearest = alt.selection_point(nearest=True, on="pointerover", fields=["data"], empty=False)
    base = alt.Chart(df).encode(
        x=alt.X("data:T", title=None, axis=alt.Axis(format="%d/%m/%y", grid=False)),
        y=alt.Y("valor:Q", title=y_title),
    )
    line = base.mark_line(strokeWidth=2, strokeCap="round", strokeJoin="round")
    hit = base.mark_point(size=400, opacity=0).encode(  # alvos invisíveis, maiores que o ponto
        tooltip=[alt.Tooltip("data:T", title="Semana de", format="%d/%m/%Y"),
                 alt.Tooltip("valor:Q", title="Valor", format=".1f")]
    ).add_params(nearest)
    rule = base.mark_rule(strokeWidth=1, color="#8a8984").encode(
        opacity=alt.condition(nearest, alt.value(0.7), alt.value(0))
    )
    dot = base.mark_point(filled=True, size=70, stroke="white", strokeWidth=2).encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    )
    return alt.layer(line, rule, dot, hit).properties(title=title, height=320)


# ------------------------------------------------------------------ componentes

RANKING_COLUMNS = {
    "familia": st.column_config.TextColumn("Família"),
    "familia_id": None,  # None = coluna oculta
    "links": st.column_config.NumberColumn("Links de compra", format="%d"),
    "pais": st.column_config.TextColumn("País", width="small"),
    "pontuacao": st.column_config.ProgressColumn("Pontuação", min_value=0, max_value=100, format="%.1f"),
    "confianca": st.column_config.ProgressColumn("Confiança", min_value=0, max_value=100, format="%.0f"),
    "classificacao": st.column_config.TextColumn("Classificação"),
    "tipo": st.column_config.TextColumn("Tipo de tendência"),
    # Numérica de propósito (ordenação correta); vazios aparecem como "None".
    "crescimento_pct": st.column_config.NumberColumn("Crescimento", format="%+.1f%%"),
    "categoria": st.column_config.TextColumn("Categoria"),
    "fontes": st.column_config.TextColumn("Fontes", width="medium"),
    "ultima_data": st.column_config.DateColumn("Último dado", format="DD/MM/YYYY"),
    "link": st.column_config.LinkColumn("Fonte original", display_text="abrir"),
}


def ranking_table(df, key: str):
    if df.empty:
        st.info("Nenhuma família nesta visão com os filtros atuais.")
        return
    # Células vazias: "—" em texto (o Streamlit mostraria "None").
    df = df.copy()
    for col in ("categoria", "classificacao"):
        df[col] = df[col].fillna("—")
    event = st.dataframe(
        df, column_config=RANKING_COLUMNS, hide_index=True, width="stretch",
        on_select="rerun", selection_mode="single-row", key=key,
    )
    rows = event.selection.rows if event and event.selection else []
    if rows:
        chosen = df.iloc[rows[0]]
        st.session_state["familia_escolhida"] = f"{chosen['familia']} [{chosen['pais']}]"
        st.caption(f"Selecionado: **{chosen['familia']}** — veja a aba **Detalhes**.")


def detail_page(d: ui.DashboardData, ranking, cfg, engine):
    options = [f"{r.familia} [{r.pais}]" for r in ranking.itertuples()]
    if not options:
        st.info("Nenhuma família com os filtros atuais.")
        return
    chosen = st.session_state.get("familia_escolhida")
    label = st.selectbox("Família", options, index=options.index(chosen) if chosen in options else 0)
    family, country = label.rsplit(" [", 1)
    key = (family, country.rstrip("]"))
    result, series_list = d.scores[key], d.latest[key]

    c1, c2, c3 = st.columns(3)
    c1.metric("Pontuação", f"{result.score:.1f}")
    c2.metric("Confiança", f"{result.confidence:.0f}")
    c3.metric("Qualidade dos dados", f"{result.quality:.2f}")
    # Texto longo não cabe num st.metric (fica cortado); vai numa linha própria.
    st.markdown(f"**Classificação ({d.main_window} dias):** {result.classification}")
    t = d.trend_types.get(key)
    if t:
        st.markdown(f"**Tipo de tendência:** {ui.type_label(t)} — {t.explicacao}")
    st.caption(DISCLAIMER)

    family_id = next((s.family_id for s in series_list if s.family_id is not None), None)
    where_to_buy(engine, family, family_id)

    for s in series_list:
        st.subheader(f"Evolução — {s.source_code} ({s.frequency})")
        first, last = s.data.index[0].date(), s.data.index[-1].date()
        if first < last:
            start, end = st.slider("Período do gráfico", min_value=first, max_value=last, value=(first, last),
                                   format="DD/MM/YYYY", key=f"periodo_{label}_{s.source_code}")
        else:
            start, end = first, last
        frame = ui.series_frame(s, start, end)
        y_title = ui.METRIC_LABELS.get(s.metric, s.metric)
        st.altair_chart(line_chart(frame, f"{family} ({s.frequency})", y_title), width="stretch")
        st.caption(
            f"{len(s.data)} pontos de {first:%d/%m/%Y} a {last:%d/%m/%Y} · lacunas: {s.gaps} · "
            f"termos: {', '.join(s.terms)}" + (f" · coleta #{s.run_id}" if s.run_id else "")
        )
        with st.expander("Ver os dados em tabela"):
            st.dataframe(frame, hide_index=True, width="stretch",
                         column_config={"data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")})

        st.markdown("**Comparação entre períodos** (janela atual × anterior)")
        windows = as_text(ui.windows_table(s), {
            "semanas_ou_pontos": "{:.0f}", "media_atual": "{:.1f}", "media_anterior": "{:.1f}",
            "crescimento_pct": "{:+.1f}%", "velocidade_pct_sem": "{:+.1f}", "aceleracao_pp": "{:+.1f}",
            "consistencia": "{:.2f}",
        })
        st.dataframe(windows, hide_index=True, width="stretch", column_config={
            "janela": "Janela", "semanas_ou_pontos": "Pontos", "media_atual": "Média atual",
            "media_anterior": "Média anterior", "crescimento_pct": "Crescimento",
            "velocidade_pct_sem": "Velocidade (%/sem)", "aceleracao_pp": "Aceleração (p.p.)",
            "consistencia": "Consistência", "classificacao": "Classificação",
        })

    st.subheader("Como a pontuação foi calculada")
    contrib = ui.contributions_table(result, cfg)
    contrib["criterio"] = contrib["criterio"].map(lambda c: LABELS.get(c, c))
    st.dataframe(as_text(contrib, {"peso_pct": "{:.0f}%", "nota": "{:.2f}", "pontos": "{:+.1f}"}),
                 hide_index=True, width="stretch", column_config={
        "criterio": "Critério", "peso_pct": "Peso", "nota": "Nota (0–1)", "pontos": "Pontos",
        "sem_dados": st.column_config.CheckboxColumn("Sem dados"),
    })
    if result.missing:
        st.caption("Critérios sem dados contam como "
                   + (f"neutros ({cfg.neutral_value})." if cfg.missing_strategy == "neutro" else "excluídos.")
                   + " Detalhes: docs/pontuacao.md")

    link = d.links.get(key)
    if link:
        st.link_button("Abrir a consulta original", link)

    # 'is' compara a identidade do objeto; '==' compararia os dados do Pandas e daria erro
    others = [s for s in d.all_series.get(key, []) if all(s is not x for x in series_list)]
    if others:
        with st.expander(f"Outras exportações ({len(others)}) — escalas diferentes, não compare os valores"):
            for s in others:
                st.altair_chart(line_chart(ui.series_frame(s), f"Coleta #{s.run_id}", "valor"),
                                width="stretch")


def where_to_buy(engine, family: str, family_id: int | None):
    """Links de compra que você cadastrou + buscas prontas nos marketplaces."""
    st.subheader("Onde comprar")
    if family_id is None:
        st.info("Este termo ainda não tem família. Rode `python scripts\\families.py agrupar` para cadastrar links.")
    else:
        links = repo.list_links(engine, family_id)
        if not links:
            st.caption("Nenhum link cadastrado para esta família. Adicione abaixo.")
        cols = st.columns(len(MARKETPLACES))
        for col, mp in zip(cols, MARKETPLACES.values()):
            with col:
                st.markdown(f"**{mp.name}**")
                mp_links = [x for x in links if x["marketplace"] == mp.code]
                if not mp_links:
                    st.caption("nenhum link")
                for link in mp_links:
                    st.link_button(link["label"] or "Ver produto", link["url"], width="stretch")
                    if st.button("Remover", key=f"rm_link_{link['id']}", type="tertiary"):
                        repo.delete_link(engine, link["id"])
                        st.rerun()

        with st.expander("Adicionar link de produto"):
            with st.form(f"novo_link_{family_id}", clear_on_submit=True):
                code = st.selectbox("Marketplace", list(MARKETPLACES), format_func=lambda c: MARKETPLACES[c].name)
                url = st.text_input("Link do produto (https://...)")
                label = st.text_input("Descrição (opcional)", placeholder="ex.: kit com 2 unidades")
                if st.form_submit_button("Salvar link"):
                    try:
                        save_link(engine, family_id, code, url, label)
                        st.success("Link salvo.")
                        st.rerun()
                    except ValueError as exc:
                        st.error(f"Não foi possível salvar: {exc}")

    st.markdown("**Buscar nos marketplaces** (abre a busca no site; não é um produto específico)")
    for col, (name, url) in zip(st.columns(len(MARKETPLACES)), search_links(family).items()):
        col.link_button(f"Buscar na {name}" if name != "Mercado Livre" else "Buscar no Mercado Livre", url,
                        width="stretch")


# ------------------------------------------------------------------ página

def main():
    try:
        settings = load_settings()
        cfg = load_scoring_config()
        load_trend_config()  # valida config/tendencias.toml logo no início
        engine = engine_for(settings.database_url)
    except (ValueError, ScoringConfigError, TrendConfigError, SchemaOutdatedError) as exc:
        st.error(f"Erro de configuração: {exc}")
        st.stop()

    with st.sidebar:
        st.header("Filtros")
        window = st.selectbox("Janela de análise", ui.WINDOWS_DAYS, index=ui.WINDOWS_DAYS.index(cfg.main_window),
                              format_func=lambda w: f"{w} dias")
        include_sim = st.toggle("Incluir dados SIMULADOS", value=False)

    d = cached_dashboard(settings.database_url, window, include_sim)

    st.title("📡 Radar Viral")
    updated = f"{d.last_update:%d/%m/%Y %H:%M} (UTC)" if d.last_update else "nunca"
    st.caption(f"Última importação: {updated} · janela: {d.main_window} dias · {DISCLAIMER}")
    if include_sim:
        st.warning("Dados SIMULADOS incluídos: os resultados abaixo NÃO representam o mercado real.")
    if d.ranking.empty:
        st.info("Ainda não há dados. Importe um arquivo (ex.: `python scripts\\import_google_trends.py ...`) "
                "e agrupe as famílias (`python scripts\\families.py agrupar`).")
        st.stop()

    with st.sidebar:
        todos = "Todos"
        countries = st.multiselect("País", d.countries, placeholder=todos)
        sources = st.multiselect("Fonte", d.sources, placeholder=todos)
        types = st.multiselect("Tipo de tendência", [SUSTENTADA, SUBITA], placeholder=todos)
        classes = st.multiselect("Classificação", sorted(d.ranking["classificacao"].unique()), placeholder=todos)
        cats_available = sorted(d.ranking["categoria"].dropna().unique())
        categories = st.multiselect("Categoria", cats_available, placeholder=todos) if cats_available else []
        min_score = st.slider("Pontuação mínima", 0, 100, 0)
        min_conf = st.slider("Confiança mínima", 0, 100, 0)
        search = st.text_input("Buscar família")
        if st.button("Recarregar dados"):
            st.cache_data.clear()
            st.rerun()

    ranking = ui.filter_ranking(d.ranking, countries, sources, classes, categories, min_score, min_conf, search,
                                types=types)
    # Contagem de links lida na hora (fora do cache): muda quando você salva um link.
    counts = repo.count_links_by_family(engine)
    ranking = ranking.assign(links=ranking["familia_id"].map(lambda f: link_count(counts, f)))

    tabs = st.tabs(["Ranking", "Sustentadas", "Altas súbitas", *ui.TAB_GROUPS, "Categorias", "Detalhes"])
    with tabs[0]:
        st.caption(f"{len(ranking)} família(s). Clique numa linha para ver os detalhes.")
        ranking_table(ranking, "tab_ranking")
    with tabs[1]:
        st.caption("Cresceram e continuam em alta há pelo menos 8 semanas (ajustável em config/tendencias.toml).")
        ranking_table(ranking[ranking["tipo"].str.startswith(SUSTENTADA)], "tab_sustentadas")
    with tabs[2]:
        st.caption("Alta expressiva e rápida, há menos de 8 semanas: oportunidade rápida, risco de queda.")
        ranking_table(ranking[ranking["tipo"].str.startswith(SUBITA)], "tab_subitas")
    for tab, (name, group) in zip(tabs[3:6], ui.TAB_GROUPS.items()):
        with tab:
            ranking_table(ranking[ranking["classificacao"].isin(group)], f"tab_{name}")
    with tabs[6]:
        if d.categories.empty:
            st.info("Nenhuma fonte importada informa categoria (o Google Trends não informa). "
                    "Use a coluna `categoria` no CSV padrão para ver esta visão.")
        else:
            st.dataframe(d.categories, hide_index=True, width="stretch", column_config={
                "categoria": "Categoria", "familias": "Famílias", "em_crescimento": "Em crescimento",
                "pontuacao_media": st.column_config.NumberColumn("Pontuação média", format="%.1f"),
            })
    with tabs[7]:
        detail_page(d, ranking, cfg, engine)


main()
