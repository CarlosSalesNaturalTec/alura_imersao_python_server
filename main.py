# Carrega bibliotecas 
from flask import Flask, request, jsonify
from pathlib import Path
import os
import requests
import hashlib
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()  

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
my_api_key = os.environ.get("API_KEY") 
system_instruction =  os.environ.get("SYSTEM_INSTRUCTIONS")

# Inicia modelo
genai.configure(api_key=my_api_key)
model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest",
                              generation_config=generation_config,
                              system_instruction=system_instruction,
                              safety_settings=safety_settings)

app = Flask(__name__)

# Endpoint POST para receber dados do webhook
@app.route("/webhook", methods=["POST"])
def webhook():   
    # obtem mensagem da WhatsApp Cloud API
    data = request.json
    if data.get("entry") and data["entry"][0].get("changes"):
        change = data["entry"][0]["changes"][0]
        if change.get("value") and change["value"].get("messages"):
            message = change["value"]["messages"][0]
            id_message = message.get("id")
            tel = message.get("from")
            timestamp = message.get("timestamp")
            type_message = message.get("type")

            if type_message == "text":
                body_message = message.get("text").get("body")
            elif type_message == "button":
                body_message = message.get("button").get("text")
            else:
                body_message = f"Mensagem do Tipo: {type_message}"
                resposta = f"Mensagem recebida de {tel}: {body_message}"

    # envia mensagem para ser processada pela IA
    convo = model.start_chat(history= [])
    convo.send_message(body_message)
    resposta = convo.last.text

    # envia resposta de volta para o usuário através da WhatsApp Cloud API
    response = envia_msg_texto(tel, resposta)
    if response == True:
      return jsonify({"status": "Ok"}), 200
    else:
      return jsonify({"status": "Erro ao enviar resposta pelo WhatsApp"}), 400

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

def envia_msg_texto(tel, text_response):
    
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
            print("Erro: retorno esperado não recebido.")
    else:
        print(f"Erro ao enviar mensagem. Status code: {response.status_code}")

    return False  # Indica falha        

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))