# Chatbot de Atendimento ao Cliente para Vendas de Marketplace de Eletrónicos

## 1. Utilidade do Projeto

Este projeto implementa um **chatbot inteligente** utilizando um modelo de linguagem (LLM), especificamente a API Gemini do Google, para simular um ambiente de vendas de um marketplace fictício de eletrónicos. O objetivo principal do chatbot, chamado **IAne**, é:

- **Interagir com clientes:** Entender as suas necessidades e preferências de produtos eletrónicos.
- **Apresentar produtos:** Fornecer informações sobre os produtos disponíveis no catálogo, que é carregado dinamicamente de um banco de dados Firestore.
- **Gerir um carrinho de compras:** Permitir que os clientes adicionem e (implicitamente) removam itens.
- **Recolher dados do cliente:** Caso o cliente decida finalizar a compra, recolher nome completo, e-mail e telefone.
- **Gerar uma proposta comercial:** No final, apresentar um resumo da compra com os itens do carrinho, valor total e um link (fictício) para checkout.

O chatbot é projetado para ter um fluxo de conversa natural, guiando o cliente desde a saudação inicial até à finalização da compra, com validações de entrada para garantir a qualidade dos dados recolhidos.

---

## 2. Executando o Projeto

Você pode executar este projeto de duas maneiras:
- **Localmente** (requer Python e as dependências instaladas)
- **Via Docker** (mais simples e isolado)

### 2.1. Pré-requisitos Comuns
Antes de executar, você irá precisar de:

- **Credenciais do Firebase** (`firebase-credentials.json`): Para que o backend Python possa comunicar com o Firestore (onde os produtos são armazenados).
- **Chave da API Gemini (Google AI Studio):** Para que o chatbot possa usar o modelo de linguagem Gemini.
- **Configuração do arquivo `.env`.**

#### 2.1.1. Gerando as Credenciais do Firebase (`firebase-credentials.json`)

