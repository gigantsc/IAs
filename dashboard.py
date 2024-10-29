import json 
from dotenv import load_dotenv 
import redis 
import pandas as pd 
import streamlit as st 
import plotly.express as px 
from openai import OpenAI 
from datetime import datetime, timedelta
import pickle
from pathlib import Path

# Definir o layout expandido da página
st.set_page_config(layout="wide")
load_dotenv()

# Configuração de pastas para armazenamento da chave
PASTA_CONFIGURACOES = Path('configuracoes')
PASTA_CONFIGURACOES.mkdir(exist_ok=True)

# Funções de leitura e escrita da chave API
def salva_chave(caminho, chave):
    with open(caminho, 'wb') as f:
        pickle.dump(chave, f)

def le_chave(caminho):
    if caminho.exists() and caminho.stat().st_size > 0:
        with open(caminho, 'rb') as f:
            try:
                return pickle.load(f)
            except (EOFError, pickle.UnpicklingError):
                st.warning(f"O arquivo de chave em {caminho} está corrompido ou vazio. Salve novamente a chave.")
                # Limpa o arquivo corrompido
                caminho.write_bytes(b'')
                return ''
    else:
        return ''



# Caminhos dos arquivos de configuração
API_KEY_PATH = PASTA_CONFIGURACOES / 'OPENAI_API_KEY'
REDIS_URL_PATH = PASTA_CONFIGURACOES / 'REDIS_URL'
REDIS_PASSWORD_PATH = PASTA_CONFIGURACOES / 'REDIS_PASSWORD'

AI_NAME_PATH = PASTA_CONFIGURACOES / 'AI_NAME'
AI_OBJECTIVES_PATH = PASTA_CONFIGURACOES / 'AI_OBJECTIVES'

AI_STATUS_PATH = PASTA_CONFIGURACOES / 'STATUS'

# Lógica para salvar e ler as chaves de configuração
if 'api_key' not in st.session_state:
    st.session_state['api_key'] = le_chave(API_KEY_PATH)
if 'redis_url' not in st.session_state:
    st.session_state['redis_url'] = le_chave(REDIS_URL_PATH)
if 'redis_password' not in st.session_state:
    st.session_state['redis_password'] = le_chave(REDIS_PASSWORD_PATH)
if 'ai_name_info' not in st.session_state:
    st.session_state['ai_name_info'] = le_chave(AI_NAME_PATH)
if 'ai_objectives_info' not in st.session_state:
    st.session_state['ai_objectives_info'] = le_chave(AI_OBJECTIVES_PATH)
if 'ai_status_info' not in st.session_state:
    st.session_state['ai_status_info'] = le_chave(AI_STATUS_PATH)

# Inicializar o cliente OpenAI usando a chave salva
api_key = st.session_state['api_key']

# Inicializar o cliente OpenAI somente se a chave estiver disponível
if st.session_state['api_key']:
    try:
        client = OpenAI(api_key=st.session_state['api_key'])
        st.toast("Cliente OpenAI inicializado com sucesso.", icon="✅")
    except Exception as e:
        st.error(f"Erro ao inicializar o cliente OpenAI: {e}")
else:
    st.warning("A chave da API OpenAI não foi fornecida. Vá para 'Configurações' para inserir sua chave.")

# Conectar ao Redis somente se as variáveis estiverem preenchidas
# Configurar Redis após garantir que URL e senha estão disponíveis
redis_client = None  # Definindo como None inicialmente para evitar NameError
if st.session_state.get('redis_url') and st.session_state.get('redis_password'):
    try:
        redis_client = redis.Redis.from_url(
            f'redis://default:{st.session_state["redis_password"]}@{st.session_state["redis_url"]}'
        )
        redis_client.ping()
        st.toast("Conexão com Redis estabelecida com sucesso.", icon="✅")
    except redis.ConnectionError as e:
        st.error(f"Erro ao conectar ao Redis: {e}")
        redis_client = None
        st.stop()
    except Exception as e:
        st.error(f"Erro inesperado ao conectar ao Redis: {e}")
        redis_client = None
        st.stop()
else:
    st.warning("As credenciais do Redis estão incompletas. Preencha os campos de URL e senha na seção de configurações.")



