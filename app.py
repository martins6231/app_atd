# streamlit_britvic_mobile.py
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import io
from prophet import Prophet
import calendar
from datetime import datetime

# --------------------- CONFIG STREAMLIT PARA MOBILE E VISUAL MODERNO ---------------------
# Layout centralizado para melhor usabilidade mobile; tema escuro será respeitado pelo sistema da plataforma;
st.set_page_config(
    page_title="Acompanhamento Britvic",
    layout="centered",
    initial_sidebar_state="expanded"
)
# CSS responsivo para ampliar toques e melhorar visual em telas pequenas:
st.markdown("""
    <style>
        /* Ajuste tamanhos e espaços para mobile */
        .block-container { max-width: 700px; padding: 1.3rem 0.6rem 0.7rem 0.6rem;}
        header, footer {display: none;}
        [data-testid="stSidebar"] {min-width:145px; width: 85vw;}
        .stButton>button, .stDownloadButton>button {
            font-size:1.10rem; border-radius: 8px; padding: 0.6em 2em; margin: 0.15em 0.4em;
        }
        .stExpanderHeader {font-size:1.12rem;}
        .stMetric {min-width:120px !important;}
        .stSelectbox>div>div, .stMultiSelect>div>div {font-size:1.07rem;}
        /* Barra de navegação fixa */
        .mobile-header {
            position:fixed; top:0; left:0; right:0; height:2.7rem; z-index:99999;
            background:linear-gradient(100deg, #00ADD8 80%, #5B5F97 100%);
            color:white; display:flex; align-items:center; justify-content:center;
            box-shadow: 0 2px 10px #2222;
            font-size:1.16rem; font-weight:700; letter-spacing:0.04em;
        }
        .page-title {margin-top:3.2rem;}
    </style>
""", unsafe_allow_html=True)
# ---- Barra de navegação superior em formato mobile ----
st.markdown('<div class="mobile-header">🔎 Acompanhamento de Produção Britvic</div>', unsafe_allow_html=True)
st.markdown('<div class="page-title"></div>', unsafe_allow_html=True)

def nome_mes(numero):
    return calendar.month_abbr[int(numero)]

# ------------ SIDEBAR (CONTRASTANTE, ÍCONES, AMIGÁVEL PARA TOUCH) ------------
with st.sidebar:
    st.markdown("## ⚙️ Configurações")
    st.markdown(
        '<span style="font-size:0.97rem;">Carregue sua planilha <b>.xlsx</b> de produção (colunas obrigatórias: <b>categoria, data, caixas_produzidas</b>).</span>',
        unsafe_allow_html=True
    )
    upload = st.file_uploader(
        "Selecione o arquivo Excel...",
        type="xlsx",
        accept_multiple_files=False,
        help="Envie arquivo Excel com dados da produção"
    )

# ------------ LEITURA E LIMPEZA DO ARQUIVO -----------------
@st.cache_data(show_spinner="Carregando dados...")
def carregar_dados(uploaded_file):
    try:
        df = pd.read_excel(uploaded_file, engine='openpyxl')
        return df
    except Exception as e:
        st.error(f"Erro ao ler a planilha: {e}")
        return None

if not upload:
    st.warning("Envie o arquivo de dados para continuar.")
    st.stop()
df_raw = carregar_dados(upload)

def tratar_dados(df):
    erros = []
    df = df.rename(columns=lambda x: x.strip().lower().replace(" ", "_"))
    obrigatorias = ['categoria', 'data', 'caixas_produzidas']
    for col in obrigatorias:
        if col not in df.columns:
            erros.append(f"Coluna obrigatória ausente: {col}")
    # Converte datas
    try:
        df['data'] = pd.to_datetime(df['data'])
    except Exception:
        erros.append("Erro ao converter coluna 'data'.")
    na_count = df.isna().sum()
    for col, qtd in na_count.items():
        if qtd > 0:
            erros.append(f"Coluna '{col}' com {qtd} valores ausentes.")
    negativos = (df['caixas_produzidas'] < 0).sum()
    if negativos > 0:
        erros.append(f"{negativos} registros negativos em 'caixas_produzidas'.")
    df_clean = df.dropna(subset=['categoria','data','caixas_produzidas']).copy()
    df_clean['caixas_produzidas'] = pd.to_numeric(df_clean['caixas_produzidas'], errors='coerce').fillna(0).astype(int)
    df_clean = df_clean[df_clean['caixas_produzidas'] >= 0]
    df_clean = df_clean.drop_duplicates(subset=['categoria','data'], keep='first')
    return df_clean, erros

