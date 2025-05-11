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

# Configurações iniciais do Streamlit
st.set_page_config(
    page_title="Produção Britvic",
    layout="wide",
    page_icon="🧃",
)

# Adicionando a logo
st.markdown(
    """
    <div style="text-align: center;">
        <img src="britvic-seeklogo.png" alt="Logo Britvic" width="300"/>
    </div>
    """,
    unsafe_allow_html=True,
)

# Título estilizado
st.markdown(
    """
    <h1 style="text-align: center; color: #003057;">
        🔎 Dashboard de Produção - Britvic
    </h1>
    """,
    unsafe_allow_html=True,
)

def nome_mes(numero):
    return calendar.month_abbr[int(numero)]

# Sidebar com configurações
st.sidebar.header("Configurações")

st.markdown(
    """
    <p style="text-align: center; color: #003057; font-size: 18px;">
        Os dados deste Dashboard são atualizados automaticamente a cada 10 minutos a partir de uma planilha segura em nuvem (Google Drive).
    </p>
    """,
    unsafe_allow_html=True,
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
    """Converte link /edit do Google Sheets para /export?format=xlsx"""
    if "docs.google.com/spreadsheets" in shared_url:
        import re
        match = re.search(r'/d/([a-zA-Z0-9-_]+)', shared_url)
        if match:
            sheet_id = match.group(1)
            return f'https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx'
    return shared_url

@st.cache_data(ttl=600)  # Atualiza automaticamente a cada 10 minutos (600 segundos)
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

# ---------------------------------------------------------------

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
    negativos = (df['caixas_produzidas'] < 0).sum()
    if negativos > 0:
        erros.append(f"{negativos} registros negativos em 'caixas_produzidas'.")
    df_clean = df.dropna(subset=['categoria', 'data', 'caixas_produzidas']).copy()
    df_clean['caixas_produzidas'] = pd.to_numeric(df_clean['caixas_produzidas'], errors='coerce').fillna(0).astype(int)
    df_clean = df_clean[df_clean['caixas_produzidas'] >= 0]
    df_clean = df_clean.drop_duplicates(subset=['categoria', 'data'], keep='first')
    return df_clean, erros

df, erros = tratar_dados(df_raw)
with st.expander("Relatório de problemas encontrados", expanded=len(erros) > 0):
    if erros:
        for e in erros:
            st.warning(e)
    else:
        st.success("Nenhum problema crítico encontrado.")

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

# -------- SELEÇÃO DE PARÂMETROS --------
categorias = selecionar_categoria(df)
categoria_analise = st.sidebar.selectbox("Categoria:", categorias)

anos_disp = sorted(df[df['categoria'] == categoria_analise]['data'].dt.year.unique())
anos_selecionados = st.sidebar.multiselect("Ano(s):", anos_disp, default=anos_disp)

meses_disp = sorted(df[(df['categoria'] == categoria_analise) & (df['data'].dt.year.isin(anos_selecionados))]['data'].dt.month.unique())
meses_nome = [f"{m:02d} - {calendar.month_name[m]}" for m in meses_disp]
map_mes = dict(zip(meses_nome, meses_disp))
meses_selecionados_nome = st.sidebar.multiselect("Mês(es):", meses_nome, default=meses_nome)
meses_selecionados = [map_mes[n] for n in meses_selecionados_nome]

df_filtrado = filtrar_periodo(df, categoria_analise, anos_selecionados, meses_selecionados)

st.subheader(f"Análise para categoria: **{categoria_analise}**")
if df_filtrado.empty:
    st.error("Não há dados para esse período e categoria.")
    st.stop()

# --------- KPIs ---------
# ... KPIs e gráficos continuam iguais ...
