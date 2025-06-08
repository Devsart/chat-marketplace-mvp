import os
import uuid
from flask import Flask, request, jsonify, render_template, session as session_data
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import re
from datetime import datetime
from collections import defaultdict
import random
import logging
import copy
import json
from utils.constants import AB_TEST_ENABLED
from utils.firebase import seed_initial_products, save_session_to_firestore
from utils.llm import call_gemini_api, call_openrouter_api, get_base_system_prompt, build_llm_prompt_context_instruction

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dapojNDOUIANIKDAHIODHAKMsdnawuiohqSJ213141SAMjmopdja")

try:
    cred = credentials.ApplicationDefault()
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    logging.info("Firebase Admin SDK inicializado com sucesso.")
except Exception as e:
    logging.error(f"ERRO CRÍTICO: Falha ao inicializar o Firebase Admin SDK: {e}")
    db = None

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
        logging.error(f"Erro ao listar modelos: {e}")
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
            logging.info(f"Filtrando dados do dashboard para o modelo: {selected_model}")
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
        logging.error(f"Erro ao buscar dados do dashboard: {e}")
        return jsonify({"error": "Falha ao processar dados do dashboard"}), 500

@app.route('/initialize_chat', methods=['POST'])
def initialize_chat():
    if not db:
        return jsonify({"bot_response": "ERRO: Banco de dados indisponível.", "chat_state": "ERROR"}), 500
    
    if session_data.get("session_uuid") and not session_data.get("session_saved"):
        session_to_save = copy.deepcopy(session_data) # Cria uma cópia profunda para garantir a integridade dos dados
        logging.info(f"Salvando sessão anterior abandonada: {session_to_save['session_uuid']}")
        save_session_to_firestore(db, session_to_save)
    
    session_data.clear()
    session_data["customer_data"] = {
        "name": None, "email": None, "phone": None, 
        "product_selected_for_cart": None, 
        "cart": []
    }
    session_data["chat_state"] = 'ajuda_na_escolha' 
    session_data["chat_history_for_llm"] = []
    session_data["last_input_invalid"] = False
    session_data["session_uuid"] = str(uuid.uuid4())
    session_data["session_saved"] = False
    session_data["total_value"] = 0.0


    if AB_TEST_ENABLED:
        session_data["ab_test_group"] = random.choice(['A', 'B'])
        logging.info(f"Nova sessão iniciada. Teste A/B ativo. Grupo atribuído: {session_data['ab_test_group']}")
    else:
        session_data["ab_test_group"] = 'A' # Padrão para grupo A se o teste estiver desativado
        logging.info("Nova sessão iniciada. Teste A/B inativo. Usando modelo padrão do grupo A.")

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
    system_prompt = get_base_system_prompt(db)
    context_instruction = build_llm_prompt_context_instruction(session_data)
    
    llm_payload_history.append({"role": "user", "parts": [{"text": system_prompt + "\n\n" + context_instruction}]})
    llm_payload_history.append({"role": "model", "parts": [{"text": "Entendido."}]})
    llm_payload_history.extend(session_data["chat_history_for_llm"])

    if AB_TEST_ENABLED:
        bot_response = call_openrouter_api(system_prompt, session_data["chat_history_for_llm"], session_data)
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
    
    logging.info(session_data)
    save_session_to_firestore(db, session_data)
    return jsonify({"bot_response": bot_response_text, "chat_state": session_data["chat_state"]})

if __name__ == '__main__':
    if not db: logging.error("ERRO CRÍTICO: Firestore não inicializado.")
    else:
        with app.app_context(): 
            seed_initial_products(db)
    
    logging.basicConfig(level=logging.DEBUG)
    app.run(debug=True, port=5001)