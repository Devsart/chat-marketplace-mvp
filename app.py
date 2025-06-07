import os
import uuid
import requests
from flask import Flask, request, jsonify, render_template, session as session_data
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import re
from datetime import datetime, timezone
from collections import defaultdict
import random
import logging
import copy
import json
from pydantic import BaseModel, Field


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dapojNDOUIANIKDAHIODHAKMsdnawuiohqSJ213141SAMjmopdja")

if not app.debug:
    app.logger.setLevel(logging.INFO)
else:
    # Força o logger a mostrar tudo no modo debug
    app.logger.setLevel(logging.DEBUG)
    # Garante que o handler do Flask envie logs para o terminal
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    handler.setFormatter(formatter)
    if not app.logger.handlers:
        app.logger.addHandler(handler)
    else:
        # Evita handlers duplicados
        app.logger.handlers.clear()
        app.logger.addHandler(handler)

try:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firebase Admin SDK inicializado com sucesso.")
except Exception as e:
    print(f"ERRO CRÍTICO: Falha ao inicializar o Firebase Admin SDK: {e}")
    db = None

GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GEMINI_API_KEY:
    print("ALERTA: GOOGLE_API_KEY não encontrada.")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

AB_TEST_ENABLED = False
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

OPENROUTER_MODEL_A = "deepseek/deepseek-r1-0528:free"
OPENROUTER_MODEL_B = "microsoft/phi-4-reasoning:free" 
if not OPENROUTER_API_KEY:
    print("ALERTA: OPENROUTER_API_KEY não encontrada nas variáveis de ambiente.")

DEFAULT_PRODUCTS_SEED = [
    {"id": "p1", "name": "NovoPhone X12", "price": "3.499,00", "category": "Smartphone"},
    {"id": "p2", "name": "UltraBook Pro 15", "price": "7.999,00", "category": "Laptop"},
    {"id": "p3", "name": "TimeWatch S2", "price": "1.299,00", "category": "Smartwatch"},
    {"id": "p4", "name": "TabMaster 10", "price": "2.499,00", "category": "Tablet"},
    {"id": "p5", "name": "SoundBuds Plus", "price": "399,00", "category": "Fone de Ouvido"},
    {"id": "p6", "name": "PhotoSnap DSLR", "price": "4.499,00", "category": "Câmera"},
    {"id": "p7", "name": "VisionScreen 55\" 4K", "price": "3.999,00", "category": "Smart TV"},
    {"id": "p8", "name": "GameBox X", "price": "2.999,00", "category": "Console de Videogame"}
]

def seed_initial_products():
    if not db:
        app.logger.error("Firestore não inicializado. Seed não executado.")
        return
    try:
        products_ref = db.collection('products')
        docs = products_ref.limit(1).stream()
        if not list(docs): 
            app.logger.info("Populando 'products' com dados padrão...")
            for product_data in DEFAULT_PRODUCTS_SEED:
                products_ref.document(product_data['id']).set(product_data)
            app.logger.info(f"{len(DEFAULT_PRODUCTS_SEED)} produtos adicionados.")
        else:
            app.logger.info("'products' já contém dados.")
    except Exception as e:
        app.logger.error(f"Erro no seed de produtos: {e}")

def load_products_from_firestore():
    if not db:
        app.logger.error("Firestore não inicializado. Não é possível carregar produtos.")
        return []
    try:
        products_ref = db.collection('products')
        docs = products_ref.stream()
        products_list = [doc.to_dict() for doc in docs if all(k in doc.to_dict() for k in ['id', 'name', 'price', 'category'])]
        if not products_list: app.logger.warning("Nenhum produto carregado do Firestore.")
        return products_list
    except Exception as e:
        app.logger.error(f"Erro ao carregar produtos do Firestore: {e}")
        return []

