"""Definição das tabelas (o "esquema" do banco).

Usamos SQLAlchemy Core: descrevemos as tabelas em Python e o SQLAlchemy gera
o SQL correto para SQLite hoje e para PostgreSQL no futuro.

Princípio central: a tabela observations é "somente acréscimo" (append-only).
Nunca sobrescrevemos uma coleta antiga; cada coleta gera novas linhas. É isso
que permite medir crescimento ao longo do tempo.
"""

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()

# Catálogo de fontes de dados (Mercado Livre, Google Trends, ...).
sources = Table(
    "sources",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(50), nullable=False, unique=True),  # ex.: "mercadolivre"
    Column("name", String(100), nullable=False),
    Column("base_url", String(255)),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

# Cada execução de um coletor. Permite saber quando coletamos, se deu certo
# e quantos itens vieram — essencial para auditar a qualidade dos dados.
collection_runs = Table(
    "collection_runs",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("source_id", Integer, ForeignKey("sources.id"), nullable=False),
    Column("country", String(2), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("status", String(20), nullable=False),  # running | success | partial | failed
    Column("items_collected", Integer, nullable=False, default=0),
    Column("error_message", Text),
    # Preenchidos quando a coleta é a importação de um arquivo (Etapa 2).
    # O hash SHA-256 é a "impressão digital" do conteúdo: impede importar
    # o mesmo arquivo duas vezes e duplicar o histórico.
    Column("source_file", String(255)),
    Column("file_sha256", String(64), index=True),
)

# O histórico propriamente dito: uma linha por item por coleta.
observations = Table(
    "observations",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("run_id", Integer, ForeignKey("collection_runs.id"), nullable=False),
    Column("source_id", Integer, ForeignKey("sources.id"), nullable=False),
    Column("collected_at", DateTime(timezone=True), nullable=False),
    # Data a que o valor se refere. Difere de collected_at quando importamos
    # séries históricas: um CSV baixado hoje pode trazer dados de 2024.
    Column("reference_date", Date),
    Column("country", String(2), nullable=False),
    Column("term", String(500), nullable=False),
    Column("external_id", String(100)),
    Column("category_id", String(50)),
    Column("category_name", String(200)),
    Column("rank_position", Integer),
    Column("search_volume", Float),
    Column("popularity_value", Float),
    Column("popularity_metric", String(50)),
    Column("price", Float),
    Column("currency", String(3)),
    Column("url", String(1000)),
    Column("is_simulated", Boolean, nullable=False, default=False),
    Column("raw_payload", JSON),  # resposta original da fonte, para reprocessar depois
    # Índices aceleram as consultas mais comuns: histórico de um termo e
    # tudo que uma fonte coletou num período.
    Index("ix_obs_term_collected", "term", "collected_at"),
    Index("ix_obs_term_reference", "term", "reference_date"),
    Index("ix_obs_source_collected", "source_id", "collected_at"),
)


# ----------------------------------------------------------- Etapa 4
# Família de produtos: agrupa termos diferentes que representam o mesmo produto
# ("mini aspirador portátil", "mini aspiradores portáteis"...).
product_families = Table(
    "product_families",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(200), nullable=False, unique=True),
    Column("created_by", String(10), nullable=False),  # auto | manual
    Column("created_at", DateTime(timezone=True), nullable=False),
)

# A qual família cada termo pertence (um termo = uma família).
# method="manual" significa correção feita por você: o agrupamento automático
# NUNCA altera essas linhas.
term_families = Table(
    "term_families",
    metadata,
    Column("term", String(500), primary_key=True),
    Column("family_id", Integer, ForeignKey("product_families.id"), nullable=False, index=True),
    Column("method", String(10), nullable=False),  # auto | manual
    Column("similarity", Float),  # similaridade média com a família no momento da atribuição
    Column("assigned_at", DateTime(timezone=True), nullable=False),
)


# ----------------------------------------------------------- Etapa 8
# Links de compra que VOCÊ insere para cada família (Amazon, Shopee,
# Mercado Livre...). Uma família com links fica protegida: o agrupamento
# automático (--refazer) não a desfaz.
product_links = Table(
    "product_links",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("family_id", Integer, ForeignKey("product_families.id"), nullable=False, index=True),
    Column("marketplace", String(30), nullable=False),  # amazon | shopee | mercadolivre
    Column("url", String(1000), nullable=False),
    Column("label", String(200)),  # descrição opcional, ex.: "kit com 2 unidades"
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("family_id", "url", name="uq_link_family_url"),
)
