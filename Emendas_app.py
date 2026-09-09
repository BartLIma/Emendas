import pandas as pd
import streamlit as st
import os
import urllib.parse

st.set_page_config(layout="wide", page_title="Monitoramento de Emendas Parlamentares")

# --- NOMES PADRONIZADOS DOS ARQUIVOS DE EMENDAS ---
ARQUIVOS_EMENDAS = {
    "Individuais": "emendas_individuais.csv",
    "Bancada Obrigatória": "emendas_bancada.csv",
    "Comissão": "emendas_comissao.csv"
}

# --- FUNÇÃO ROBUSTA COM AUTO-DETECÇÃO DE SEPARADOR ---
def carregar_banco_emendas(caminho_arquivo):
    if not os.path.exists(caminho_arquivo):
        return pd.DataFrame()
    
    # Testa os encodings mais comuns e os dois principais separadores do Excel
    for enc in ["utf-8-sig", "latin1", "cp1252"]:
        for separador in [";", ","]:
            try:
                # Carrega o dataframe testando a combinação atual
                df = pd.read_csv(caminho_arquivo, sep=separador, dtype=str)
                df.columns = df.columns.str.strip()
                
                # Se o Pandas leu correto, o número de colunas deve ser maior que 1
                if len(df.columns) > 1:
                    # Limpa espaços em branco das células e substitui nulos
                    for col in df.columns:
                        df[col] = df[col].fillna("").astype(str).str.strip()
                    return df
            except Exception:
                continue
                
    # Fallback caso tenha lido apenas 1 coluna na primeira tentativa (tenta forçar leitura)
    try:
        df = pd.read_csv(caminho_arquivo, sep=None, engine="python", dtype=str)
        df.columns = df.columns.str.strip()
        for col in df.columns:
            df[col] = df[col].fillna("").astype(str).str.strip()
        return df
    except Exception:
        return pd.DataFrame()

# Carregamento inicial das bases
df_ind = carregar_banco_emendas(ARQUIVOS_EMENDAS["Individuais"])
df_ban = carregar_banco_emendas(ARQUIVOS_EMENDAS["Bancada Obrigatória"])
df_com = carregar_banco_emendas(ARQUIVOS_EMENDAS["Comissão"])
# --- 🔍 BLOCO DE DIAGNÓSTICO TEMPORÁRIO (REMOVER DEPOIS) ---
st.markdown("### 🛠️ Depuração e Inspeção de Arquivos Crús")
for nome_tipo, nome_arq in ARQUIVOS_EMENDAS.items():
    if os.path.exists(nome_arq):
        try:
            with open(nome_arq, "r", encoding="utf-8", errors="ignore") as f:
                linhas_cruas = [f.readline().strip() for _ in range(3)]
            
            st.write(f"📁 **Arquivo:** `{nome_arq}` ({nome_tipo})")
            st.code("\n".join(linhas_cruas), language="text")
        except Exception as e:
            st.error(f"Erro ao ler `{nome_arq}`: {e}")
st.markdown("---")
# --- 🎛️ PAINEL LATERAL DE NAVEGAÇÃO E FILTROS ---
st.sidebar.header("Filtros de Pesquisa")

tipo_emenda = st.sidebar.radio(
    "Tipo de Emenda:",
    ["Individuais", "Bancada Obrigatória", "Comissão"]
)

st.sidebar.markdown("---")
st.sidebar.subheader("Parâmetros do Filtro")

# Definição dos anos padrão exigidos (2023 a 2026)
col_ano1, col_ano2 = st.sidebar.columns(2)
with col_ano1:
    ano_inicial = st.number_input("Ano Inicial:", min_value=2000, max_value=2100, value=2023)
with col_ano2:
    ano_final = st.number_input("Ano Final:", min_value=2000, max_value=2100, value=2026)

# Filtro de texto para Parlamentar e Beneficiário (vazio = todos)
busca_parlamentar = st.sidebar.text_input("Parlamentar (Em branco = Todos):", value="").strip()
busca_beneficiario = st.sidebar.text_input("Beneficiário / CNPJ (Em branco = Todos):", value="").strip()