def get_base_system_prompt():
    products_list = load_products_from_firestore()
    products_string = "\n".join([f"- {p['category']}: {p['name']} - R$ {p['price']}" for p in products_list])
    if not products_string: products_string = "Nenhum produto disponível no momento."

    return f"""Você é 39A-na, assistente de vendas virtual do "Marketplace" de eletrônicos.
                Seu objetivo: ajudar clientes a encontrar produtos, adicioná-los ao carrinho, e se desejarem finalizar a compra, coletar Nome, Email e Telefone para gerar uma proposta comercial COM UM LINK DE CHECKOUT FALSO.
                Mantenha tom amigável e profissional, sempre em português brasileiro.
                Produtos disponíveis:
                {products_string}

                FLUXO DE VENDA:
                1. AJUDA NA ESCOLHA: Ajude o cliente a encontrar um produto.
                2. CONFIRMA CARRINHO: Ao identificar um produto, PERGUNTE se o cliente quer adicioná-lo ao carrinho. Ex: "O NovoPhone X12 custa R$ 3.499,00. Gostaria de adicioná-lo ao carrinho?"
                3. APÓS ADICIONAR: Se sim, informe que foi adicionado e PERGUNTE: "Gostaria de adicionar mais itens ou finalizar a compra?"
                4. CONTINUAR COMPRANDO: Se quiser mais itens, volte ao passo 1.
                5. FINALIZAR COMPRA: Se quiser finalizar, inicie a coleta de dados: Nome completo, Email, Telefone (com DDD). SEJA RIGOROSO E PEÇA UM DADO POR VEZ.
                6. PROPOSTA FINAL: Após coletar todos os dados, gere uma proposta com TODOS OS ITENS DO CARRINHO, o VALOR TOTAL, e o LINK DE CHECKOUT FALSO.

                REGRAS IMPORTANTES:
                - NÃO adivinhe informações. Peça explicitamente.
                - Se uma entrada para nome/email/telefone for inválida, peça novamente com gentileza, explicando o formato esperado.
                - O LINK DE CHECKOUT (falso) DEVE SER ENVIADO SOMENTE NA PROPOSTA FINAL, após todos os dados coletados e deve ter um formato http://marketplace-39A/{{id_fake_da_proposta}}.
                - Pagamento/garantia: Mencione parcelamento 12x sem juros e garantia estendida disponível se perguntado.

                VOCÊ DEVE RETORNAR A RESPOSTA SEMPRE NESTE FORMATO JSON VÁLIDO:
                {{
                    "chat_state": "fase_atual",
                    "resposta": "Sua resposta amigável e profissional aqui.",
                    "product_selected_for_cart": {{"nome": "Nome do produto", "preço": "Preço do produto"}},
                    "cart": [   {{"nome": "Nome do produto", "preço": "Preço do produto"}} ],
                    "total_value": "Valor total do carrinho em produtos, formatado como float com vírgula",
                    "customer_data": {{
                    "name": "Nome do cliente",
                    "email": "Email do cliente",
                    "phone": "Telefone do cliente"
                    }},
                    "last_input_invalid": false
                }}
            """

def build_llm_prompt_context_instruction():
    instruction = "INSTRUÇÃO PARA ESTA RESPOSTA ESPECÍFICA: "
    state = session_data["chat_state"]
    customer = session_data["customer_data"]
    product_selected = customer.get("product_selected_for_cart")
    cart_items = customer.get("cart", [])
    last_input_invalid = session_data.get("last_input_invalid", False)

    if state == 'INITIAL' or state == 'PRODUCT_QUERY':
        instruction += "Saudação inicial ou busca de produtos. Pergunte o que o cliente procura. Se já há itens no carrinho, pode mencioná-los brevemente (ex: 'Seu carrinho atual: [itens]')."
    else:
        instruction += "Responda ao usuário, considerando o estado atual da conversa."
    
    session_data["last_input_invalid"] = False
    return instruction

