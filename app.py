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

# --- Configurar Tema ---
st.set_page_config(
    page_title="Acompanhamento Britvic", 
    layout="wide",
    page_icon="🍹"  # Um ícone relacionado ao tema.
)

# Definir as cores do tema
COR_VERDE = "#006B3F"
COR_AZUL = "#002A32"
COR_BRANCA = "#FFFFFF"
COR_CINZA_CLARO = "#F5F5F5"
COR_AMARELO = "#FFC107"

# --- Cabeçalho ---
st.image("britvic-seeklogo.png", use_column_width=True)  # Insere o logotipo no topo.
st.markdown(
    f"""
    <div style="background-color:{COR_VERDE};padding:15px;border-radius:10px">
        <h1 style="color:{COR_BRANCA};text-align:center">🔎 Acompanhamento de Produção - Britvic</h1>
    </div>
    """, unsafe_allow_html=True
)

# --- Sidebar ---
st.sidebar.header("⚙️ Configurações")
st.sidebar.markdown(f"""
<div style="color:{COR_AZUL};">
    Configure a categoria, ano e mês para análise personalizada.
</div>
""", unsafe_allow_html=True)

# Texto de introdução
st.markdown("""
Os dados deste Dashboard são atualizados automaticamente a cada 10 minutos a partir de uma planilha segura hospedada na nuvem (Google Drive).
""")

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

@st.cache_data(ttl=600)  # Atualiza automaticamente a cada 10 minutos
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
    st.error("Adicione CLOUD_XLSX_URL ao seu .streamlit/secrets.toml e garanta que a planilha esteja acessível.")
    st.stop()

xlsx_url = st.secrets["CLOUD_XLSX_URL"]
df_raw = carregar_excel_nuvem(xlsx_url)
if df_raw is None:
    st.stop()

# ------------------ Processamento de Dados ------------------
def tratar_dados(df):
    erros = []
    df = df.rename(columns=lambda x: x.strip().lower().replace(" ", "_"))  # Limpeza de colunas
    try:
        df['data'] = pd.to_datetime(df['data'])
    except Exception:
        erros.append("Erro ao converter coluna 'data'.")
    na_count = df.isna().sum()
    for col, qtd in na_count.items():
        if qtd > 0:
            erros.append(f"Coluna '{col}' possui {qtd} valores ausentes.")
    if 'caixas_produzidas' in df.columns and (df['caixas_produzidas'] < 0).sum() > 0:
        erros.append("Há valores negativos em 'caixas_produzidas'.")
    return df, erros

df, erros = tratar_dados(df_raw)

# Relatório de problemas de dados encontrados
if erros:
    with st.expander("🚨 Problemas de Qualidade de Dados"):
        st.warning("Os seguintes problemas foram detectados:")
        for erro in erros:
            st.text(erro)
else:
    st.success("Nenhum problema crítico encontrado nos dados.")

# ------------------ Filtros e Seleção ------------------
categorias = sorted(df['categoria'].dropna().unique())
categoria_selecionada = st.sidebar.selectbox("Escolha uma Categoria:", categorias, index=0)

anos = sorted(df[df['categoria'] == categoria_selecionada]['data'].dt.year.dropna().unique())
anos_selecionados = st.sidebar.multiselect("Selecione o Ano:", anos, default=anos)

# Filtro do DataFrame
df_filtrado = df[(df['categoria'] == categoria_selecionada) & (df['data'].dt.year.isin(anos_selecionados))]

if df_filtrado.empty:
    st.error("⚠️ Não há dados disponíveis para a categoria e anos selecionados.")
    st.stop()

# ------------------ Estilo dos KPIs ------------------
st.markdown(f"""
<div style="background-color:{COR_CINZA_CLARO};padding:10px;border-radius:10px;">
    <h2 style="color:{COR_AZUL};text-align:center">📈 Destaques de Produção</h2>
</div>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)
# KPI 1
col1.metric("Produção Total", f"{int(df_filtrado['caixas_produzidas'].sum()):,} caixas", delta="5%", delta_color="normal")
# KPI 2
col2.metric("Média Diária", f"{df_filtrado['caixas_produzidas'].mean():,.2f} caixas", delta="-1%", delta_color="inverse")
# KPI 3
col3.metric("Desvio Padrão", f"{df_filtrado['caixas_produzidas'].std():,.2f} caixas")

# ------------------ Gráficos ------------------
def plot_tendencia_producao(df):
    fig = px.line(
        df, x="data", y="caixas_produzidas",
        title="Tendência de Produção ao Longo do Tempo",
        labels={"data": "Data", "caixas_produzidas": "Caixas Produzidas"},
        markers=True,
    )
    fig.update_traces(line_color=COR_VERDE)
    fig.update_layout(template="plotly_white", paper_bgcolor=COR_BRANCA)
    st.plotly_chart(fig, use_container_width=True)

plot_tendencia_producao(df_filtrado)

# --- Exportação ---
st.markdown(f"""
<div style="background-color:{COR_AMARELO};padding:10px;border-radius:10px;">
    <h3 style="color:{COR_AZUL};text-align:center">📂 Exportação de Dados</h3>
</div>
""", unsafe_allow_html=True)

if st.button("Exportar Dados Filtrados (.xlsx)"):
    buffer = io.BytesIO()
    df_filtrado.to_excel(buffer, index=False, engine="openpyxl")
    buffer.seek(0)
    st.download_button(
        label="📥 Baixar Arquivo",
        data=buffer,
        file_name=f"producao_britvic_{categoria_selecionada}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
