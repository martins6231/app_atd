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

# Configuração da página com título e tema ajustado
st.set_page_config(page_title="Acompanhamento Britvic", layout="wide")

# Cores da identidade visual
PRIMARY_GREEN = "#006B3F"
DARK_BLUE = "#002A32"
LIGHT_GREY = "#F5F5F5"
WARNING_YELLOW = "#FFC107"
WHITE = "#FFFFFF"

# Estilo personalizado
st.markdown(
    f"""
    <style>
        /* Background geral */
        .css-18e3th9 {{
            background-color: {LIGHT_GREY};
        }}
        /* Texto de título */
        .css-10trblm {{ 
            color: {DARK_BLUE}; 
        }}
        /* Botões e elementos principais */
        div.stButton > button:first-child {{
            background-color: {PRIMARY_GREEN};
            color: {WHITE};
            border: 1px solid {DARK_BLUE};
            border-radius: 10px;
        }}
        div.stButton > button:first-child:hover {{
            background-color: {DARK_BLUE};
            color: {WHITE};
        }}
        /* Alertas */
        .stAlert {{
            border-radius: 10px;
        }}
        /* Títulos e subtítulos */
        .stMarkdown h2 {{
            color: {DARK_BLUE};
        }}
        .streamlit-expanderHeader {{
            background-color: {PRIMARY_GREEN};
            color: {WHITE};
            border-radius: 10px 10px 0 0;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)

# --- TÍTULO ---
st.title("🔎 Acompanhamento de Produção - Britvic")

# --- SIDEBAR ---
st.sidebar.header("Configurações")
st.sidebar.markdown(
    """
    **Filtros para análise**
    Escolha a categoria, ano(s) e mês(es) desejados para detalhar os dados.
    """
)

# --- TEXTO INTRODUTÓRIO ---
st.markdown(
    f"""
    **Bem-vindo ao dashboard de análise da Britvic!**  
    Este painel apresenta insights sobre produção.  
    As informações são atualizadas a cada **10 minutos** e estão alinhadas com os princípios de **simplicidade e clareza**.

    ---
    """
)

# --- FUNÇÕES DO SISTEMA ---
def nome_mes(numero):
    return calendar.month_abbr[int(numero)]

# Função para converter link do Google Sheets
def convert_gsheet_link(shared_url):
    if "docs.google.com/spreadsheets" in shared_url:
        import re
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", shared_url)
        if match:
            sheet_id = match.group(1)
            return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    return shared_url

# Função para baixar o Excel
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
        try:
            df = pd.read_excel(tmp.name, engine="openpyxl")
        except Exception as e:
            st.error(f"Erro ao carregar o arquivo Excel: {e}")
            return None
    return df

# --- CONTROLE DE ARQUIVO ---
if "CLOUD_XLSX_URL" not in st.secrets:
    st.error(
        "⚠️ O URL da planilha em nuvem não foi configurado. Atualize o arquivo `.streamlit/secrets.toml`."
    )
    st.stop()

xlsx_url = st.secrets["CLOUD_XLSX_URL"]
df_raw = carregar_excel_nuvem(xlsx_url)
if df_raw is None:
    st.stop()

# --- PRÉ-PROCESSAMENTO E VALIDAÇÃO ---
def tratar_dados(df):
    erros = []
    df = df.rename(columns=lambda x: x.strip().lower().replace(" ", "_"))
    if 'data' not in df.columns or 'caixas_produzidas' not in df.columns:
        erros.append("Colunas obrigatórias ausentes: 'data', 'caixas_produzidas'")
    if len(erros) > 0:
        return None, erros

    try:
        df["data"] = pd.to_datetime(df["data"])
        df["caixas_produzidas"] = pd.to_numeric(
            df["caixas_produzidas"], errors="coerce"
        ).fillna(0).astype(int)
    except Exception:
        erros.append("Falha ao converter dados de 'data' ou 'caixas_produzidas'.")

    return df, erros

df, erros = tratar_dados(df_raw)
if erros:
    with st.expander("⚠️ Problemas no processamento"):
        for erro in erros:
            st.warning(erro)
    st.stop()

# --- FILTRO DE CATEGORIAS ---
def selecionar_categoria(df):
    return sorted(df["categoria"].dropna().unique())


categorias = selecionar_categoria(df)
categoria_analise = st.sidebar.selectbox("Categoria:", categorias)

anos_disp = sorted(df["data"].dt.year.unique())
anos_selecionados = st.sidebar.multiselect("Ano(s):", anos_disp, default=anos_disp)

# --- SELEÇÃO DE PARAMÊTROS ---
st.subheader(f"Categoria selecionada: {categoria_analise}")

# --- KPIS ---
st.markdown(
    f"""
    **Indicadores**  
    Os valores abaixo representam os resultados da produção para a **categoria selecionada**.
    """
)
