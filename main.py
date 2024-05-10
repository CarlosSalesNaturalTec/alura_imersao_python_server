# Carrega bibliotecas 
from flask import Flask, request, jsonify
from pathlib import Path
import os
import requests
import hashlib
import time
import google.generativeai as genai
from google.cloud import storage 
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv
load_dotenv()  

# Variáveis de ambiente
my_api_key = os.environ.get("API_KEY")                        # Gemini - API_KEY
system_instruction =  os.environ.get("SYSTEM_INSTRUCTIONS")   # Gemini - Instruções do Sistema / Prompt contendo a "Persona" do Assistente.
url_base = os.environ.get("URL_BASE")                         # WhatsApp Cloud API - URL base da API (incluindo versão)
token = os.environ.get("TOKEN")                               # WhatsApp Cloud API - Token de segurança para acesso às mensagens 
bucket_name = os.environ.get("BUCKET_NAME")                   # Google Cloud Storage - Nome do Bucket para armazenamento de midias

# Parâmetros do modelo
generation_config = {
  "temperature": 1,
  "top_p": 0.95,
  "top_k": 0,
  "max_output_tokens": 8192,
}
safety_settings = [
  {
    "category": "HARM_CATEGORY_HARASSMENT",
    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
  },
  {
    "category": "HARM_CATEGORY_HATE_SPEECH",
    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
  },
  {
    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
  },
  {
    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
  },
]

# Inicia modelo
genai.configure(api_key=my_api_key)
model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest",
                              generation_config=generation_config,
                              system_instruction=system_instruction,
                              safety_settings=safety_settings)

# Inicializa o Firebase app (Gestão de Banco No-SQL ref. histórico de mensagens)
cred = credentials.Certificate("/credentials/firebase_credentials.json")    # Path: /credentials/... => volume criado dentro do container / Google Cloud Run
firebase_admin.initialize_app(cred)
db = firestore.client()

app = Flask(__name__)

# Endpoint POST para recebimento de notificações da WhatsApp Cloud API
@app.route("/webhook", methods=["POST"])
def webhook():   
    data = request.json

    # Tratamento de mensagens recebidas
    if data.get("entry") and data["entry"][0].get("changes"):
        change = data["entry"][0]["changes"][0]
        if change.get("value") and change["value"].get("messages"):
            message = change["value"]["messages"][0]
            tel = message.get("from")
            type_message = message.get("type")
            message_history = get_menssages(tel)                    # Obtem histórico de mensagens

            # Tratamento de Mensagens de TEXTO
            if type_message == "text":
                body_message = message.get("text").get("body")      # Texto da mensagem digitada pelo usuário      
                role = "user"                                       # role=user => mensagem enviada pelo usuário
                store_message(tel, role, body_message)              # Salva mensagem em banco NO-SQL. 

                convo = model.start_chat(history = message_history) # Inicia chat, contextualizando a IA com o histórico da conversação
                convo.send_message(body_message)                    # envia nova mensagem para ser processada pela IA
                response = convo.last.text                          # Obtem resposta da IA

                send_message = send_text_message(tel, response)     # Envia resposta de volta para o usuário através da WhatsApp Cloud API                
                if send_message:
                    role = "model"                                  # role=model => mensagem enviada pela IA
                    store_message(tel, role, response)              # Salva mensagem em banco NO-SQL. 
            
            # Tratamento de Mensagens de AUDIO
            elif type_message == "audio":                
                id_media = message.get("audio").get("id")                   
                url_media = get_url_media(id_media)                 # obtem URL do audio (Midia protegida por token - WhastApp Cloud API)
                if url_media:               
                    media = download_media(url_media)               # faz o download do audio em formato binário 
                    if media:
                        url_public = store_media(media, tel)             # Salva audio em bucket do Google Cloud Storage e obtem sua URL
                        if url_public:
                            send_text_message(tel, f"Url Audio: {url_public}")  # envia resposta de volta para o usuário através da WhatsApp Cloud API       
                        else:
                            send_text_message(tel, "Não foi possível salvar o Audio na Nuvem. Tente Novamente") 
                    else:
                        send_text_message(tel, "Não foi possível obter o Audio. Tente Novamente") 
                else:
                    send_text_message(tel, "Não foi possível obter a URL do Audio. Tente Novamente") 

            # Outros tipos de mensagens (imagens, figurinhas, localização, contato, etc)                                             
            else:               
                resposta = f"Desculpe ainda não fui programado para analisar mensagens do tipo: *{type_message}*. Envie somente Texto ou Áudio"
                send_text_message(tel, resposta)    # envia resposta de volta para o usuário através da WhatsApp Cloud API       
    
    return jsonify({"status": "Ok"}), 200