# Mapeamento do DataFrame ativo baseado na seleção do menu lateral
if tipo_emenda == "Individuais":
    df_ativo = df_ind.copy()
elif tipo_emenda == "Bancada Obrigatória":
    df_ativo = df_ban.copy()
else:
    df_ativo = df_com.copy()  # <--- Certifique-se de que esta linha está com 4 espaços de recuo

# --- LÓGICA DE FILTRAGEM DINÂMICA E SEGURA ---
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
    # 1. Painel de Resumos Financeiros (Totalizadores de Moeda)
    colunas_valores = ["Instrumento (R$)", "Empenhado (R$)", "Pago (R$)"]
    totais = {}
    
    for col_val in colunas_valores:
        if col_val in df_filtrado.columns:
            # Limpeza rápida de pontos e vírgulas textuais para conversão numérica correta
            serie_limpa = df_filtrado[col_val].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
            totais[col_val] = pd.to_numeric(serie_limpa, errors="coerce").fillna(0).sum()
        else:
            totais[col_val] = 0.0

    st.markdown("### 📊 Sumarização dos Recursos Filtrados")
    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
        st.metric("Total Instrumento", f"R$ {totais['Instrumento (R$)']:=,2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col_m2:
        st.metric("Total Empenhado", f"R$ {totais['Empenhado (R$)']:=,2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    with col_m3:
        st.metric("Total Pago", f"R$ {totais['Pago (R$)']:=,2f}".replace(",", "X").replace(".", ",").replace("X", "."))

    # 2. Exibição da Tabela Completa Tratada em Tela
    st.markdown(f"**Registros localizados:** {len(df_filtrado)} linhas.")
    st.dataframe(df_filtrado, use_container_width=True, hide_index=True)

    # 3. Bloco de Exportação e Cópia Rápida para Mensagens
    st.markdown("---")
    st.subheader("📥 Exportação e Compartilhamento")
    
    col_exp1, col_exp2 = st.columns(2)
    
    with col_exp1:
        # Conversões para download limpo
        csv_buffer = df_filtrado.to_csv(index=False, sep=";").encode("utf-8-sig")
        st.download_button(
            label="📄 Baixar Resultado em CSV",
            data=csv_buffer,
            file_name=f"emendas_{tipo_emenda.lower().replace(' ', '_')}_filtrado.csv",
            mime="text/csv"
        )
        
    with col_exp2:
        # Geração dinâmica do resumo em texto para o botão de cópia rápida
        texto_resumo_copia = (
            f"📊 *RESUMO DE EMENDAS PARLAMENTARES FEDERAIS ({tipo_emenda})*\n"
            f"📅 Período de Consulta: {ano_inicial} a {ano_final}\n"
            f"👥 Parlamentar Filtrado: {busca_parlamentar if busca_parlamentar else 'Todos'}\n"
            f"🏢 Beneficiário Filtrado: {busca_beneficiario if busca_beneficiario else 'Todos'}\n"
            f"🔢 Total de Linhas: {len(df_filtrado)}\n\n"
            f"💰 *VALORES CONSOLIDADOS:*\n"
            f"• Total Instrumento: R$ {totais['Instrumento (R$)']:=,2f}\n"
            f"• Total Empenhado: R$ {totais['Empenhado (R$)']:=,2f}\n"
            f"• Total Pago: R$ {totais['Pago (R$)']:=,2f}\n\n"
            f"_Gerado automaticamente via Painel de Emendas PB_"
        ).replace(",", "X").replace(".", ",").replace("X", ".")
        
        # Área de texto com ícone nativo de cópia no canto superior direito
        st.text_area("📋 Copie o resumo abaixo para enviar por mensagem:", value=texto_resumo_copia, height=160)

# --- RODAPÉ DISCRETO PADRONIZADO DA PARCERIA ---
st.markdown("---")
st.markdown(
    "<p style='text-align:right; font-size:12px; color:gray; font-style:italic;'>"
    "Desenvolvido por: Bartolomeu Lima (Corecon-ES 1541) & AI Workspace 🤝 2026</p>",
    unsafe_allow_html=True
)