def call_gemini_api(prompt_history):
    if not GEMINI_API_KEY:
        app.logger.error("API Key Gemini não configurada.")
        return "ERRO INTERNO: IA indisponível."
    payload = {
        "contents": prompt_history,
        "generationConfig": {"temperature": 0.65, "maxOutputTokens": 500}
    }
    headers = {'Content-Type': 'application/json'}
    try:
        response = requests.post(GEMINI_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        if result.get("candidates") and result["candidates"][0].get("content") and result["candidates"][0]["content"].get("parts"):
            return result["candidates"][0]["content"]["parts"][0]["text"]
        # ... (resto do tratamento de erro da API)
        app.logger.error(f"Resposta API Gemini inesperada: {result}")
        return "Desculpe, não consegui processar (resposta IA inesperada)."
    except Exception as e:
        app.logger.error(f"Erro API Gemini: {e}")
        return "Ops! Problema com nossa IA. Tente novamente."

def call_openrouter_api(system_prompt, chat_history):
    if not OPENROUTER_API_KEY:
        app.logger.error("API Key do OpenRouter não configurada.")
        return "ERRO INTERNO: A configuração da IA está ausente."

    ab_group = session_data.get("ab_test_group")
    if AB_TEST_ENABLED and ab_group == 'B':
        model_to_use = OPENROUTER_MODEL_B
        app.logger.info(f"Sessão no grupo B. Usando modelo: {model_to_use}")
    else:
        model_to_use = OPENROUTER_MODEL_A
        app.logger.info(f"Sessão no grupo A. Usando modelo: {model_to_use}")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5001", 
        "X-Title": "Marketplace Chatbot"
    }

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_history)

    payload = {
        "model": model_to_use,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 600
    }

    try:
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()

        if result.get("choices") and result["choices"][0].get("message") and result["choices"][0]["message"].get("content"):
            return result["choices"][0]["message"]["content"].strip()
        else:
            app.logger.error(f"Resposta da API OpenRouter inesperada: {result}")
            return "Desculpe, não consegui processar a sua solicitação (resposta da IA foi inesperada)."
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Erro de comunicação com a API OpenRouter: {e}")
        if e.response is not None:
            app.logger.error(f"Detalhes do erro da API: {e.response.text}")
        return "Ops! Tive um problema de comunicação com nossa IA. Poderia tentar novamente?"
    except Exception as e:
        app.logger.error(f"Erro inesperado ao chamar a API OpenRouter: {e}")
        return "Desculpe, ocorreu um erro interno ao tentar processar sua solicitação."

