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
COR_VERDE = "#006B3F"  # Fundo e gráficos
COR_AZUL = "#002A32"  # Tipografia e bordas
COR_BRANCO = "#FFFFFF"  # Fundo e texto principal
COR_CINZA_CLARO = "#F5F5F5"  # Painéis e divisórias
COR_AMARELO = "#FFC107"  # Indicadores e alertas

# Configuração da página
st.set_page_config(
    page_title="Acompanhamento Britvic",
    layout="wide",
    page_icon="🍹"
)

# ----------- Exibindo a logo -----------
logo_path = "britvic-seeklogo.png"

if os.path.isfile(logo_path):
    st.image(logo_path, use_container_width=True)
else:
    st.warning(f"Logo '{logo_path}' não encontrada! Certifique-se de adicionar o arquivo corretamente ao diretório do app.")

# ----------- Cabeçalho Principal -----------
st.markdown(
    f"""
    <div style="background-color:{COR_VERDE};padding:20px;border-radius:8px;">
        <h1 style="color:{COR_BRANCO};text-align:center;margin-bottom:0px;">
            🔎 Dashboard de Acompanhamento de Produção Britvic
        </h1>
    </div>
    """,
    unsafe_allow_html=True
)

# ----------- Introdução e Sidebar -----------
st.sidebar.header("⚙️ Configurações")
st.sidebar.markdown(
    f"""
    <div style="color:{COR_AZUL};">
    Configure a categoria, ano e mês para análises mais específicas.
    </div>
    """, unsafe_allow_html=True
)

st.markdown(
    f"""
    <div>
        Os dados deste dashboard são atualizados automaticamente a cada 10 minutos, via integração segura com o Google Drive.
    </div>
    """,
    unsafe_allow_html=True
)

# ------------------ Download seguro da planilha -----------------
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
            return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
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
            st.error(f"Erro ao abrir o Excel: {e}")
            return None
    return df

if "CLOUD_XLSX_URL" not in st.secrets:
    st.error("Adicione CLOUD_XLSX_URL ao seu .streamlit/secrets.toml e compartilhe a planilha para 'qualquer pessoa com o link'.")
    st.stop()

xlsx_url = st.secrets["CLOUD_XLSX_URL"]
df_raw = carregar_excel_nuvem(xlsx_url)
if df_raw is None:
    st.stop()

# ------------------- Tratamento dos dados -------------------
def tratar_dados(df):
    erros = []
    df = df.rename(columns=lambda x: x.strip().lower().replace(" ", "_"))
    obrigatorias = ["categoria", "data", "caixas_produzidas"]
    for col in obrigatorias:
        if col not in df.columns:
            erros.append(f"Coluna obrigatória ausente: {col}")
    try:
        df["data"] = pd.to_datetime(df["data"])
    except Exception:
        erros.append("Erro ao converter coluna 'data'.")
    na_count = df.isna().sum()
    for col, qtd in na_count.items():
        if qtd > 0:
            erros.append(f"Coluna '{col}' com {qtd} valores ausentes.")
    negativos = (df["caixas_produzidas"] < 0).sum() if "caixas_produzidas" in df else 0
    if negativos > 0:
        erros.append(f"{negativos} registros negativos em 'caixas_produzidas'.")
    if set(obrigatorias).issubset(df.columns):
        df_clean = df.dropna(subset=["categoria", "data", "caixas_produzidas"]).copy()
        df_clean["caixas_produzidas"] = pd.to_numeric(df_clean["caixas_produzidas"], errors="coerce").fillna(0).astype(int)
        df_clean = df_clean[df_clean["caixas_produzidas"] >= 0]
        df_clean = df_clean.drop_duplicates(subset=["categoria", "data"], keep="first")
    else:
        df_clean = pd.DataFrame()
    return df_clean, erros

df, erros = tratar_dados(df_raw)
with st.expander("Relatório de problemas encontrados", expanded=bool(erros)):
    if erros:
        for e in erros:
            st.warning(e)
    else:
        st.success("Nenhum problema crítico encontrado.")

def selecionar_categoria(df):
    return sorted(df["categoria"].dropna().unique())

def dataset_ano_mes(df, categoria=None):
    df_filt = df if categoria is None else df[df["categoria"] == categoria]
    df_filt["ano"] = df_filt["data"].dt.year
    df_filt["mes"] = df_filt["data"].dt.month
    return df_filt

def filtrar_periodo(df, categoria, anos_selecionados):
    cond = (df["categoria"] == categoria)
    if anos_selecionados:
        cond &= df["data"].dt.year.isin(anos_selecionados)
    return df[cond].copy()

# --------- Filtros Sidebar --------
categorias = selecionar_categoria(df)
categoria_analise = st.sidebar.selectbox("Categoria:", categorias)

anos_disp = sorted(df[df["categoria"] == categoria_analise]["data"].dt.year.unique())
anos_selecionados = st.sidebar.multiselect("Ano(s):", anos_disp, default=anos_disp)

df_filtrado = filtrar_periodo(df, categoria_analise, anos_selecionados)

if df_filtrado.empty:
    st.error("Nenhum dado encontrado para as opções selecionadas.")
    st.stop()

# --------- KPIs Estilizados ---------
def exibe_kpis(df):
    with st.container():
        total_producao = int(df["caixas_produzidas"].sum())
        media_diaria = df["caixas_produzidas"].mean()
        desvio_padrao = df["caixas_produzidas"].std()

        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Total Produzido", f"{total_producao:,} caixas")
        kpi2.metric("Média Diária", f"{media_diaria:.2f} caixas")
        kpi3.metric("Desvio Padrão", f"{desvio_padrao:.2f} caixas")

exibe_kpis(df_filtrado)

# --------- Gráficos ---------
def plot_tendencia(df):
    if df.empty:
        st.info("Sem dados para gerar o gráfico.")
        return
    figura = px.line(
        df, x="data", y="caixas_produzidas",
        title=f"Tendência de Produção - {categoria_analise}",
        markers=True
    )
    figura.update_traces(line_color=COR_VERDE)
    st.plotly_chart(figura, use_container_width=True)

plot_tendencia(df_filtrado)