# Endpoint GET para validação do webhook junto a WhatsApp Cloud API
@app.route("/webhook", methods=["GET"])
def verify_webhook():
    verify_token = os.environ.get("VERIFY_TOKEN")
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode and token:
        if mode == "subscribe" and token == verify_token:
            return challenge, 200
        else:
            return "Verification failed", 403
    else:
        return "Invalid request", 400


# Envia mensagem de texto para a WhatsApp Cloud API
def send_text_message(tel, text_response):
    
    url_base = os.environ.get("URL_BASE") 
    id_tel = os.environ.get("ID_TEL") 
    token = os.environ.get("TOKEN") 

    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": tel,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text_response
        }
    }

    url = f"{url_base}/{id_tel}/messages"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        json_response = response.json()
        if json_response.get("messages") and json_response["messages"][0].get("id"):            
            return True  # Indica sucesso
    else:
        return False  # Indica falha        


# Obtem URL do audio enviado pela WhatsApp Cloud API
def get_url_media(id_media):    
    url = f"{url_base}/{id_media}"
    headers = {
        "Authorization": f"Bearer {token}"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json().get("url")
    else:
        return False


# Realiza o Download de midia (audio/video) 
def download_media(url_media):    
    headers = {
        "Authorization": f"Bearer {token}"
    }

    try:
        response = requests.get(url_media, headers=headers, stream=True)
        response.raise_for_status()  
        return response.content
    except requests.exceptions.RequestException as e:
        print(f"Erro ao baixar o arquivo de áudio: {e}") 
        return False
    except Exception as e:
        print(f"Erro ao salvar no Cloud Storage: {e}") 
        return False
    
    
# Salva mídia em Bucket do Google Cloud Storage e retorna sua URL
def store_media(media, tel):
    storage_client = storage.Client()           
    bucket = storage_client.bucket(bucket_name) # Bucket em que será salvo a midia
    file_name = f"{tel}_{time.time()}.ogg"          # Nome do arquivo a ser salvo (concatena número do telefone + timestamp)
    blob = bucket.blob(file_name)               

    try:
        blob.upload_from_string(media, content_type="audio/ogg")    # Realiza o Upload do arquivo para o Cloud Storage         
        file_url = blob.public_url                                  # Obtem sua URL
        return file_url
    except Exception as e:
        print(f"Erro ao tentar salvar mídia no Bucket da Google Cloud Storage. Detalhes: {e}")
        return False


# Salva mensagem em banco No-SQL para recuperação de histórico de conversa
def store_message(tel, role, message):
    try:
        doc_ref = db.collection(f"messages_{tel}").document()
        doc_ref.set({
            "timestamp": time.time(),
            "role": role,
            "parts": [message]
        })    
    except Exception as e:
        print(f"Erro ao salvar mensagem no Firebase/FireStore. Detalhes: {e}")
        return False
    

# Obtem histórico de mensagens do telefone, a partir de Banco No-SQL hospedado na Google Cloud FireStore/Firebase
def get_menssages(tel):
    mensagens_ref = db.collection(f"messages_{tel}").order_by("timestamp")
    mensagens = mensagens_ref.stream()

    # Lista para armazenar as mensagens formatadas
    messages_array = []

    for mensagem in mensagens:
        message_dict = mensagem.to_dict()
        # Cria o formato desejado para cada mensagem
        formatted_message = {
            "role": message_dict["role"],
            "parts": message_dict["parts"]
        }
        messages_array.append(formatted_message)

    return messages_array


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))