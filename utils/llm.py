import logging
import requests
from utils.firebase import load_products_from_firestore
from utils.constants import (
    GEMINI_API_KEY, GEMINI_API_URL,
    OPENROUTER_API_KEY, OPENROUTER_API_URL,
    OPENROUTER_MODEL_A, OPENROUTER_MODEL_B,
    AB_TEST_ENABLED
)

def get_base_system_prompt(db):
    products_list = load_products_from_firestore(db)
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

def build_llm_prompt_context_instruction(session_data):
    instruction = "INSTRUÇÃO PARA ESTA RESPOSTA ESPECÍFICA: "
    state = session_data["chat_state"]

    if state == 'INITIAL' or state == 'PRODUCT_QUERY':
        instruction += "Saudação inicial ou busca de produtos. Pergunte o que o cliente procura. Se já há itens no carrinho, pode mencioná-los brevemente (ex: 'Seu carrinho atual: [itens]')."
    else:
        instruction += "Responda ao usuário, considerando o estado atual da conversa."
    
    session_data["last_input_invalid"] = False
    return instruction

def call_gemini_api(prompt_history):
    if not GEMINI_API_KEY:
        logging.error("API Key Gemini não configurada.")
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
        logging.error(f"Resposta API Gemini inesperada: {result}")
        return "Desculpe, não consegui processar (resposta IA inesperada)."
    except Exception as e:
        logging.error(f"Erro API Gemini: {e}")
        return "Ops! Problema com nossa IA. Tente novamente."

def call_openrouter_api(system_prompt, chat_history, session_data):
    if not OPENROUTER_API_KEY:
        logging.error("API Key do OpenRouter não configurada.")
        return "ERRO INTERNO: A configuração da IA está ausente."

    ab_group = session_data.get("ab_test_group")
    if AB_TEST_ENABLED and ab_group == 'B':
        model_to_use = OPENROUTER_MODEL_B
        logging.info(f"Sessão no grupo B. Usando modelo: {model_to_use}")
    else:
        model_to_use = OPENROUTER_MODEL_A
        logging.info(f"Sessão no grupo A. Usando modelo: {model_to_use}")

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
            logging.error(f"Resposta da API OpenRouter inesperada: {result}")
            return "Desculpe, não consegui processar a sua solicitação (resposta da IA foi inesperada)."
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro de comunicação com a API OpenRouter: {e}")
        if e.response is not None:
            logging.error(f"Detalhes do erro da API: {e.response.text}")
        return "Ops! Tive um problema de comunicação com nossa IA. Poderia tentar novamente?"
    except Exception as e:
        logging.error(f"Erro inesperado ao chamar a API OpenRouter: {e}")
        return "Desculpe, ocorreu um erro interno ao tentar processar sua solicitação."