# Conectar AI_NAME E AI_OBJECTIVES somente se as variáveis estiverem preenchidas
if st.session_state['ai_name_info'] and st.session_state['ai_objectives_info'] and st.session_state['ai_status_info']:
    try:
        ai_name = st.session_state["ai_name_info"]
        ai_objectives = st.session_state["ai_objectives_info"]
        ai_status = st.session_state["ai_status_info"]
        st.toast("Informações sobre as IAs configuradas com sucesso.", icon="✅")
    except Exception as e:
        st.error(f"Erro ao definir informações das IAs: {e}")
        st.stop()
else:
    st.warning("As informações sobre as IAs estão incompletas. Por favor, verifique as informações na seção de configurações.")








# Funções para salvar e restaurar análises individuais no Redis
def salvar_analise_no_redis(redis_client, phone_number, analise_tipo, resultado):
    redis_client.set(f"analise:{analise_tipo}:{phone_number}", resultado)

def restaurar_analise_do_redis(redis_client, phone_number, analise_tipo):
    resultado = redis_client.get(f"analise:{analise_tipo}:{phone_number}")
    if resultado:
        return resultado.decode('utf-8')
    else:
        return None

# Função para obter todos os números históricos
def get_historic_phone_numbers(_redis_client):
    phone_numbers_with_timestamps = {}
    cursor = '0'

    # Carregar todos os números do Redis
    while True:
        cursor, keys = _redis_client.scan(cursor=cursor, match='message:*', count=1000)
        for key in keys:
            message_data = _redis_client.hgetall(key)
            if b'phoneNumber' in message_data and b'createdAt' in message_data:
                phone_number = message_data[b'phoneNumber'].decode('utf-8')
                created_at = int(message_data[b'createdAt'].decode('utf-8'))
                if phone_number not in phone_numbers_with_timestamps or created_at > phone_numbers_with_timestamps[phone_number]:
                    phone_numbers_with_timestamps[phone_number] = created_at
        if cursor == 0:
            break

    # Ordenar e retornar todos os históricos
    sorted_phone_numbers = sorted(phone_numbers_with_timestamps.items(), key=lambda x: x[1], reverse=True)
    historic_phone_numbers = [{'phone_number': phone, 'created_at': timestamp} for phone, timestamp in sorted_phone_numbers]
    return historic_phone_numbers

# Adicionar um seletor de período à barra lateral
with st.sidebar:
    st.header("Navegação")
    pagina_selecionada = st.selectbox("Escolha a página", ["Painel de Mensagem", "Dashboard BI", "Configurações"])





# Função para a página de configurações
def pagina_configuracoes():
    
    st.markdown("<h1 style='color: #03fcf8;'>Configurações</h1>", unsafe_allow_html=True)
    st.write("Insira suas informações para realizar as conexões.")
    st.markdown("<div style='margin-bottom: 40px;'></div>", unsafe_allow_html=True)

    # Campo de entrada para a chave OpenAI
    st.markdown("<span style='color: #03fcf8; font-weight: bold;'>OPENAI_API_KEY</span>", unsafe_allow_html=True)
    
    chave_input = st.text_input("• Insira sua chave da OpenAI:", value=st.session_state['api_key'])

    # Espaço entre os campos
    st.markdown("<div style='margin-bottom: 40px;'></div>", unsafe_allow_html=True)
    
    # Campos de entrada para o Redis
    st.markdown("<span style='color: #03fcf8; font-weight: bold;'>CREDENCIAIS DO REDIS</span>", unsafe_allow_html=True)
    
    redis_url_input = st.text_input("• Insira a URL pública do Redis:", value=st.session_state['redis_url'])
    
    redis_password_input = st.text_input("• Insira a senha do seu banco de dados Redis:", value=st.session_state['redis_password'], type="password")

    # Espaço entre os campos
    st.markdown("<div style='margin-bottom: 40px;'></div>", unsafe_allow_html=True)


    st.markdown("<span style='color: #03fcf8; font-weight: bold;'>INFORMAÇÕES SOBRE AS IAS</span>", unsafe_allow_html=True)
    
    ai_name_input = st.text_input("• Digite o nome da sua IA. Se não tiver dado um nome, escreva apenas: IA de atendimento", value=st.session_state['ai_name_info'])
    
    ai_objectives_input = st.text_input("• Quais pontos a IA que faz o resumo da conversa deverá prestar atenção? (Exemplo: Usuário demonstrou interesse no produto?, Qual foi o tema da conversa?)", value=st.session_state['ai_objectives_info'])
    
    ai_status_input = st.text_input("• Quais status sua IA poderá usar para classificar o lead? (Inclua o status e a descrição dele. Exemplo: Use 'Lead quente' quando o usuário demostrar interesse no produto.)", value=st.session_state['ai_status_info'])



    # Botão para salvar as configurações
    if st.button("Salvar"):
        # Salvar a chave da OpenAI
        st.session_state['api_key'] = chave_input
        salva_chave(API_KEY_PATH, chave_input)


        st.session_state['ai_name_info'] = ai_name_input
        salva_chave(AI_NAME_PATH, ai_name_input)
        
        st.session_state['ai_objectives_info'] = ai_objectives_input
        salva_chave(AI_OBJECTIVES_PATH, ai_objectives_input)

        st.session_state['ai_status_info'] = ai_status_input
        salva_chave(AI_STATUS_PATH, ai_status_input)



        # Salvar as configurações do Redis
        st.session_state['redis_url'] = redis_url_input
        salva_chave(REDIS_URL_PATH, redis_url_input)
        st.session_state['redis_password'] = redis_password_input
        salva_chave(REDIS_PASSWORD_PATH, redis_password_input)

        st.success("Configurações salvas com sucesso!")