df, erros = tratar_dados(df_raw)
# ----------------------------------------- Relatório Expandido -----------------------------------------
with st.expander("📋 Relatório de problemas encontrados", expanded=len(erros)>0):
    if erros:
        for e in erros: st.warning(e)
    else:
        st.success("Nenhum problema crítico encontrado.")

# ------------- FUNÇÕES DE SELEÇÃO E FILTRAGEM -----------------
def selecionar_categoria(df):
    return sorted(df['categoria'].dropna().unique())

def dataset_ano_mes(df, categoria=None):
    df_filt = df if categoria is None else df[df['categoria'] == categoria]
    df_filt['ano'] = df_filt['data'].dt.year
    df_filt['mes'] = df_filt['data'].dt.month
    return df_filt

def filtrar_periodo(df, categoria, anos_selecionados, meses_selecionados):
    cond = (df['categoria'] == categoria)
    if anos_selecionados:
        cond &= (df['data'].dt.year.isin(anos_selecionados))
    if meses_selecionados:
        cond &= (df['data'].dt.month.isin(meses_selecionados))
    return df[cond].copy()

def gerar_dataset_modelo(df, categoria=None):
    df_cat = df[df['categoria'] == categoria] if categoria else df
    grupo = df_cat.groupby('data')['caixas_produzidas'].sum().reset_index()
    return grupo.sort_values('data')

# ------------ FILTROS (DISTRIBUÍDOS NO SIDEBAR PARA USO FÁCIL NO MOBILE) -----------
categorias = selecionar_categoria(df)
anos_disp = sorted(df[df['categoria']==categorias[0]]['data'].dt.year.unique())
# Otimizado: exibe apenas seletor de categoria e, uma vez escolhida, carrega anos e meses.
categoria_analise = st.sidebar.selectbox("🗂️ Categoria", categorias)
anos_disp = sorted(df[df['categoria']==categoria_analise]['data'].dt.year.unique())
anos_selecionados = st.sidebar.multiselect("Ano(s)", anos_disp, default=anos_disp)
meses_disp = sorted(df[(df['categoria']==categoria_analise) & (df['data'].dt.year.isin(anos_selecionados))]['data'].dt.month.unique())
meses_nome = [f"{m:02d} - {calendar.month_name[m]}" for m in meses_disp]
map_mes = dict(zip(meses_nome, meses_disp))
meses_selecionados_nome = st.sidebar.multiselect("Mês(es)", meses_nome, default=meses_nome)
meses_selecionados = [map_mes[n] for n in meses_selecionados_nome]

df_filtrado = filtrar_periodo(df, categoria_analise, anos_selecionados, meses_selecionados)

# ----------- ÁREA PRINCIPAL e Cabeçalho Responsivo -----------
st.markdown(f"<h3 style='margin:0 0 0.7em 0;padding-bottom:2px;border-radius: 6px;'>📈 Análise para <b>{categoria_analise}</b></h3>", unsafe_allow_html=True)
if df_filtrado.empty:
    st.error("Não há dados para esse período e categoria.")
    st.stop()