def save_session_to_firestore(session_data):
    """Salva o estado final da sessão atual no Firestore."""
    if not db or not session_data.get("session_uuid"):
        return

    try:
        session_uuid = session_data["session_uuid"]
        ab_group = session_data.get("ab_test_group")
        
        if AB_TEST_ENABLED and ab_group == 'B':
            model_used = OPENROUTER_MODEL_B
        elif AB_TEST_ENABLED:
            model_used = OPENROUTER_MODEL_A
        else:
            model_used = "Gemini-2.0-flash"  # Modelo padrão se A/B não estiver ativo
        

        data_to_save = {
            "session_uuid": session_uuid,
            "final_state": session_data["chat_state"],
            "model_used": model_used,
            "timestamp_utc": datetime.now(timezone.utc),
            "cart_items": len(session_data["customer_data"]["cart"]),
            "total_value": session_data["total_value"]
        }

        sessions_ref = db.collection('sessions')
        sessions_ref.document(session_uuid).set(data_to_save)
        app.logger.info(f"Sessão {session_uuid} salva no Firestore.")

    except Exception as e:
        app.logger.error(f"Erro ao salvar sessão {session_data.get('session_uuid')} no Firestore: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dash')
def dashboard():
    """Renderiza a página HTML do dashboard."""
    return render_template('dashboard.html')

@app.route('/list_models')
def list_models():
    """Busca e retorna uma lista de nomes de modelos únicos da coleção de sessões."""
    if not db:
        return jsonify({"error": "Firestore não está disponível"}), 500
    try:
        sessions_ref = db.collection('sessions').select(['model_used']).stream()
        unique_models = set(session.get('model_used') for session in sessions_ref if session.get('model_used'))
        return jsonify(sorted(list(unique_models)))
    except Exception as e:
        app.logger.error(f"Erro ao listar modelos: {e}")
        return jsonify({"error": "Falha ao buscar lista de modelos"}), 500


@app.route('/dashboard_data')
def dashboard_data():
    """Fornece os dados processados para os gráficos do dashboard, com filtro opcional por modelo."""
    if not db:
        return jsonify({"error": "Firestore não está disponível"}), 500

    try:
        selected_model = request.args.get('model')
        
        query = db.collection('sessions')
        if selected_model:
            app.logger.info(f"Filtrando dados do dashboard para o modelo: {selected_model}")
            query = query.where('model_used', '==', selected_model)
        
        sessions = [doc.to_dict() for doc in query.stream()]

        # Processamento para o gráfico de barras
        states_by_model = defaultdict(lambda: defaultdict(int))
        all_states = set()
        model_labels = set()

        for session in sessions:
            model = session.get('model_used', 'Desconhecido')
            state = session.get('final_state', 'UNKNOWN')
            states_by_model[model][state] += 1
            all_states.add(state)
            model_labels.add(model)
        
        sorted_states = sorted(list(all_states))
        bar_chart_datasets = []
        for model_label in sorted(list(model_labels)):
            bar_chart_datasets.append({
                "label": model_label,
                "data": [states_by_model[model_label].get(state, 0) for state in sorted_states]
            })

        bar_chart_data = {"labels": sorted_states, "datasets": bar_chart_datasets}


        # Processamento para o gráfico de série temporal
        time_series_by_model = defaultdict(lambda: defaultdict(lambda: {'total': 0, 'finalized': 0}))
        for session in sessions:
            model = session.get('model_used', 'Desconhecido')
            timestamp = session.get('timestamp_utc')
            if not isinstance(timestamp, datetime): continue 

            date_str = timestamp.strftime('%Y-%m-%d')
            time_series_by_model[model][date_str]['total'] += 1
            if session.get('final_state') == 'proposta_final':
                time_series_by_model[model][date_str]['finalized'] += 1
        
        time_series_datasets = []
        for model_label, date_data in time_series_by_model.items():
            dataset = {"label": model_label, "data": []}
            for date_str in sorted(date_data.keys()):
                daily_data = date_data[date_str]
                rate = (daily_data['finalized'] / daily_data['total'] * 100) if daily_data['total'] > 0 else 0
                dataset["data"].append({"x": date_str, "y": round(rate, 2)})
            time_series_datasets.append(dataset)
        
        time_series_data = {"datasets": time_series_datasets}

        return jsonify({
            "bar_chart_data": bar_chart_data,
            "time_series_data": time_series_data
        })

    except Exception as e:
        app.logger.error(f"Erro ao buscar dados do dashboard: {e}")
        return jsonify({"error": "Falha ao processar dados do dashboard"}), 500

@app.route('/initialize_chat', methods=['POST'])
def initialize_chat():
    if not db:
        return jsonify({"bot_response": "ERRO: Banco de dados indisponível.", "chat_state": "ERROR"}), 500
    
    if session_data.get("session_uuid") and not session_data.get("session_saved"):
        session_to_save = copy.deepcopy(session_data) # Cria uma cópia profunda para garantir a integridade dos dados
        app.logger.info(f"Salvando sessão anterior abandonada: {session_to_save['session_uuid']}")
        save_session_to_firestore(session_to_save)
    
    session_data.clear()
    session_data["customer_data"] = {
        "name": None, "email": None, "phone": None, 
        "product_selected_for_cart": None, 
        "cart": []
    }
    session_data["chat_state"] = 'PRODUCT_QUERY' 
    session_data["chat_history_for_llm"] = []
    session_data["last_input_invalid"] = False
    session_data["session_uuid"] = str(uuid.uuid4())
    session_data["session_saved"] = False
    session_data["total_value"] = 0.0


    if AB_TEST_ENABLED:
        session_data["ab_test_group"] = random.choice(['A', 'B'])
        app.logger.info(f"Nova sessão iniciada. Teste A/B ativo. Grupo atribuído: {session_data['ab_test_group']}")
    else:
        session_data["ab_test_group"] = 'A' # Padrão para grupo A se o teste estiver desativado
        app.logger.info("Nova sessão iniciada. Teste A/B inativo. Usando modelo padrão do grupo A.")

    initial_greeting = "Olá! Bem-vindo ao Marketplace. Sou 39A-na, sua assistente virtual. O que você está procurando hoje?"
    session_data["chat_history_for_llm"].append({"role": "model", "parts": [{"text": initial_greeting}]})
    return jsonify({"bot_response": initial_greeting, "chat_state": session_data["chat_state"]})

@app.route('/send_message', methods=['POST'])
def send_message():
    if not db:
        return jsonify({"bot_response": "ERRO: Banco de dados indisponível.", "chat_state": "ERROR"}), 500

    data = request.get_json()
    user_input = data.get('user_input', '').strip()
    session_data["last_input_invalid"] = False 

    if not user_input:
        return jsonify({"bot_response": "Por favor, diga algo.", "chat_state": session_data["chat_state"]}), 400

    if session_data["chat_state"] == 'FINALIZED':
        return jsonify({"bot_response": "Obrigado! Para uma nova compra, por favor, reinicie a conversa.", "chat_state": session_data["chat_state"]})

    session_data["chat_history_for_llm"].append({"role": "user", "parts": [{"text": user_input}]})
    
    current_state_before_llm = session_data["chat_state"]
    customer = session_data["customer_data"]

    if current_state_before_llm == 'AWAITING_NAME':
        words = user_input.split()
        if len(user_input) > 3 and len(words) >= 2 and words[0][0].isupper() and all(word[0].isalpha() or word[0].isdigit()==False for word in words if len(word)>0): # Verifica se todas as palavras começam com letra
            customer["name"] = user_input
            session_data["chat_state"] = 'AWAITING_EMAIL'
        else:
            session_data["last_input_invalid"] = True
    elif current_state_before_llm == 'AWAITING_EMAIL':
        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if re.fullmatch(email_regex, user_input):
            customer["email"] = user_input
            session_data["chat_state"] = 'AWAITING_PHONE'
        else:
            session_data["last_input_invalid"] = True
    elif current_state_before_llm == 'AWAITING_PHONE':
        cleaned_phone = re.sub(r'\D', '', user_input)
        if 10 <= len(cleaned_phone) <= 11:
            customer["phone"] = user_input 
            session_data["chat_state"] = 'PROPOSAL_READY'
        else:
            session_data["last_input_invalid"] = True
    llm_payload_history = []
    system_prompt = get_base_system_prompt()
    context_instruction = build_llm_prompt_context_instruction()
    
    llm_payload_history.append({"role": "user", "parts": [{"text": system_prompt + "\n\n" + context_instruction}]})
    llm_payload_history.append({"role": "model", "parts": [{"text": "Entendido."}]})
    llm_payload_history.extend(session_data["chat_history_for_llm"])

    if AB_TEST_ENABLED:
        bot_response = call_openrouter_api(system_prompt, session_data["chat_history_for_llm"])
    else:
        bot_response = call_gemini_api(llm_payload_history)
    bot_response_text = bot_response
    match = re.search(r'\{.*\}', bot_response, re.DOTALL)
    try:
        bot_response = json.loads(bot_response)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', bot_response, re.DOTALL)
        if match:
            clean_json_str = match.group(0)
            bot_response = json.loads(clean_json_str)
    if not isinstance(bot_response, dict):
        bot_response_text = bot_response
    else:
        bot_response_text = bot_response["resposta"] if isinstance(bot_response, dict) else bot_response
        session_data["chat_state"] = bot_response["chat_state"] if isinstance(bot_response, dict) else session_data["chat_state"]
        session_data["customer_data"]["product_selected_for_cart"] = bot_response.get("product_selected_for_cart", None)
        session_data["customer_data"]["cart"] = bot_response.get("cart", [])
        session_data["last_input_invalid"] = bot_response.get("last_input_invalid", False)
        session_data["total_value"] = bot_response.get("total_value", 0.0)
    session_data["chat_history_for_llm"].append({"role": "model", "parts": [{"text": bot_response_text}]})

    if isinstance(bot_response_text, str) and re.search(r'https?://', bot_response_text):
        session_data["chat_state"] = "proposta_final"
    
    app.logger.info(session_data)
    save_session_to_firestore(session_data)
    return jsonify({"bot_response": bot_response_text, "chat_state": session_data["chat_state"]})

if __name__ == '__main__':
    if not GEMINI_API_KEY: print("AVISO: GOOGLE_API_KEY não definida.")
    if not db: print("ERRO CRÍTICO: Firestore não inicializado.")
    else:
        with app.app_context(): 
            seed_initial_products()
    
    app.run(debug=True, port=5001)