# Função para o "Painel de Mensagem"
def painel_mensagem():
    st.title('Dashboard - Conversas da IA com Usuários')

    # Função para normalizar o número de telefone
    def normalize_phone_number(phone):
        if not phone:
            return ''
        normalized_phone = ''.join(filter(str.isdigit, phone))
        if normalized_phone.startswith('55'):
            normalized_phone = normalized_phone[2:]
            if len(normalized_phone) == 10:
                ddd = normalized_phone[:2]
                rest_of_number = normalized_phone[2:]
                normalized_phone = f"{ddd}9{rest_of_number}"
        return normalized_phone

    # Função para normalizar a data para o formato correto com ou sem horário incluído
    def normalizar_data(data_string):
        try:
            # Verifica se a data está vazia ou contém uma mensagem de erro
            if pd.isnull(data_string) or data_string.strip() == "" or "Erro" in data_string:
                return ''  # Retornar uma string vazia se a data estiver ausente ou for uma mensagem de erro

            # Tenta converter o valor para inteiro (timestamp UNIX)
            try:
                data_timestamp = int(data_string)
                # Converte o timestamp UNIX em uma data legível
                data_formatada = pd.to_datetime(data_timestamp, unit='s')
            except ValueError:
                # Caso não seja um timestamp, tenta converter como data formatada
                # Primeiro tenta com horário, depois sem horário
                try:
                    data_formatada = pd.to_datetime(data_string, format='%d/%m/%y %H:%M:%S', dayfirst=True)
                except ValueError:
                    # Se falhar, tenta sem o horário
                    data_formatada = pd.to_datetime(data_string, format='%d/%m/%y', dayfirst=True)

            # Retorna a data no formato 'DD/MM/YY HH:MM:SS' (se possível) ou apenas 'DD/MM/YY'
            return data_formatada.strftime('%d/%m/%y %H:%M:%S') if ' ' in data_string else data_formatada.strftime('%d/%m/%y')
        except Exception as e:
            st.error(f"Erro ao converter a data: {data_string} - {e}")
            return ''

    # Funções para gerar resumos, datas, nomes e classificações
    def gerar_resumo_conversa(mensagens, phone_number, ai_name, ai_objectives):
        try:
            # Limitar o resumo às últimas 15 mensagens
            mensagens_limitadas = '\n'.join(mensagens.strip().split('\n')[-15:])
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"Escreva seu resumo todo em um único parágrafo sem 'enters' ou 'quebras de linhas'. Resuma a conversa entre o usuário, cujo número é {phone_number}, e a IA de nome {ai_name}. Caso o usuário forneça o nome durante a conversa, use o nome fornecido para referenciá-lo. Lembre-se que {ai_name} é o nome da IA. No seu resumo, atente-se às seguintes situações:{ai_objectives}. Essas são as mensagens entre o usuário e a IA: {mensagens_limitadas}"},
                ],
                max_tokens=300,
                temperature=0.2,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Erro ao gerar resumo: {e}"

    def gerar_data(mensagens, phone_number):
        try:
            # Extrair as 8 primeiras mensagens do usuário
            linhas = mensagens.strip().split('\n')
            ultima_mensagem = '\n'.join(linhas[-8:])  # Junta as 8 primeiras linhas
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"Identifique a data da mensagem mais recente enviada pelo número {phone_number}. Seu retorno deve ser apenas a data na seguinte estrutura: 'XX/XX/XX HH:MM:SS'. Exemplo de resposta: 12/10/24 09:30:55. Por exemplo, se tiver uma mensagem com data '12/10/24 09:30:55' e outra com '12/10/24 09:35:55', você deve retornar '12/10/24 09:35:55'."},
                    {"role": "user", "content": f"Identifique a data da mensagem mais recente enviada pelo número {phone_number}. Seu retorno deve ser apenas a data na seguinte estrutura: 'XX/XX/XX HH:MM:SS'. Exemplo de resposta: 12/10/24 09:30:55. Por exemplo, se tiver uma mensagem com data '12/10/24 09:30:55' e outra com '12/10/24 09:35:55', você deve retornar '12/10/24 09:35:55'. Essas são as mensagens:\n\n{ultima_mensagem}"},
                ],
                max_tokens=50,
                temperature=0.2,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Erro ao gerar data: {e}"

    def gerar_nome(mensagens, phone_number, ai_name):
        try:
            mensagens_limitadas = '\n'.join(mensagens.strip().split('\n')[-20:])
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"Analise a conversa entre o usuário, cujo telefone é {phone_number}, e a IA, cujo nome é {ai_name}. Seu objetivo é identificar e retornar o nome do usuário. Seu retorno deve ser apenas o nome do usuário: Exemplo 'Bruno'. Caso não identifique o nome do usuário, retorne apenas 'Nome não fornecido'. Lembre-se que o nome da IA é {ai_name}."},
                    {"role": "user", "content": f"As mensagens são:\n\n{mensagens_limitadas}"},
                ],
                max_tokens=50,
                temperature=0.2,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Erro ao gerar nome: {e}"

    def gerar_classificacao(mensagens, phone_number, ai_name):
        try:
            mensagens_limitadas = '\n'.join(mensagens.strip().split('\n')[-20:])
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"Analise a conversa entre o usuário, cujo telefone é {phone_number}, e a IA, cujo nome é {ai_name}. Classifique a conversa conforme as seguintes categorias: {ai_status}. Sua resposta deve conter apenas a classificação. Exemplo: 'Lead quente'"},
                    {"role": "user", "content": f"As mensagens são:\n\n{mensagens_limitadas}"},
                ],
                max_tokens=50,
                temperature=0.2,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Erro ao gerar classificação: {e}"

    # Função para salvar dados processados no Redis
    def salvar_dados_no_redis(redis_client, df):
        for _, row in df.iterrows():
            phone_number = row['Número de WhatsApp']
            redis_client.set(f"dashboard_dados:{phone_number}", json.dumps(row.to_dict()))  # Salva o DataFrame como JSON no Redis

    # Função para restaurar dados do Redis
    def restaurar_dados_do_redis(redis_client):
        # Verificar se redis_client está conectado antes de tentar acessar
        if not redis_client:
         print("redis_client não está conectado. Verifique a conexão com o Redis.")
         return []  # Retorna lista vazia se a conexão falhar
        cursor = '0'
        dados_redis = []
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match='dashboard_dados:*', count=1000)
            for key in keys:
                dado = redis_client.get(key)
                if dado:
                    dados_redis.append(json.loads(dado.decode('utf-8')))
            if cursor == 0:
                break
        return dados_redis

    # Função para salvar o estado dos checks no Redis
    def salvar_checks_no_redis(redis_client, df):
        for _, row in df.iterrows():
            phone_number = row['Número de WhatsApp']
            check_value = row['Selecionado']
            redis_client.set(f"check:{phone_number}", str(check_value))  # Armazena como string ('True' ou 'False')

    # Função para restaurar os checks do Redis
    def restaurar_checks_do_redis(redis_client, df):
        for i, row in df.iterrows():
            phone_number = row['Número de WhatsApp']
            check_value = redis_client.get(f"check:{phone_number}")
            if check_value:
                df.at[i, 'Selecionado'] = check_value.decode('utf-8') == 'True'  # Converte string para booleano

    # Carregar dados salvos do Redis ou session_state
    dados_salvos = restaurar_dados_do_redis(redis_client)
    if 'df' not in st.session_state:
        if dados_salvos:
            df = pd.DataFrame(dados_salvos)
            # Aplicar a normalização da data e ordenar
            df['Data de Criação'] = df['Data de Criação'].apply(normalizar_data)
            df = df.sort_values(by='Data de Criação', ascending=False)
            st.session_state['df'] = df
        else:
            df = pd.DataFrame()
            st.session_state['df'] = df
    else:
        df = st.session_state['df']

    
    # Adicionar o seletor de período
    period_options = ['Completo', 'Último mês', 'Últimos 14 dias', 'Últimos 7 dias', 'Ontem', 'Hoje']
    selected_period = st.selectbox('Selecione o período', period_options)

    # Obter a data atual
    today = datetime.today()