# -------- KPIs (Mostrados em cards grandes, toques facilitados no mobile) ---------
def exibe_kpis(df, categoria):
    df_cat = df[df['categoria'] == categoria]
    if df_cat.empty:
        st.info("Sem dados para a seleção.")
        return None
    df_cat['ano'] = df_cat['data'].dt.year
    kpis = df_cat.groupby('ano')['caixas_produzidas'].agg(['sum','mean','std','count']).reset_index()
    # Otimização: KPIs em cards com cores suaves e fonte maior no mobile.
    cols = st.columns(len(kpis))
    for i, (_, row) in enumerate(kpis.iterrows()):
        ano = int(row['ano'])
        with cols[i]:
            st.metric(f"{ano}", f"{int(row['sum']):,} caixas", help=f"Média diária: {row['mean']:.0f}\nRegistros: {row['count']}")
            st.caption(f"Média/dia: <b>{row['mean']:.0f}</b><br>Ocorrências: {row['count']}", unsafe_allow_html=True)
    return kpis

exibe_kpis(df_filtrado, categoria_analise)

# ----------------- FUNÇÕES DE GRÁFICOS (Tamanho e legenda otimizados) -----------------
def plot_tendencia(df, categoria):
    grupo = gerar_dataset_modelo(df, categoria)
    if grupo.empty:
        st.info("Sem dados para tendência.")
        return
    fig = px.line(
        grupo, x='data', y='caixas_produzidas',
        title=f"Tendência diária",
        markers=True,
        labels={"data": "Data", "caixas_produzidas": "Caixas Produzidas"}
    )
    fig.update_traces(line_color="#636EFA", line_width=2, marker=dict(size=6, color="darkblue"))
    fig.update_layout(template="plotly_white", hovermode="x", height=340, title_x=0.1,
        font=dict(size=16))
    st.plotly_chart(fig, use_container_width=True)

def plot_variacao_mensal(df, categoria):
    agrup = dataset_ano_mes(df, categoria)
    mensal = agrup.groupby([agrup['data'].dt.to_period('M')])['caixas_produzidas'].sum().reset_index()
    mensal['mes'] = mensal['data'].dt.strftime('%b/%Y')
    mensal['var_%'] = mensal['caixas_produzidas'].pct_change() * 100
    fig1 = px.bar(
        mensal, x='mes', y='caixas_produzidas', text_auto='.0s',
        title="Produção mensal",
        labels={"mes":"Mês/Ano", "caixas_produzidas":"Caixas"}
    )
    fig1.update_traces(marker_color="#27AE60")
    fig1.update_layout(template="plotly_white", height=310, margin=dict(l=15,r=15,t=40,b=20))
    fig2 = px.line(
        mensal, x='mes', y='var_%', markers=True,
        title="Variação percentual mensal (%)",
        labels={"mes":"Mês/Ano", "var_%":"Variação (%)"}
    )
    fig2.update_traces(line_color="#E67E22", marker=dict(size=5))
    fig2.update_layout(template="plotly_white", height=230, margin=dict(l=15, r=15, t=40, b=5))
    st.plotly_chart(fig1, use_container_width=True)
    st.plotly_chart(fig2, use_container_width=True)

def plot_sazonalidade(df, categoria):
    agrup = dataset_ano_mes(df, categoria)
    if agrup.empty:
        st.info("Sem dados para sazonalidade.")
        return
    fig = px.box(
        agrup, x='mes', y='caixas_produzidas', color=agrup['ano'].astype(str),
        points='all', notched=True,
        title="Sazonalidade mensal",
        labels={'mes': "Mês", "caixas_produzidas": "Produção"},
        hover_data=["ano"]
    )
    fig.update_layout(
        xaxis=dict(
            tickmode='array',
            tickvals=list(range(1,13)),
            ticktext=[nome_mes(m) for m in range(1,13)]
        ),
        template="plotly_white",
        legend_title="Ano",
        height=265
    )
    st.plotly_chart(fig, use_container_width=True)

