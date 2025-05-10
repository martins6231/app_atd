import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import io
import requests
import tempfile
import zipfile
from prophet import Prophet
import calendar
from datetime import datetime
import os

# ----------- Paleta Britvic -----------
COR_VERDE = "#006B3F"
COR_AZUL = "#002A32"
COR_BRANCA = "#FFFFFF"
COR_CINZA_CLARO = "#F5F5F5"
COR_AMARELO = "#FFC107"

st.set_page_config(
    page_title="Acompanhamento Britvic",
    layout="wide",
    page_icon="🍹"
)

# ----------- Carregar logo britvic -----------

logo_path = "britvic-seeklogo.png"
if os.path.isfile(logo_path):
    st.image(logo_path, use_container_width=True)
else:
    st.warning(f"Logo '{logo_path}' não encontrada! Por favor, verifique se o arquivo está no repositório.")

# ----------- Cabeçalho estilizado -----------
st.markdown(
    f"""
    <div style="background-color:{COR_VERDE};padding:15px;border-radius:10px;margin-bottom:10px;">
        <h1 style="color:{COR_BRANCA};text-align:center;margin-bottom:0;">🔎 Acompanhamento de Produção - Britvic</h1>
    </div>
    """, unsafe_allow_html=True
)

# ----------- Sidebar configurável -----------
st.sidebar.header("⚙️ Configurações")
st.sidebar.markdown(
    f"<div style='color:{COR_AZUL};'>Configure a categoria, ano e mês para análise personalizada.</div>",
    unsafe_allow_html=True
)

st.markdown(
    "Os dados deste Dashboard são atualizados automaticamente a cada 10 minutos a partir de uma planilha segura hospedada na nuvem (Google Drive)."
)

def is_excel_file(file_path):
    try:
        with zipfile.ZipFile(file_path):
            return True
    except zipfile.BadZipFile:
        return False
    except Exception:
        return False

def convert_gsheet_link(shared_url):
    if "docs.google.com/spreadsheets" in shared_url:
        import re
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', shared_url)
        if match:
            sheet_id = match.group(1)
            return f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx'
    return shared_url

@st.cache_data(ttl=600)
def carregar_excel_nuvem(link):
    url = convert_gsheet_link(link)
    resp = requests.get(url)
    if resp.status_code != 200:
        st.error(f"Erro ao baixar planilha. Status code: {resp.status_code}")
        return None
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(resp.content)
        tmp.flush()
        if not is_excel_file(tmp.name):
            st.error("Arquivo baixado não é um Excel válido. Confirme se o link é público/correto!")
            return None
        try:
            df = pd.read_excel(tmp.name, engine="openpyxl")
        except Exception as e:
            st.error(f"Erro abrindo o Excel: {e}")
            return None
    return df

if "CLOUD_XLSX_URL" not in st.secrets:
    st.error("Adicione CLOUD_XLSX_URL ao seu .streamlit/secrets.toml e compartilhe a planilha para 'qualquer pessoa com o link'.")
    st.stop()

xlsx_url = st.secrets["CLOUD_XLSX_URL"]
df_raw = carregar_excel_nuvem(xlsx_url)
if df_raw is None:
    st.stop()

def tratar_dados(df):
    erros = []
    df = df.rename(columns=lambda x: x.strip().lower().replace(" ", "_"))
    obrigatorias = ['categoria', 'data', 'caixas_produzidas']
    for col in obrigatorias:
        if col not in df.columns:
            erros.append(f"Coluna obrigatória ausente: {col}")
    try:
        df['data'] = pd.to_datetime(df['data'])
    except Exception:
        erros.append("Erro ao converter coluna 'data'.")
    na_count = df.isna().sum()
    for col, qtd in na_count.items():
        if qtd > 0:
            erros.append(f"Coluna '{col}' com {qtd} valores ausentes.")
    negativos = (df['caixas_produzidas'] < 0).sum() if 'caixas_produzidas' in df else 0
    if negativos > 0:
        erros.append(f"{negativos} registros negativos em 'caixas_produzidas'.")
    if set(obrigatorias).issubset(df.columns):
        df_clean = df.dropna(subset=['categoria','data','caixas_produzidas']).copy()
        df_clean['caixas_produzidas'] = pd.to_numeric(df_clean['caixas_produzidas'], errors='coerce').fillna(0).astype(int)
        df_clean = df_clean[df_clean['caixas_produzidas'] >= 0]
        df_clean = df_clean.drop_duplicates(subset=['categoria','data'], keep='first')
    else:
        df_clean = pd.DataFrame()
    return df_clean, erros

df, erros = tratar_dados(df_raw)
with st.expander("Relatório de problemas encontrados", expanded=len(erros)>0):
    if erros:
        for e in erros: st.warning(e)
    else:
        st.success("Nenhum problema crítico encontrado.")

def selecionar_categoria(df):
    return sorted(df['categoria'].dropna().unique())

def dataset_ano_mes(df, categoria=None):
    df_filt = df if categoria is None else df[df['categoria'] == categoria]
    df_filt = df_filt.copy()
    df_filt['ano'] = df_filt['data'].dt.year
    df_filt['mes'] = df_filt['data'].dt.month
    return df_filt

