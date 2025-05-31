# app.py
import streamlit as st
import requests
import datetime
import pandas as pd
import json

# --- 1. Carregar Credenciais do Bling (seguras com secrets.toml) ---
try:
    CLIENT_ID = st.secrets["bling"]["client_id"]
    CLIENT_SECRET = st.secrets["bling"]["client_secret"]
    REDIRECT_URI = st.secrets["bling"]["redirect_uri"]
except KeyError:
    st.error("Credenciais Bling não encontradas. Certifique-se de configurar o arquivo secrets.toml corretamente.")
    st.stop() # Para a execução da aplicação

# URLs da API Bling
AUTH_URL = "https://www.bling.com.br/b/Api/v3/oauth/authorize"
TOKEN_URL = "https://www.bling.com.br/Api/v3/oauth/token"
PEDIDOS_VENDA_URL = "https://www.bling.com.br/Api/v3/pedidos/vendas"

# --- 2. Funções de Autenticação e API Bling ---

def get_authorization_url():
    """Gera o URL para o usuário autorizar a aplicação Bling."""
    state = "bling_app_state" # Pode ser um valor único para segurança
    return f"{AUTH_URL}?response_type=code&client_id={CLIENT_ID}&state={state}&redirect_uri={REDIRECT_URI}"

def exchange_code_for_token(code):
    """Troca o código de autorização por um token de acesso e refresh token."""
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI
    }
    response = requests.post(TOKEN_URL, headers=headers, data=data)
    response.raise_for_status() # Lança uma exceção para códigos de status HTTP de erro (4xx ou 5xx)
    return response.json()

def refresh_access_token(refresh_token):
    """Renova o token de acesso usando o refresh token."""
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    response = requests.post(TOKEN_URL, headers=headers, data=data)
    response.raise_for_status()
    return response.json()

@st.cache_data(ttl=3600) # Armazena em cache os dados por 1 hora
def get_vendas_do_dia(access_token):
    """Busca as vendas do dia na API do Bling."""
    hoje = datetime.date.today().strftime("%d/%m/%Y")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    params = {
        "dataInicial": hoje,
        "dataFinal": hoje,
        "situacao": "Atendido" # Ajuste a situação conforme sua necessidade (ver doc Bling)
    }

    try:
        # A API do Bling pode ter paginação, então precisamos buscar todas as páginas
        all_vendas = []
        page = 1
        while True:
            current_params = params.copy()
            current_params["pagina"] = page
            response = requests.get(PEDIDOS_VENDA_URL, headers=headers, params=current_params)
            response.raise_for_status()
            
            data = response.json().get('data', [])
            if not data:
                break # Sem mais dados, sai do loop
            all_vendas.extend(data)
            page += 1

        return all_vendas
    except requests.exceptions.RequestException as e:
        st.error(f"Erro ao buscar vendas do Bling: {e}")
        if response:
            st.error(f"Resposta detalhada do Bling: {response.text}")
        return []

# --- 3. Interface do Streamlit ---

st.set_page_config(page_title="Visualizador de Vendas Bling", layout="wide")
st.title("📊 Vendas do Dia (Bling ERP)")

# Gerenciar tokens na sessão do Streamlit
if 'access_token' not in st.session_state:
    st.session_state.access_token = None
if 'refresh_token' not in st.session_state:
    st.session_state.refresh_token = None
if 'token_expires_at' not in st.session_state:
    st.session_state.token_expires_at = None

# --- Lógica de Autenticação OAuth2 ---
query_params = st.query_params

if query_params.get("code"):
    auth_code = query_params["code"]
    try:
        token_response = exchange_code_for_token(auth_code)
        st.session_state.access_token = token_response["access_token"]
        st.session_state.refresh_token = token_response["refresh_token"]
        st.session_state.token_expires_at = datetime.datetime.now() + datetime.timedelta(seconds=token_response["expires_in"])
        st.success("Autenticação Bling realizada com sucesso!")
        # Limpa os parâmetros da URL para evitar reprocessar o código
        st.query_params.clear() 
        st.experimental_rerun() # Recarrega a página para remover o código da URL
    except Exception as e:
        st.error(f"Erro ao autenticar com o Bling: {e}")
        st.session_state.access_token = None
        st.session_state.refresh_token = None
        st.session_state.token_expires_at = None

# Se não houver token de acesso, mostre o botão de autenticação
if st.session_state.access_token is None:
    st.warning("Você precisa autenticar com o Bling para visualizar as vendas.")
    auth_link = get_authorization_url()
    st.markdown(f"[Clique aqui para autenticar com o Bling]({auth_link})", unsafe_allow_html=True)
else:
    # --- Verificar Expiração do Token e Renovar ---
    if st.session_state.token_expires_at and datetime.datetime.now() >= st.session_state.token_expires_at:
        st.warning("Token de acesso expirado. Tentando renovar...")
        try:
            token_response = refresh_access_token(st.session_state.refresh_token)
            st.session_state.access_token = token_response["access_token"]
            st.session_state.refresh_token = token_response["refresh_token"]
            st.session_state.token_expires_at = datetime.datetime.now() + datetime.timedelta(seconds=token_response["expires_in"])
            st.success("Token de acesso renovado com sucesso!")
        except Exception as e:
            st.error(f"Erro ao renovar token. Por favor, autentique novamente: {e}")
            st.session_state.access_token = None
            st.session_state.refresh_token = None
            st.session_state.token_expires_at = None
            st.experimental_rerun() # Recarrega para mostrar o botão de autenticação

    if st.session_state.access_token:
        st.success("Conectado ao Bling.")
        
        # Botão para recarregar os dados
        if st.button("Atualizar Vendas do Dia"):
            st.cache_data.clear() # Limpa o cache para buscar dados frescos
            st.experimental_rerun() # Recarrega a página para exibir os novos dados

        vendas = get_vendas_do_dia(st.session_state.access_token)

        if vendas:
            st.subheader(f"Vendas Realizadas Hoje ({datetime.date.today().strftime('%d/%m/%Y')})")
            
            # Preparar dados para exibição
            dados_para_df = []
            total_vendas = 0
            for venda in vendas:
                cliente_nome = venda.get('cliente', {}).get('nome')
                valor_venda = float(venda.get('total'))
                situacao = venda.get('situacao', {}).get('descricao')
                
                dados_para_df.append({
                    "ID Pedido": venda.get('numero'), # 'numero' é o número do pedido, 'id' é o ID interno
                    "Data": venda.get('data'),
                    "Cliente": cliente_nome if cliente_nome else "Não informado",
                    "Valor Total": f"R$ {valor_venda:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."), # Formatação BR
                    "Situação": situacao if situacao else "Não informada",
                    "Observações": venda.get('observacoes')
                })
                total_vendas += valor_venda
            
            df_vendas = pd.DataFrame(dados_para_df)

            st.metric(label="Total de Vendas do Dia", value=f"R$ {total_vendas:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            st.dataframe(df_vendas, use_container_width=True)

            st.caption(f"Total de {len(vendas)} vendas encontradas para hoje.")

        else:
            st.info("Nenhuma venda encontrada para o dia de hoje com a situação 'Atendido'.")