1. Acesse a [Firebase Console](https://console.firebase.google.com/) e faça login.
2. Selecione o seu Projeto: Clique no projeto Firebase que está a usar. Se não tiver um, crie um novo.
3. No menu à esquerda, clique no ícone de engrenagem ⚙️ ao lado de "Visão geral do projeto" e selecione **Definições do projeto**.
4. Na página de definições, vá para o separador **Contas de serviço**.
5. Clique no botão **Gerar nova chave privada**. Confirme a geração na janela pop-up.
6. O seu navegador fará o download de um arquivo JSON. Renomeie-o para `firebase-credentials.json` (ou outro nome, mas ajuste as referências nos comandos Docker) e guarde-o na pasta raiz do seu projeto.
7. **Ative a API Firestore e crie o banco de dados:**
   - Na Google Cloud Console (o link geralmente está na mensagem de erro se a API não estiver ativada, ou procure por "Firestore" na consola), certifique-se de que a Cloud Firestore API está ATIVADA para o seu projeto.
   - Na Firebase Console, vá em **Firestore Database** (em "Build") e clique em **Criar banco de dados**. Siga as instruções, escolhendo o modo de segurança (para desenvolvimento, "modo de teste" é mais fácil, mas lembre-se de proteger em produção) e uma localização para o servidor.

#### 2.1.2. Configurando o Arquivo `.env`

Na raiz do seu projeto, crie um arquivo chamado `.env` com o seguinte conteúdo:

```env
GOOGLE_API_KEY="SUA_API_KEY_GEMINI_AQUI"
GOOGLE_APPLICATION_CREDENTIALS="caminho/para/seu/firebase-credentials.json" # Usado mais para execução local direta
```

Substitua `SUA_API_KEY_GEMINI_AQUI` pela chave de API obtida do Google AI Studio.

---

### 2.2. Execução Local (Python Direto)

1. Clone o repositório ou tenha os arquivos:
   - `app.py` (backend Flask)
   - `templates/index.html` (frontend)
   - `requirements.txt`
   - `firebase-credentials.json`
   - `.env`
2. Crie e ative um ambiente virtual:

   ```sh
   python -m venv venv
   # No Windows:
   venv\Scripts\activate
   # No macOS/Linux:
   source venv/bin/activate
   ```

3. Instale as dependências:
   ```sh
   pip install -r requirements.txt
   ```

4. Execute a aplicação Flask:
   ```sh
   python app.py
   ```

5. Acesse o chatbot em [http://127.0.0.1:5001](http://127.0.0.1:5001).

---

### 2.3. Execução via Docker

1. Tenha os arquivos necessários na raiz do projeto:
   - `Dockerfile`
   - `requirements.txt`
   - `app.py`
   - `templates/index.html`
   - `firebase-credentials.json`
   - `.env`

2. Construa a imagem Docker:
   ```sh
   docker build -t chatbot-marketplace .
   ```

3. Execute o container Docker:
   ```sh
   docker run -d \
     -p 5001:5001 \
     --env-file ./.env \
     --name chatbot-app \
     chatbot-marketplace
   ```

4. Acesse o chatbot em [http://127.0.0.1:5001](http://127.0.0.1:5001).

---

## 3. Respostas às Dúvidas da "Parte Falada" (do PDF)

### Como você começaria a resolver esse problema?

- Entendimento profundo dos requisitos de negócio e fluxos de conversa.
- Escolha da tecnologia principal (LLM).
- Design da arquitetura inicial (MVP):
  - **Frontend:** Uma interface web simples (HTML, JS, CSS) para interação.
  - **Backend:** Um servidor (Flask em Python) para:
    - Gerir o estado da conversa.
    - Interagir com a API do LLM.
    - Conectar-se a uma base de dados para produtos (Firestore).
  - **Base de Dados:** Firestore para armazenar dinamicamente o catálogo de produtos.
- Desenvolvimento iterativo e considerações de segurança.

### Como você limitaria os produtos devolvidos?

- Compreensão da intenção via LLM.
- Filtragem por características/categorias no backend.
- Ranking e relevância.
- Personalização e interação progressiva.

### Como você testaria o modelo?

- **Testes unitários:** Funções de validação, lógica de estado, simulação da API do LLM, conexão com Firestore.
- **Testes de integração:** Fluxo completo frontend-backend-LLM.
- **Golden datasets:** Pares de entrada/saída esperados.
- **Avaliação humana:** Naturalidade, coerência, tom de voz.
- **Testes A/B e métricas de desempenho.**
- **Testes de robustez e segurança.**

### Quais os riscos que você vê na aplicação de um modelo desses em um ambiente real?

- **Alucinações do LLM:** O modelo pode gerar informações factualmente incorretas sobre produtos, políticas da empresa, ou inventar funcionalidades.
  - *Mitigação:* RAG (como fizemos com Firestore para produtos), prompts bem definidos, "grounding" do modelo em dados confiáveis.
- **Fuga de dados/privacidade:** Se não tratado corretamente, dados sensíveis do cliente podem ser expostos.
  - *Mitigação:* Usar APIs de LLM com políticas de não treino em dados de API, mascaramento de PII antes de enviar ao LLM, arquiteturas seguras.
- **Comportamento inesperado/Não Alinhado:** O LLM pode gerar respostas ofensivas, enviesadas, ou que não sigam o tom de voz da marca.
  - *Mitigação:* Prompts de sistema fortes (meta-prompting), moderação de conteúdo (pode ser um LLM separado ou filtros), "guardrails", e monitorização contínua.
- **Dependência do Fornecedor de LLM:** Se a API estiver fora do ar ou houver mudanças significativas na API/modelo, a sua aplicação pode ser afetada.
  - *Mitigação:* Ter planos de contingência, usar abstrações para facilitar a troca de fornecedores se necessário (como LangChain faria).
- **Custo:** Chamadas de API para LLMs podem tornar-se caras em alto volume.
  - *Mitigação:* Otimizar prompts, usar modelos menores/mais baratos para tarefas mais simples, cache de respostas comuns (com cuidado para não ficar desatualizado).
- **Experiência do Utilizador Frustrante:** Se o bot não entender bem, entrar em loops, ou demorar para responder.
  - *Mitigação:* Design de conversação cuidadoso, testes extensivos, mecanismos de fallback para atendimento humano.
- **Escalabilidade:** Garantir que o backend e a API do LLM possam lidar com o volume de utilizadores.

### Como você lidaria com atualizações?

- **Catálogo de produtos:** Atualização dinâmica via Firestore. Qualquer atualização no Firestore é refletida no chatbot sem necessidade de re-deploy do código do chatbot (a menos que a estrutura dos dados do produto mude drasticamente).
- **Prompts do sistema:** Os prompts estão no código (app.py). Mudanças neles exigiriam um novo deploy do backend.
  - *Melhoria:* Os prompts poderiam ser armazenados numa base de dados ou sistema de configuração, permitindo atualizações sem deploy.
- **Modelo de LLM:** Geralmente, isso envolve atualizar a chamada da API para o novo endpoint/modelo.
  - Requer testes de regressão extensivos, pois um novo modelo pode comportar-se de maneira diferente.
- **Lógica do chatbot:** Exige modificações no código (app.py) e um novo deploy.
- **Versionamento de código (Git) e um pipeline de CI/CD são essenciais.**
- **Monitorização e Feedback Contínuo:** Analisar logs de conversas (anonimizados) para identificar onde o bot falha ou causa frustração. Recolher feedback dos utilizadores. Usar esse feedback para iterar nos prompts, na lógica e no fluxo.

### Como você limitaria o valor total da compra / transferiria o atendimento para um humano para valores superiores ao CAP?

O PDF menciona um CAP de 5k.

- **Cálculo do Valor do Carrinho:** Conforme o cliente adiciona itens ao carrinho, o backend calcula o valor total (como já fazemos com `calculate_total_cart_value`).
- **Verificação do CAP:** Antes de pedir dados pessoais (`AWAITING_NAME`): Quando o cliente indica que quer "finalizar a compra", o backend verifica se o valor total do carrinho excede o CAP (R$ 5.000,00).
  - Durante a adição ao carrinho: Opcionalmente, poderia haver um aviso se um único item ou a adição de um item fizesse o carrinho ultrapassar o CAP.
- **Transferência para Atendimento Humano:** Se o CAP for excedido:
  - O chatbot não prosseguiria para a recolha de dados.
  - Ele informaria ao cliente de forma amigável: "Percebi que o valor da sua compra é um pouco mais alto. Para garantir a melhor assistência e condições especiais para si, gostaria de transferi-lo para um dos nossos consultores especializados. Tudo bem?"
- **Mecanismo de Transferência:**
  - **Ideal:** Integração com um sistema de live chat ou CRM. O chatbot poderia criar um ticket ou iniciar uma sessão de chat com um humano, passando o contexto da conversa (cliente, itens no carrinho).
  - **Simples:** Fornecer um número de telefone, e-mail de contato, ou um link para um formulário de contato para atendimento especializado.
  - *Manter o contexto:* Ao transferir, é crucial que o agente humano receba o máximo de contexto possível sobre a interação do cliente com o chatbot para evitar que o cliente tenha que repetir tudo.

### Você usaria alguma arquitetura específica para resolver esse problema? (ex. RAG)

Sim, a arquitetura que implementamos JÁ É uma forma de RAG (Retrieval-Augmented Generation).

- **Arquitetura Atual (RAG Simples):**
  - **Retrieval:** Buscamos a lista completa de produtos do Firestore.
  - **Augmentation:** Injetamos essa lista de produtos no prompt do sistema do LLM, "aumentando" o seu conhecimento com dados em tempo real sobre o catálogo.
  - **Generation:** O LLM usa esse prompt aumentado para gerar respostas e interagir.

- **Prós da nossa abordagem RAG atual:**
  - Dados Atualizados: O chatbot usa sempre a informação mais recente dos produtos sem retreinar o LLM.
  - Redução de Alucinações (sobre produtos): O LLM está "ancorado" nos dados fornecidos.
  - Simplicidade para este caso de uso: Para um catálogo de produtos de tamanho gerenciável, carregar a lista e incluí-la no prompt é eficaz.

- **Problemas/Limitações da nossa abordagem RAG atual e quando um RAG mais avançado seria necessário:**
  - Tamanho do Contexto do LLM: Se o catálogo de produtos se tornasse extremamente grande (milhares de produtos com descrições longas), a lista completa poderia exceder o limite de tokens do contexto do prompt do LLM.
  - Recuperação Genérica: Atualmente, recuperamos todos os produtos. Não fazemos uma busca inteligente dentro do catálogo baseada na semântica da pergunta do utilizador antes de passar ao LLM.

- **Quando um RAG mais avançado (com Banco de Dados Vetorial) seria útil:**
  - Catálogos Enormes: Se o catálogo for muito grande para caber no prompt.
  - Busca Semântica por Produtos: Se quiséssemos que o chatbot encontrasse produtos com base em descrições vagas ou consultas em linguagem natural que não mencionam nomes exatos. Ex: "Quero um portátil leve, com boa bateria e que execute programas de design gráfico".
  - Recomendação de Produtos Similares: "Gostei do NovoPhone X12, mas é um pouco caro. Tem algo parecido mais em conta?"

- **Prós:**
  - Melhora drasticamente a relevância da recuperação para consultas complexas ou vagas.
  - Escala bem para grandes volumes de dados textuais.

- **Contras:**
  - Adiciona complexidade à arquitetura (processo de embedding, gestão do DB vetorial).
  - Pode ter custos adicionais.
  - A qualidade da busca depende da qualidade do modelo de embedding escolhido.

**Conclusão para Melhorias:** Para o MVP atual, o RAG simples com Firestore é uma boa solução. Se o projeto evoluir para ter um catálogo muito maior, ou a necessidade de entender consultas de produto muito mais abertas e semânticas, então a combinação de LangChain com um banco de dados vetorial seria uma evolução natural.

**Diagrama de Arquitetura MVP**

 - A inserir

 **Diagrama de Arquitetura Escalável**

 - A inserir.