def filtrar_periodo(df, categoria, anos_selecionados):
    cond = (df['categoria'] == categoria)
    if anos_selecionados:
        cond &= (df['data'].dt.year.isin(anos_selecionados))
    return df[cond].copy()

# --------- Filtros sidebar ---------
categorias = selecionar_categoria(df)
categoria_analise = st.sidebar.selectbox("Categoria:", categorias)

anos_disp = sorted(df[df['categoria']==categoria_analise]['data'].dt.year.unique())
anos_selecionados = st.sidebar.multiselect("Ano(s):", anos_disp, default=anos_disp)

df_filtrado = filtrar_periodo(df, categoria_analise, anos_selecionados)

st.subheader(f"Análise para categoria: **{categoria_analise}**")
if df_filtrado.empty:
    st.error("Não há dados para esse período e categoria.")
    st.stop()

# ---------------------- KPIs ----------------------

def exibe_kpis(df, categoria):
    df_cat = df[df['categoria'] == categoria]
    if df_cat.empty:
        st.info("Sem dados para a seleção.")
        return None
    df_cat['ano'] = df_cat['data'].dt.year
    kpis = df_cat.groupby('ano')['caixas_produzidas'].agg(['sum','mean','std','count']).reset_index()
    cols = st.columns(len(kpis))
    for i, (_, row) in enumerate(kpis.iterrows()):
        ano = int(row['ano'])
        with cols[i]:
            st.markdown(
                f"""<div style="background-color:{COR_CINZA_CLARO};padding:15px 8px;border-radius:10px;text-align:center;margin-bottom:8px;">
                    <h3 style="color:{COR_AZUL}; margin-bottom:5px;">Ano {ano}</h3>
                    <span style="font-size:1.7em; color:{COR_VERDE};">{int(row['sum']):,} caixas</span><br>
                    <span style="font-size:0.8em;color:{COR_AZUL};">Média diária: {row['mean']:.0f} <br>Registros: {row['count']}</span>
                </div>""",
                unsafe_allow_html=True,
            )
    return kpis

exibe_kpis(df_filtrado, categoria_analise)

# ---------------------- Gráficos ----------------------

def plot_tendencia(df, categoria):
    grupo = df[df['categoria'] == categoria].groupby('data')['caixas_produzidas'].sum().reset_index()
    if grupo.empty:
        st.info("Sem dados para tendência.")
        return
    fig = px.line(
        grupo, x='data', y='caixas_produzidas',
        title=f"Tendência Diária - {categoria}",
        markers=True,
        labels={"data":"Data", "caixas_produzidas":"Caixas Produzidas"}
    )
    fig.update_traces(line_color=COR_VERDE, line_width=2, marker=dict(size=7, color=COR_AZUL))
    fig.update_layout(template="plotly_white", hovermode="x", plot_bgcolor=COR_BRANCA)
    st.plotly_chart(fig, use_container_width=True)

def nome_mes(numero):
    return calendar.month_abbr[int(numero)]

def plot_variacao_mensal(df, categoria):
    agrup = dataset_ano_mes(df, categoria)
    mensal = agrup.groupby([agrup['data'].dt.to_period('M')])['caixas_produzidas'].sum().reset_index()
    mensal['mes'] = mensal['data'].dt.strftime('%b/%Y')
    mensal['var_%'] = mensal['caixas_produzidas'].pct_change() * 100
    # Barra produção mensal
    fig1 = px.bar(
        mensal, x='mes', y='caixas_produzidas',
        text_auto=True,
        title=f"Produção Mensal Total - {categoria}",
        labels={"mes":"Mês/Ano", "caixas_produzidas":"Caixas Produzidas"},
        color_discrete_sequence=[COR_VERDE]
    )
    fig1.update_layout(template="plotly_white")
    # Linha variação %
    fig2 = px.line(
        mensal, x='mes', y='var_%', markers=True,
        title=f"Variação Percentual Mensal (%) - {categoria}",
        labels={"mes":"Mês/Ano", "var_%":"Variação (%)"}
    )
    fig2.update_traces(line_color=COR_AMARELO, marker=dict(size=7))
    fig2.update_layout(template="plotly_white")
    st.plotly_chart(fig1, use_container_width=True)
    st.plotly_chart(fig2, use_container_width=True)

plot_tendencia(df_filtrado, categoria_analise)
plot_variacao_mensal(df_filtrado, categoria_analise)

# (Continue inserindo outras funções de gráfico, previsão, insights, etc, conforme sua necessidade)

# -- Exportação de dados filtrados --
st.markdown(
    f"""<div style="background-color:{COR_AMARELO};padding:10px;border-radius:10px;text-align:center;margin-top:15px;">
        <h3 style="color:{COR_AZUL};">📂 Exportação de Dados</h3>
    </div>""",
    unsafe_allow_html=True
)
if st.button("Exportar Dados Filtrados (.xlsx)"):
    buffer = io.BytesIO()
    df_filtrado.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)
    st.download_button(
        label="📥 Baixar Arquivo",
        data=buffer,
        file_name=f"producao_britvic_{categoria_analise}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ------------------------------------
# DICA: Se quiser incluir mais gráficos, alertas dinâmicos, visuais customizados, pode incrementar usando os exemplos anteriores!
