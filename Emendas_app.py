import pandas as pd
import streamlit as st
import os
import urllib.parse

st.set_page_config(layout="wide", page_title="Monitoramento de Emendas Parlamentares")
# --- NOMES PADRONIZADOS DOS ARQUIVOS DE EMENDAS (ATUALIZADO) ---
ARQUIVOS_EMENDAS = {
    "Individuais": "emendas_individuais.csv",
    "Bancada": "emendas_bancada.csv",  # <--- Mudamos a chave aqui para "Bancada"
    "Comissão": "emendas_comissao.csv"
}
# --- NOMES PADRONIZADOS DOS ARQUIVOS DE EMENDAS ---
def carregar_banco_emendas(caminho_arquivo):
    if not os.path.exists(caminho_arquivo):
        return pd.DataFrame()
    
    # Como vimos na imagem, o padrão correto e exato é latin1/cp1252 com separador ponto e vírgula
    for enc in ["latin1", "utf-8-sig", "cp1252"]:
        try:
            df = pd.read_csv(caminho_arquivo, sep=";", encoding=enc, dtype=str)
            df.columns = df.columns.str.strip()
            
            if not df.empty and len(df.columns) > 1:
                # Limpa espaços em branco e remove nulos
                for col in df.columns:
                    df[col] = df[col].fillna("").astype(str).str.strip()
                return df
        except Exception:
            continue
            
    return pd.DataFrame()

# Carregamento cirúrgico dos bancos
df_ind = carregar_banco_emendas(ARQUIVOS_EMENDAS["Individuais"])
df_ban = carregar_banco_emendas(ARQUIVOS_EMENDAS["Bancada Obrigatória"])
df_com = carregar_banco_emendas(ARQUIVOS_EMENDAS["Comissão"])

# --- 🎛️ PAINEL LATERAL DE NAVEGAÇÃO E FILTROS ---
st.sidebar.header("Filtros de Pesquisa")

# Ajustado para "Bancada" apenas
tipo_emenda = st.sidebar.radio(
    "Tipo de Emenda:",
    ["Individuais", "Bancada", "Comissão"]
)

st.sidebar.markdown("---")
st.sidebar.subheader("Parâmetros do Filtro")

col_ano1, col_ano2 = st.sidebar.columns(2)
with col_ano1:
    ano_inicial = st.number_input("Ano Inicial:", min_value=2000, max_value=2100, value=2023)
with col_ano2:
    ano_final = st.number_input("Ano Final:", min_value=2000, max_value=2100, value=2026)

# REGRA DE NEGÓCIO ATUALIZADA: Define o padrão do campo dependendo do tipo selecionado
default_parlamentar = ""
if tipo_emenda == "Bancada":
    default_parlamentar = "Bancada"
elif tipo_emenda == "Comissão":
    default_parlamentar = "Comissão"

busca_parlamentar = st.sidebar.text_input("Parlamentar (Em branco = Todos):", value=default_parlamentar).strip()
busca_beneficiario = st.sidebar.text_input("Beneficiário / CNPJ (Em branco = Todos):", value="").strip()

# Mapeamento do DataFrame baseado nos nomes dos arquivos reais
if tipo_emenda == "Individuais":
    df_ativo = df_ind.copy() if df_ind is not None else pd.DataFrame()
elif tipo_emenda == "Bancada":
    df_ativo = df_ban.copy() if df_ban is not None else pd.DataFrame()
else:
    df_ativo = df_com.copy() if df_com is not None else pd.DataFrame()# --- LÓGICA DE FILTRAGEM DINÂMICA E SEGURA ---
df_filtrado = df_ativo.copy()  # <--- Esta linha fica encostada na margem esquerda (sem espaços antes)

if not df_filtrado.empty:
    # 1. Filtro por Intervalo de Anos (Apenas se a coluna 'Ano' existir no arquivo)
    if "Ano" in df_filtrado.columns:
        # Tenta converter para numérico temporariamente para fazer a comparação de intervalo
        df_filtrado["_Ano_Num"] = pd.to_numeric(df_filtrado["Ano"], errors="coerce").fillna(0).astype(int)
        df_filtrado = df_filtrado[(df_filtrado["_Ano_Num"] >= ano_inicial) & (df_filtrado["_Ano_Num"] <= ano_final)]
        df_filtrado = df_filtrado.drop(columns=["_Ano_Num"])

    # 2. Filtro por Parlamentar (Apenas se a coluna existir e não estiver em branco)
    if busca_parlamentar and "Parlamentar" in df_filtrado.columns:
        df_filtrado = df_filtrado[df_filtrado["Parlamentar"].str.lower().str.contains(busca_parlamentar.lower(), na=False)]

    # 3. Filtro por Beneficiário ou CNPJ (Busca em ambas as colunas se existirem)
    if busca_beneficiario:
        termo_busca = busca_beneficiario.lower()
        condicao_beneficiario = pd.Series(False, index=df_filtrado.index)
        
        if "Beneficiário" in df_filtrado.columns:
            condicao_beneficiario |= df_filtrado["Beneficiário"].str.lower().str.contains(termo_busca, na=False)
        if "CNPJ Beneficiário" in df_filtrado.columns:
            condicao_beneficiario |= df_filtrado["CNPJ Beneficiário"].str.lower().str.contains(termo_busca, na=False)
            
        df_filtrado = df_filtrado[condicao_beneficiario]