#começa
      # Verificar se o DataFrame está vazio
    if df.empty:
        st.warning("Sem dados disponíveis no DataFrame.")
        st.stop()  # Interrompe a execução se não houver dados

    # Verificar as colunas disponíveis no DataFrame
    st.write("Colunas disponíveis no DataFrame:", df.columns.tolist())

    # Remover espaços extras nos nomes das colunas e converter tudo para minúsculas para facilitar a comparação
    df.columns = df.columns.str.strip().str.lower()

    # Verificar se a coluna 'data de criação' (em minúsculas) existe
    if 'data de criação' not in df.columns:
        st.error("Coluna 'Data de Criação' não encontrada no DataFrame. As colunas disponíveis são: " + ", ".join(df.columns))
        st.stop()

    # Ajustar para o nome correto da coluna em minúsculas
    temp_dates = pd.to_datetime(df['data de criação'], format='%d/%m/%y %H:%M:%S', dayfirst=True, errors='coerce')
 
    #termina

    # Criar uma série temporária com as datas convertidas
    temp_dates = pd.to_datetime(df['Data de Criação'], format='%d/%m/%y %H:%M:%S', dayfirst=True, errors='coerce')
    
    # Aplicar o filtro de acordo com o período selecionado
    if selected_period == 'Último mês':
        start_date = today - timedelta(days=30)
        mask = temp_dates >= start_date
        df_filtered = df[mask]
    elif selected_period == 'Últimos 14 dias':
        start_date = today - timedelta(days=14)
        mask = temp_dates >= start_date
        df_filtered = df[mask]
    elif selected_period == 'Últimos 7 dias':
        start_date = today - timedelta(days=7)
        mask = temp_dates >= start_date
        df_filtered = df[mask]
    elif selected_period == 'Ontem':
        yesterday = today - timedelta(days=1)
        mask = temp_dates.dt.date == yesterday.date()
        df_filtered = df[mask]
    elif selected_period == 'Hoje':
        mask = temp_dates.dt.date == today.date()
        df_filtered = df[mask]
    else:
        df_filtered = df  # 'Completo', não aplica filtro


    # Adicionar botão de atualização
    if st.button('Atualizar'):
        # Obter números históricos do Redis
        historic_phone_numbers = get_historic_phone_numbers(redis_client)
        if not historic_phone_numbers:
            st.info("Nenhum dado encontrado no Redis.")
            return

        # Criar uma cópia do dataframe atual
        previous_df = df.copy()

        data = []
        for item in historic_phone_numbers:
            phone_number = item['phone_number']
            data_criacao = item['created_at']
            normalized_phone_number = normalize_phone_number(phone_number)

            # Verificar se o número já existe no dataframe anterior
            previous_data = previous_df[previous_df['Número de WhatsApp'] == normalized_phone_number]
            if not previous_data.empty:
                previous_message_count = previous_data['Nº User Messages'].values[0]
            else:
                previous_message_count = 0

            # Obter o threadId associado a este número de telefone
            thread_id_key = f'threadId:{normalized_phone_number}'
            thread_id = redis_client.get(thread_id_key)
            mensagens_texto = ''
            mensagens_texto_completo = ''
            if thread_id:
                thread_id = thread_id.decode('utf-8')
                # Obter as mensagens da conversa
                conversation_key = f'conversation:{normalized_phone_number}:{thread_id}'
                messages = redis_client.lrange(conversation_key, 0, -1)
                # Contar quantas mensagens foram enviadas pelo usuário
                user_message_count = sum(1 for msg in messages if json.loads(msg).get('role', '') == 'user')
            else:
                user_message_count = 0
                thread_id = ''

            # Se o número de mensagens for igual ao anterior e os dados já existirem, manter os dados antigos
            if user_message_count == previous_message_count and not previous_data.empty:
                data.append(previous_data.iloc[0].to_dict())
                continue
            else:
                # Sempre regenerar as análises quando o número de mensagens aumentar
                if thread_id:
                    # Processar mensagens para gerar o resumo e outras informações
                    mensagens = []
                    for msg in messages:
                        msg_obj = json.loads(msg)
                        role = msg_obj.get('role', '')
                        content = msg_obj.get('content', '')
                        if role == "user":
                            mensagens.append(f"Usuário: {content}")
                        elif role == "assistant":
                            mensagens.append(f"Assistente: {content}")

                    
                    mensagens_texto = '\n'.join(mensagens[-20:])  # Pega as últimas 20 mensagens

                    # Gerar análises usando as funções correspondentes
                    resumo = gerar_resumo_conversa(mensagens_texto, phone_number, ai_name, ai_objectives)
                    salvar_analise_no_redis(redis_client, phone_number, 'resumo', resumo)

                    data_ia = gerar_data(mensagens_texto, phone_number)
                    salvar_analise_no_redis(redis_client, phone_number, 'data', data_ia)

                    user_data = gerar_nome(mensagens_texto, phone_number, ai_name)
                    salvar_analise_no_redis(redis_client, phone_number, 'nome', user_data)

                    classificacao = gerar_classificacao(mensagens_texto, phone_number, ai_name)
                    salvar_analise_no_redis(redis_client, phone_number, 'classificacao', classificacao)
                else:
                    resumo = "Sem resumo disponível"
                    data_ia = ""
                    user_data = "Nome não fornecido"
                    classificacao = "Não classificado"
                    mensagens_texto = ''

                # Gerar o link do WhatsApp Web para contato direto
                whatsapp_link = f"https://wa.me/55{normalized_phone_number}"

                # Atualizar os campos específicos para o usuário existente ou criar novo
                if not previous_data.empty:
                    updated_row = previous_data.iloc[0].to_dict()
                    updated_row.update({
                        'Data de Criação': normalizar_data(data_ia),
                        'Resumo da Conversa (IA) 🤖': resumo,
                        'Mensagens': mensagens_texto,
                        'Nº User Messages': user_message_count,
                        'Status': classificacao,
                        'Nome do usuário': user_data,
                        'Thread ID': thread_id,
                        'Falar com Usuário': whatsapp_link
                    })
                else:
                    updated_row = {
                        'Selecionado': False,
                        'Data de Criação': normalizar_data(data_ia),
                        'Nome do usuário': user_data,
                        'Status': classificacao,
                        'Número de WhatsApp': normalized_phone_number,
                        'Resumo da Conversa (IA) 🤖': resumo,
                        'Mensagens': mensagens_texto,
                        'Nº User Messages': user_message_count,
                        'Thread ID': thread_id,
                        'Falar com Usuário': whatsapp_link
                    }
                data.append(updated_row)

        # Converter os dados para DataFrame
        df = pd.DataFrame(data)

        # Remover quebras de linha no campo 'Resumo da Conversa (IA) 🤖' para evitar múltiplas linhas no CSV
        df['Resumo da Conversa (IA) 🤖'] = df['Resumo da Conversa (IA) 🤖'].apply(lambda x: ' '.join(x.splitlines()))

        # Adicionar a coluna DDD, que pega os 2 primeiros dígitos do número de WhatsApp
        df['DDD'] = df['Número de WhatsApp'].apply(lambda x: x[:2])

        # Ordenar o dataframe
        df = df.sort_values(by='Data de Criação', ascending=False)

        # Salvar os dados processados no Redis
        salvar_dados_no_redis(redis_client, df)

        # Salvar o dataframe na sessão
        st.session_state['df'] = df

        # Restaurar o estado dos checks
        restaurar_checks_do_redis(redis_client, df)

        st.success('Dados atualizados com sucesso!')
    else:
        if df.empty:
            st.warning('Não há dados disponíveis. Clique em "Atualizar" para carregar os dados.')
            return
        else:
            # Restaurar o estado dos checks
            restaurar_checks_do_redis(redis_client, df)

    # Exibir o dataframe filtrado
    updated_df = st.data_editor(
        df_filtered,
        column_config={
            "Selecionado": st.column_config.CheckboxColumn(
                label="Selecionar Usuário",  # Nome da coluna de checkbox
                help="Selecione este usuário para ações futuras",
                default=False  # Valor padrão para o checkbox
            ),
            "Falar com Usuário": st.column_config.LinkColumn(
                label="Falar com Usuário",
                help="Clique para contatar o usuário via WhatsApp"
            ),
            "Mensagens": st.column_config.TextColumn(
                label="Mensagens",
                help="Conversa completa entre o usuário e a IA",
                width="large"  # Ajuste conforme necessário
            )
        },
        hide_index=True  # Esconder o índice do DataFrame
    )

    # Adicionando um botão para salvar o estado
    if st.button("Salvar Seleções"):
        salvar_checks_no_redis(redis_client, updated_df)
        st.toast("Seleções salvas com sucesso!", icon="✅")
    
    # Salvar o dataframe em um arquivo CSV após gerar a tabela
    csv_file_path = "data/relatorios_conversas.csv"
    df.to_csv(csv_file_path, index=False)
    st.toast((f"Relatório salvo como {csv_file_path}"), icon="✅")

    # Oferecer o download para o usuário
    st.download_button(
        label="Baixar relatório em CSV",
        data=df.to_csv(index=False).encode('utf-8'),
        file_name=csv_file_path,
        mime='text/csv'
    )