def plot_comparativo_ano_mes(df, categoria):
    agrup = dataset_ano_mes(df, categoria)
    tab = agrup.groupby(['ano', 'mes'])['caixas_produzidas'].sum().reset_index()
    tab['mes_nome'] = tab['mes'].apply(nome_mes)
    tab = tab.sort_values(['mes'])
    fig = go.Figure()
    anos = sorted(tab['ano'].unique())
    for ano in anos:
        dados_ano = tab[tab['ano'] == ano]
        fig.add_trace(go.Bar(
            x=dados_ano['mes_nome'],
            y=dados_ano['caixas_produzidas'],
            name=str(ano),
            text=dados_ano['caixas_produzidas'],
            textposition='auto'
        ))
    fig.update_layout(
        barmode='group',
        title="Produção mensal por ano",
        xaxis_title="Mês",
        yaxis_title="Caixas",
        legend_title="Ano",
        hovermode="x unified",
        template="plotly_white",
        height=270
    )
    st.plotly_chart(fig, use_container_width=True)

def plot_comparativo_acumulado(df, categoria):
    agrup = dataset_ano_mes(df, categoria)
    res = agrup.groupby(['ano','mes'])['caixas_produzidas'].sum().reset_index()
    res['acumulado'] = res.groupby('ano')['caixas_produzidas'].cumsum()
    fig = px.line(
        res, x='mes', y='acumulado', color=res['ano'].astype(str),
        markers=True,
        labels={'mes':"Mês", 'acumulado':"Caixas Acumuladas", 'ano':'Ano'},
        title="Acumulado mês a mês"
    )
    fig.update_traces(mode="lines+markers")
    fig.update_layout(
        legend_title="Ano",
        xaxis=dict(
            tickmode='array',
            tickvals=list(range(1,13)),
            ticktext=[nome_mes(m) for m in range(1,13)]
        ),
        hovermode="x unified",
        template="plotly_white",
        height=245
    )
    st.plotly_chart(fig, use_container_width=True)

# ------- Previsão (carregamento e gráfico simplificados para mobile) ---------
def rodar_previsao_prophet(df, categoria, meses_futuro=6):
    dataset = gerar_dataset_modelo(df, categoria)
    if dataset.shape[0] < 2:
        return dataset, pd.DataFrame(), None
    dados = dataset.rename(columns={'data':'ds', 'caixas_produzidas':'y'})
    modelo = Prophet(yearly_seasonality=True, daily_seasonality=False)
    modelo.fit(dados)
    futuro = modelo.make_future_dataframe(periods=meses_futuro*30)
    previsao = modelo.predict(futuro)
    return dados, previsao, modelo

def plot_previsao(dados_hist, previsao, categoria):
    if previsao.empty:
        st.info("Sem previsão disponível.")
        return
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=dados_hist['ds'], y=dados_hist['y'],
                             mode='lines+markers', name='Histórico',
                             line=dict(color='#2980B9', width=2),
                             marker=dict(color='#154360', size=5)))
    fig.add_trace(go.Scatter(x=previsao['ds'], y=previsao['yhat'],
                             mode='lines', name='Previsão', line=dict(color='#27AE60', width=2)))
    fig.add_trace(go.Scatter(x=previsao['ds'], y=previsao['yhat_upper'],
                             line=dict(dash='dash', color='#AED6F1'), name='Limite Sup.', opacity=0.27))
    fig.add_trace(go.Scatter(x=previsao['ds'], y=previsao['yhat_lower'],
                             line=dict(dash='dash', color='#AED6F1'), name='Limite Inf.', opacity=0.27))
    fig.update_layout(title="Previsão de produção",
                     xaxis_title="Data", yaxis_title="Caixas",
                     template="plotly_white", hovermode="x unified", height=270)
    st.plotly_chart(fig, use_container_width=True)

