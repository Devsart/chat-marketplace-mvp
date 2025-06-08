import os
from dotenv import load_dotenv

load_dotenv()
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
