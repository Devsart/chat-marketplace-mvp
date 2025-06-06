import os
import uuid
import requests
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import re

load_dotenv()

app = Flask(__name__)

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

session_data = {
    "customer_data": {
        "name": None, "email": None, "phone": None, 
        "product_selected_for_cart": None,
        "cart": []
    },
    "chat_state": 'INITIAL',
    "chat_history_for_llm": [],
    "last_input_invalid": False
}

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
                - O LINK DE CHECKOUT (falso) DEVE SER ENVIADO SOMENTE NA PROPOSTA FINAL, após todos os dados coletados.
                - Pagamento/garantia: Mencione parcelamento 12x sem juros e garantia estendida disponível se perguntado.
            """

def calculate_total_cart_value(cart):
    total = 0.0
    for item in cart:
        try:
            price_str = item['price'].replace('.', '').replace(',', '.')
            total += float(price_str)
        except ValueError:
            app.logger.error(f"Erro ao converter preço para o produto: {item['name']}")
    return total

def format_cart_for_display(cart):
    if not cart: return "Carrinho vazio."
    items_str = []
    for item in cart:
        items_str.append(f"{item['name']} (R$ {item['price']})")
    return ", ".join(items_str)

def build_llm_prompt_context_instruction():
    instruction = "INSTRUÇÃO PARA ESTA RESPOSTA ESPECÍFICA: "
    state = session_data["chat_state"]
    customer = session_data["customer_data"]
    product_selected = customer.get("product_selected_for_cart")
    cart_items = customer.get("cart", [])
    last_input_invalid = session_data.get("last_input_invalid", False)

    if state == 'INITIAL' or state == 'PRODUCT_QUERY':
        instruction += "Saudação inicial ou busca de produtos. Pergunte o que o cliente procura. Se já há itens no carrinho, pode mencioná-los brevemente (ex: 'Seu carrinho atual: [itens]')."
    elif state == 'AWAITING_PRODUCT_CHOICE':
        instruction += "Ajude o cliente a escolher um produto específico da lista. Após ele indicar um produto, você deve confirmar o produto e preço, e então perguntar se ele quer adicionar ao carrinho (transitando para AWAITING_ADD_TO_CART_CONFIRMATION)."
    elif state == 'AWAITING_ADD_TO_CART_CONFIRMATION':
        if product_selected:
            instruction += f"O cliente demonstrou interesse no produto: {product_selected['name']} (R$ {product_selected['price']}). PERGUNTE CLARAMENTE se ele deseja adicionar este item ao carrinho. Ex: 'O {product_selected['name']} custa R$ {product_selected['price']}. Gostaria de adicioná-lo ao seu carrinho?' Responda apenas a esta pergunta."
        else: # Fallback, deveria ter um produto selecionado aqui
            instruction += "ERRO DE FLUXO: Nenhum produto foi pré-selecionado para adicionar ao carrinho. Volte a ajudar o cliente a escolher um produto."
            session_data["chat_state"] = 'AWAITING_PRODUCT_CHOICE'
    elif state == 'PRODUCT_ADDED_ASK_MORE':
        cart_display = format_cart_for_display(cart_items)
        instruction += f"O último produto foi adicionado ao carrinho. Carrinho atual: {cart_display}. PERGUNTE se o cliente deseja adicionar mais itens ou finalizar a compra. Ex: 'Adicionei ao carrinho! Agora temos: {cart_display}. Deseja procurar mais algum item ou podemos finalizar sua compra?'"
    elif state == 'AWAITING_NAME':
        if not cart_items: # Segurança: não deve chegar aqui sem itens no carrinho
            instruction += "ERRO DE FLUXO: O cliente decidiu finalizar, mas o carrinho está vazio. Confirme se ele gostaria de adicionar itens antes de prosseguir."
            session_data["chat_state"] = 'PRODUCT_ADDED_ASK_MORE' # Ou AWAITING_PRODUCT_CHOICE
        elif last_input_invalid:
            instruction += f"A entrada para nome não foi válida (precisa de nome e sobrenome, mais de 3 letras, primeira maiúscula). Peça NOVAMENTE o nome completo. Ex: 'Para a proposta, preciso do seu nome completo, por favor. Como consta no seu documento?'"
        else:
            instruction += f"O cliente decidiu finalizar a compra com os itens: {format_cart_for_display(cart_items)}. Agora, peça o NOME COMPLETO. Ex: 'Ótimo! Para gerar sua proposta, qual seu nome completo?'"
    elif state == 'AWAITING_EMAIL':
        if last_input_invalid:
            instruction += f"O e-mail fornecido não pareceu válido. Peça NOVAMENTE um e-mail válido para {customer.get('name', 'cliente')}. Ex: 'Por favor, informe um e-mail no formato nome@exemplo.com.'"
        else:
            instruction += f"Nome: {customer.get('name', 'Cliente')}. Agora peça o E-MAIL. Ex: 'Obrigado, {customer.get('name', 'Cliente')}. Qual seu e-mail para contato?'"
    elif state == 'AWAITING_PHONE':
        if last_input_invalid:
            instruction += f"O telefone fornecido não pareceu válido (precisa de 10 ou 11 dígitos com DDD). Peça NOVAMENTE o telefone para {customer.get('name', 'cliente')}. Ex: 'Por favor, informe seu telefone com DDD, como (XX) XXXXX-XXXX.'"
        else:
            instruction += f"E-mail: {customer.get('email', '[email]')}. Agora peça o TELEFONE (com DDD). Ex: 'Perfeito. E qual seu telefone com DDD?'"
    elif state == 'PROPOSAL_READY':
        if all(customer.get(k) for k in ['name', 'email', 'phone']) and cart_items:
            cart_display = format_cart_for_display(cart_items)
            total_value = calculate_total_cart_value(cart_items)
            fake_link = f"https://marketplace.exemplo/finalizar_pedido/{str(uuid.uuid4())[:8]}"
            instruction += f"TODOS os dados coletados: Nome: {customer['name']}, Email: {customer['email']}, Telefone: {customer['phone']}. Carrinho: {cart_display}. Total: R$ {total_value:.2f}. Gere a PROPOSTA FINAL AMIGÁVEL, recapitulando os itens, o total, e OBRIGATORIAMENTE inclua o LINK FALSO para checkout: {fake_link}. Ex: 'Excelente, {customer['name']}! Sua proposta está pronta. Itens: {cart_display}. Valor Total: R$ {total_value:.2f}. Para finalizar, acesse: {fake_link}. Obrigado!'"
        else: 
            instruction += "ERRO DE FLUXO: Dados faltando para proposta. Verifique e peça o que falta."
            # Lógica de fallback para o estado correto
            if not cart_items: session_data["chat_state"] = 'AWAITING_PRODUCT_CHOICE'
            elif not customer.get('name'): session_data["chat_state"] = 'AWAITING_NAME'
            elif not customer.get('email'): session_data["chat_state"] = 'AWAITING_EMAIL'
            elif not customer.get('phone'): session_data["chat_state"] = 'AWAITING_PHONE'
    elif state == 'FINALIZED':
        instruction += "Proposta enviada. Agradeça e se coloque à disposição. Não inicie nova venda."
    else: # Fallback genérico
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

def find_product_in_text(text, consider_selected_product=False):
    if not text: return None
    lower_text = text.lower()
    products_list = load_products_from_firestore()
    if not products_list: return None

    if consider_selected_product and session_data["customer_data"].get("product_selected_for_cart"):
        selected = session_data["customer_data"]["product_selected_for_cart"]
        if selected["name"].lower() in lower_text:
            return selected

    for product in products_list:
        if product["name"].lower() in lower_text:
            return product
        product_name_parts = product["name"].lower().split()
        if len(product_name_parts) > 1 and all(part in lower_text for part in product_name_parts):
            return product
    return None

def process_llm_response_and_input(llm_response_text, user_input):
    state = session_data["chat_state"]
    customer = session_data["customer_data"]
    lower_user_input = user_input.lower()

    if state == 'AWAITING_PRODUCT_CHOICE':
        product = find_product_in_text(user_input)
        if product:
            customer["product_selected_for_cart"] = product
            session_data["chat_state"] = 'AWAITING_ADD_TO_CART_CONFIRMATION'
            app.logger.info(f"Produto '{product['name']}' identificado para carrinho. Novo estado: AWAITING_ADD_TO_CART_CONFIRMATION")
            return
    
    elif state == 'AWAITING_ADD_TO_CART_CONFIRMATION':
        product_to_add = customer.get("product_selected_for_cart")
        if product_to_add:
            if any(kw in lower_user_input for kw in ['sim', 'quero', 'pode', 'adicione', 'claro', 'ok', 'gostaria']):
                customer["cart"].append(product_to_add)
                app.logger.info(f"Produto '{product_to_add['name']}' ADICIONADO ao carrinho. Carrinho: {len(customer['cart'])} itens.")
                customer["product_selected_for_cart"] = None
                session_data["chat_state"] = 'PRODUCT_ADDED_ASK_MORE'
            elif any(kw in lower_user_input for kw in ['não', 'nao', 'agora não', 'depois', 'cancelar']):
                app.logger.info(f"Usuário NÃO quis adicionar '{product_to_add['name']}' ao carrinho.")
                customer["product_selected_for_cart"] = None
                session_data["chat_state"] = 'AWAITING_PRODUCT_CHOICE'
    
    elif state == 'PRODUCT_ADDED_ASK_MORE':
        if any(kw in lower_user_input for kw in ['finalizar', 'fechar', 'concluir', 'checkout', 'pagar', 'só isso']):
            if customer["cart"]:
                session_data["chat_state"] = 'AWAITING_NAME'
                app.logger.info("Usuário decidiu FINALIZAR COMPRA. Novo estado: AWAITING_NAME.")
            else: 
                app.logger.info("Usuário quer finalizar, mas carrinho vazio. Voltando para escolha de produto.")
                session_data["chat_state"] = 'AWAITING_PRODUCT_CHOICE'
        elif any(kw in lower_user_input for kw in ['mais itens', 'continuar', 'outro', 'ver mais', 'adicionar mais']):
            session_data["chat_state"] = 'AWAITING_PRODUCT_CHOICE'
            app.logger.info("Usuário quer ADICIONAR MAIS ITENS. Novo estado: AWAITING_PRODUCT_CHOICE.")
        
    elif state == 'PROPOSAL_READY':
         if "proposta comercial está pronta" in llm_response_text.lower() or \
           "proposta para o" in llm_response_text.lower() or \
           "marketplace.exemplo/finalizar_pedido" in llm_response_text.lower():
            session_data["chat_state"] = 'FINALIZED'
            app.logger.info("Proposta gerada pelo LLM. Novo estado: FINALIZED.")


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/initialize_chat', methods=['POST'])
def initialize_chat():
    if not db:
        return jsonify({"bot_response": "ERRO: Banco de dados indisponível.", "chat_state": "ERROR"}), 500
    
    session_data["customer_data"] = {
        "name": None, "email": None, "phone": None, 
        "product_selected_for_cart": None, 
        "cart": []
    }
    session_data["chat_state"] = 'PRODUCT_QUERY' 
    session_data["chat_history_for_llm"] = []
    session_data["last_input_invalid"] = False

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

    process_llm_response_and_input(None, user_input) 

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

    bot_response_text = call_gemini_api(llm_payload_history)
    session_data["chat_history_for_llm"].append({"role": "model", "parts": [{"text": bot_response_text}]})
    
    if not session_data["last_input_invalid"]:
         process_llm_response_and_input(bot_response_text, user_input)


    return jsonify({"bot_response": bot_response_text, "chat_state": session_data["chat_state"]})

if __name__ == '__main__':
    if not GEMINI_API_KEY: print("AVISO: GOOGLE_API_KEY não definida.")
    if not db: print("ERRO CRÍTICO: Firestore não inicializado.")
    else:
        with app.app_context(): 
            seed_initial_products()
    app.run(debug=True, port=5001)