# --------- INSIGHTS AUTOMÁTICOS (expansível por padrão, mobile first) ---------
def gerar_insights(df, categoria):
    grupo = gerar_dataset_modelo(df, categoria)
    tendencias = []
    mensal = grupo.copy()
    mensal['mes'] = mensal['data'].dt.to_period('M')
    agg = mensal.groupby('mes')['caixas_produzidas'].sum()
    if len(agg) > 6:
        ultimos = min(3, len(agg))
        if agg[-ultimos:].mean() > agg[:-ultimos].mean():
            tendencias.append("📈 Crescimento recente detectado nos últimos meses.")
        elif agg[-ultimos:].mean() < agg[:-ultimos].mean():
            tendencias.append("📉 Queda recente detectada nos últimos meses.")
    q1 = grupo['caixas_produzidas'].quantile(0.25)
    q3 = grupo['caixas_produzidas'].quantile(0.75)
    outliers = grupo[(grupo['caixas_produzidas'] < q1 - 1.5*(q3-q1)) | (grupo['caixas_produzidas'] > q3 + 1.5*(q3-q1))]
    if not outliers.empty:
        tendencias.append(f"⚠️ {outliers.shape[0]} dias atípicos detectados (possíveis outliers).")
    std = grupo['caixas_produzidas'].std()
    mean = grupo['caixas_produzidas'].mean()
    if mean > 0 and std/mean > 0.5:
        tendencias.append("🔁 Alta variabilidade diária. Considere revisar causas de flutuação.")
    with st.expander("💡 Insights automáticos", expanded=True):
        for t in tendencias:
            st.info(t)
        if not tendencias:
            st.success("Tudo está estável para esta categoria.")

# ------ EXPORTAÇÃO SIMPLIFICADA PARA MOBILE ------
def exportar_consolidado(df, previsao, categoria):
    if previsao.empty:
        st.warning("Sem previsão para exportar.")
        return
    dados = gerar_dataset_modelo(df, categoria)
    previsao_col = previsao[['ds', 'yhat']].rename(columns={'ds':'data', 'yhat':'previsao_caixas'})
    base_export = dados.merge(previsao_col, left_on='data', right_on='data', how='outer').sort_values("data")
    base_export['categoria'] = categoria
    nome_arq = f'consolidado_{categoria.lower()}.xlsx'
    return base_export, nome_arq

# --------------- CHAMADAS DA TELA (ORDEM OTIMIZADA) ---------------
plot_tendencia(df_filtrado, categoria_analise)
plot_variacao_mensal(df_filtrado, categoria_analise)
plot_sazonalidade(df_filtrado, categoria_analise)
if len(set(df_filtrado['data'].dt.year)) > 1:
    plot_comparativo_ano_mes(df_filtrado, categoria_analise)
    plot_comparativo_acumulado(df_filtrado, categoria_analise)
dados_hist, previsao, modelo_prophet = rodar_previsao_prophet(df_filtrado, categoria_analise, meses_futuro=6)
plot_previsao(dados_hist, previsao, categoria_analise)
gerar_insights(df_filtrado, categoria_analise)

# ----------- EXPORTAÇÃO (visualmente distinta para touch) ----------
with st.expander("⬇️ Exportação consolidada com previsão"):
    if st.button("Exportar consolidado (.xlsx)", type="primary"):
        base_export, nome_arq = exportar_consolidado(df_filtrado, previsao, categoria_analise)
        buffer = io.BytesIO()
        base_export.to_excel(buffer, index=False, engine='openpyxl')
        buffer.seek(0)
        st.download_button(
            label="Download Excel",
            data=buffer,
            file_name=nome_arq,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# --------------------------------------------------------------------------------------------
# Principais Melhorias implementadas:
# - Navegação superior fixa e temática, facilitando uso no mobile.
# - Controles grandes, fáceis de tocar.
# - KPIs e gráficos otimizados em tamanho e responsividade.
# - SideBar sempre aberta para fácil seleção.
# - Exportação e resultados dentro de expander, reduzindo poluição visual em telas pequenas.
# - Uso de cores, tipografia e margin/padding visando contraste e conforto visual.
# - Comentários claros para futuras adaptações e manutenção.
# - Modularização mantida, pronta para reuso das funções.
# --------------------------------------------------------------------------------------------