# --- RENDERIZAÇÃO DA INTERFACE PRINCIPAL ---
st.title("🏛️ Painel de Consulta: Emendas Parlamentares Federais")
st.subheader(f"📍 Destinações para o Estado da Paraíba — [ {tipo_emenda} ]")

# Exibição de avisos caso os arquivos CSV não existam na pasta do projeto
nome_arquivo_esperado = ARQUIVOS_EMENDAS[tipo_emenda]
if not os.path.exists(nome_arquivo_esperado):
    st.error(f"⚠️ Arquivo correspondente não localizado: `{nome_arquivo_esperado}`. Por favor, faça o upload da base de dados.")
    st.stop()
elif df_ativo.empty:
    st.warning(f"⚠️ O arquivo `{nome_arquivo_esperado}` foi localizado, mas a leitura não retornou dados estruturados.")
    df_ativo = df_com.copy()
# --- RESOLUÇÃO DE EXIBIÇÃO EM TELA ---
if df_filtrado.empty:
    st.info("ℹ️ Nenhum registro encontrado para os filtros selecionados.")
else:
    # 1. Painel de Resumos Financeiros (Totalizadores de Moeda Limpos e Seguros)
    colunas_valores = ["Instrumento (R$)", "Empenhado (R$)", "Pago (R$)"]
    totais = {}
    
    for col_val in colunas_valores:
        if col_val in df_filtrado.columns:
            # LIMPEZA PROFUNDA E ULTRA-SEGURA: Remove R$, espaços e ajusta pontos/vírgulas do Excel
            serie_limpa = df_filtrado[col_val].astype(str).str.replace("R$", "", regex=False)
            serie_limpa = serie_limpa.str.replace(" ", "", regex=False).str.strip()
            
            # Trata formato brasileiro (1.234,56) convertendo temporariamente para internacional (1234.56)
            serie_limpa = serie_limpa.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
            
            # Converte para numérico ignorando textos inválidos (ex: hifens ou células vazias)
            totais[col_val] = pd.to_numeric(serie_limpa, errors="coerce").fillna(0.0).sum()
        else:
            totais[col_val] = 0.0
    st.markdown("### 📊 Sumarização dos Recursos Filtrados")
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        # Formatação nativa segura do Python para exibição no padrão monetário brasileiro
        valor_formatado_inst = f"R$ {totais['Instrumento (R$)']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        st.metric("Total Instrumento", valor_formatado_inst)
    with col_m2:
        valor_formatado_emp = f"R$ {totais['Empenhado (R$)']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        st.metric("Total Empenhado", valor_formatado_emp)
    with col_m3:
        valor_formatado_pag = f"R$ {totais['Pago (R$)']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        st.metric("Total Pago", valor_formatado_pag)

    # 2. Exibição da Tabela Completa Tratada em Tela
    st.markdown(f"**Registros localizados:** {len(df_filtrado)} linhas.")
    st.dataframe(df_filtrado, use_container_width=True, hide_index=True)

   # 3. Bloco de Exportação e Cópia Rápida para Mensagens
    st.markdown("---")
    st.subheader("📥 Exportação e Compartilhamento")
    
    col_exp1, col_exp2 = st.columns(2)
    
    with col_exp1:
        csv_buffer = df_filtrado.to_csv(index=False, sep=";").encode("utf-8-sig")
        st.download_button(
            label="📄 Baixar Resultado em CSV",
            data=csv_buffer,
            file_name=f"emendas_{tipo_emenda.lower().replace(' ', '_')}_filtrado.csv",
            mime="text/csv"
        )
        
    with col_exp2:
        # CORREÇÃO CRÍTICA DO ERRO DE FORMATAÇÃO (Linha 175)
        texto_resumo_copia = (
            f"📊 *RESUMO DE EMENDAS PARLAMENTARES FEDERAIS ({tipo_emenda})*\n"
            f"📅 Período de Consulta: {ano_inicial} a {ano_final}\n"
            f"👥 Parlamentar Filtrado: {busca_parlamentar if busca_parlamentar else 'Todos'}\n"
            f"🏢 Beneficiário Filtrado: {busca_beneficiario if busca_beneficiario else 'Todos'}\n"
            f"🔢 Total de Linhas: {len(df_filtrado)}\n\n"
            f"💰 *VALORES CONSOLIDADOS:*\n"
            f"• Total Instrumento: R$ {totais['Instrumento (R$)']:,.2f}\n"
            f"• Total Empenhado: R$ {totais['Empenhado (R$)']:,.2f}\n"
            f"• Total Pago: R$ {totais['Pago (R$)']:,.2f}\n\n"
            f"_Gerado automaticamente via Painel de Emendas PB_"
        ).replace(",", "X").replace(".", ",").replace("X", ".")
        
        st.text_area("📋 Copie o resumo abaixo para enviar por mensagem:", value=texto_resumo_copia, height=160)
# --- RODAPÉ DISCRETO PADRONIZADO DA PARCERIA ---
st.markdown("---")
st.markdown(
    "<p style='text-align:right; font-size:12px; color:gray; font-style:italic;'>"
    "Desenvolvido por: Bartolomeu Lima (Corecon-ES 1541) & AI Workspace 🤝 2026</p>",
    unsafe_allow_html=True
)
