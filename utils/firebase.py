import logging
from utils.constants import DEFAULT_PRODUCTS_SEED, AB_TEST_ENABLED, OPENROUTER_MODEL_A, OPENROUTER_MODEL_B
from datetime import datetime, timezone

def seed_initial_products(db):
    if not db:
        logging.error("Firestore não inicializado. Seed não executado.")
        return
    try:
        products_ref = db.collection('products')
        docs = products_ref.limit(1).stream()
        if not list(docs): 
            logging.info("Populando 'products' com dados padrão...")
            for product_data in DEFAULT_PRODUCTS_SEED:
                products_ref.document(product_data['id']).set(product_data)
            logging.info(f"{len(DEFAULT_PRODUCTS_SEED)} produtos adicionados.")
        else:
            logging.info("'products' já contém dados.")
    except Exception as e:
        logging.error(f"Erro no seed de produtos: {e}")

def load_products_from_firestore(db):
    if not db:
        logging.error("Firestore não inicializado. Não é possível carregar produtos.")
        return []
    try:
        products_ref = db.collection('products')
        docs = products_ref.stream()
        products_list = [doc.to_dict() for doc in docs if all(k in doc.to_dict() for k in ['id', 'name', 'price', 'category'])]
        if not products_list: logging.warning("Nenhum produto carregado do Firestore.")
        return products_list
    except Exception as e:
        logging.error(f"Erro ao carregar produtos do Firestore: {e}")
        return []

def save_session_to_firestore(db,session_data):
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
        logging.info(f"Sessão {session_uuid} salva no Firestore.")

    except Exception as e:
        logging.error(f"Erro ao salvar sessão {session_data.get('session_uuid')} no Firestore: {e}")