# Função para o dashboard
def dashboard_bi():
    # Título com ícone
    st.markdown(
        "<h1 style='text-align: center; font-size: 36px;'>📊 Business Intelligence Dashboard</h1>",
        unsafe_allow_html=True
    )
#inicio nova função arquivo vazio
import os  # Adicione essa importação no topo do arquivo, caso ainda não esteja lá.

def dashboard_bi():
    # Título com ícone
    st.markdown(
        "<h1 style='text-align: center; font-size: 36px;'>📊 Business Intelligence Dashboard</h1>",
        unsafe_allow_html=True
    )

    # Caminho do arquivo CSV
    csv_file_path = 'data/relatorios_conversas.csv'

    # Verificar se o arquivo existe e não está vazio
    if not os.path.exists(csv_file_path) or os.path.getsize(csv_file_path) == 0:
        st.error("O arquivo CSV 'relatorios_conversas.csv' não foi encontrado ou está vazio.")
        return

    # Carregar arquivos CSV
    df_conversas = pd.read_csv(csv_file_path)
    df_ddd_estado = pd.read_csv('data/ddd_estado_brasil.csv')
# final função arquivo vazio


    # Carregar arquivos CSV
    df_conversas = pd.read_csv('data/relatorios_conversas.csv')
    df_ddd_estado = pd.read_csv('data/ddd_estado_brasil.csv')

    # Mesclar os dados de DDD com estado
    df_conversas = df_conversas.merge(df_ddd_estado, how='left', on='DDD')

    # Adicionar o seletor de período com uma chave única
    period_options = ['Completo', 'Último mês', 'Últimos 14 dias', 'Últimos 7 dias', 'Ontem', 'Hoje']
    selected_period = st.selectbox('Selecione o período', period_options, key='dashboard_period_selector')

    # Obter a data atual
    today = datetime.today()

    # Converter 'Data de Criação' para datetime
    df_conversas['Data de Criação'] = pd.to_datetime(
        df_conversas['Data de Criação'],
        format='%d/%m/%y %H:%M:%S',
        dayfirst=True,
        errors='coerce'
    )

    # Aplicar o filtro de acordo com o período selecionado
    if selected_period == 'Último mês':
        start_date = today - timedelta(days=30)
        mask = df_conversas['Data de Criação'] >= start_date
        df_filtered = df_conversas[mask]
    elif selected_period == 'Últimos 14 dias':
        start_date = today - timedelta(days=14)
        mask = df_conversas['Data de Criação'] >= start_date
        df_filtered = df_conversas[mask]
    elif selected_period == 'Últimos 7 dias':
        start_date = today - timedelta(days=7)
        mask = df_conversas['Data de Criação'] >= start_date
        df_filtered = df_conversas[mask]
    elif selected_period == 'Ontem':
        yesterday = today - timedelta(days=1)
        mask = df_conversas['Data de Criação'].dt.date == yesterday.date()
        df_filtered = df_conversas[mask]
    elif selected_period == 'Hoje':
        mask = df_conversas['Data de Criação'].dt.date == today.date()
        df_filtered = df_conversas[mask]
    else:
        df_filtered = df_conversas  # 'Completo', não aplica filtro

    # Cálculo dos KPIs
    total_conversas = len(df_filtered)
    media_mensagens_por_conversa = df_filtered['Nº User Messages'].mean()
    taxa_satisfacao = (
        len(df_filtered[df_filtered['Resumo da Conversa (IA) 🤖'].str.contains("satisfação|agradecimento|obrigado|obrigada", case=False, na=False)]) / total_conversas * 100
        if total_conversas > 0 else 0
    )

    # Layout com KPIs
    st.markdown(
        "<div style='background-color:#171d2a; border-radius: 10px; padding: 20px;'>",
        unsafe_allow_html=True
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("Total de Conversas", f"{total_conversas:,}", "📈", delta_color="off")
    col2.metric("Média de Mensagens por Conversa", f"{media_mensagens_por_conversa:.2f}", "💬", delta_color="off")
    col3.metric("Taxa de Satisfação do Usuário (%)", f"{taxa_satisfacao:.2f}%", "😊", delta_color="off")
    st.markdown("</div><br>", unsafe_allow_html=True)

    # Gráficos lado a lado com layout em colunas e bordas arredondadas
    col4, col5 = st.columns(2)
    with col4:
        st.markdown(
            "<div style='background-color:#171d2a; border-radius: 10px; padding: 20px;'>",
            unsafe_allow_html=True
        )
        st.subheader("📊 Distribuição dos Status dos Leads")
        fig_status = px.pie(
            df_filtered,
            names='Status',
            title='Distribuição dos Status dos Leads',
            color_discrete_sequence=px.colors.qualitative.Pastel,
            height=600,
            width=700
        )
        st.plotly_chart(fig_status)
        st.markdown("</div>", unsafe_allow_html=True)

    with col5:
        st.markdown(
            "<div style='background-color:#171d2a; border-radius: 10px; padding: 20px;'>",
            unsafe_allow_html=True
        )
        st.subheader("📍 Conversas por Estado")
        estado_counts = df_filtered['Estado'].value_counts().reset_index()
        estado_counts.columns = ['Estado', 'Quantidade']
        fig_estado = px.bar(
            estado_counts,
            x='Estado',
            y='Quantidade',
            title="Conversas por Estado",
            color='Quantidade',
            color_continuous_scale='Blues',
            height=600,
            width=850
        )
        st.plotly_chart(fig_estado)
        st.markdown("</div>", unsafe_allow_html=True)

    # Gráfico de evolução no tempo (full width)
    st.markdown(
        "<br><div style='background-color:#171d2a; border-radius: 10px; padding: 20px;'>",
        unsafe_allow_html=True
    )
    st.subheader("📈 Mensagens ao longo do tempo")

    # Agrupando por dia
    df_filtered['Data de Criação'] = df_filtered['Data de Criação'].dt.date
    df_conversas_por_data = df_filtered.groupby('Data de Criação').size().reset_index(name='Quantidade')

    fig_evolucao = px.line(
        df_conversas_por_data,
        x='Data de Criação',
        y='Quantidade',
        title="Mensagens ao longo do tempo",
        line_shape='spline',
        markers=True
    )
    fig_evolucao.update_layout(xaxis_title="Data", yaxis_title="Conversas", width=1200, height=500)
    st.plotly_chart(fig_evolucao, use_container_width=True)
    st.markdown("</div><br>", unsafe_allow_html=True)

    # Gráficos lado a lado
    col6, col7 = st.columns(2)
    with col6:
        st.markdown(
            "<div style='background-color:#171d2a; border-radius: 10px; padding: 20px;'>",
            unsafe_allow_html=True
        )
        st.subheader("🌍 Localização dos Leads")
        df_conversas_filtrado = df_filtered.dropna(subset=['Estado', 'DDD', 'Nº User Messages'])
        fig_ddd = px.treemap(
            df_conversas_filtrado,
            path=['Estado', 'DDD'],
            values='Nº User Messages',
            title="Conversas por Estados",
            color='Nº User Messages',
            color_continuous_scale='RdBu',
            height=600
        )
        st.plotly_chart(fig_ddd)
        st.markdown("</div>", unsafe_allow_html=True)

    with col7:
        st.markdown(
            "<div style='background-color:#171d2a; border-radius: 10px; padding: 20px;'>",
            unsafe_allow_html=True
        )
        st.subheader("💬 Mensagens por Usuário")
        fig_mensagens = px.bar(
            df_filtered.sort_values(by='Nº User Messages', ascending=False),
            x='Nome do usuário',
            y='Nº User Messages',
            title="Mensagens por Usuário",
            color='Nº User Messages',
            color_continuous_scale='Viridis',
            height=600,
            width=850
        )
        st.plotly_chart(fig_mensagens)
        st.markdown("</div>", unsafe_allow_html=True)


# Lógica para alternar entre páginas
if pagina_selecionada == "Painel de Mensagem":
    painel_mensagem()
elif pagina_selecionada == "Dashboard BI":
    dashboard_bi()
elif pagina_selecionada == "Configurações":
    pagina_configuracoes()




# streamlit run dashboard.py