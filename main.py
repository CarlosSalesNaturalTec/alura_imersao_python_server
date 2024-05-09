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

# inicia modelo
genai.configure(api_key=my_api_key)
model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest",
                              generation_config=generation_config,
                              system_instruction=system_instruction,
                              safety_settings=safety_settings)

app = Flask(__name__)

# Endpoint POST para receber dados do webhook
@app.route("/webhook", methods=["POST"])
def webhook():

    # obtem dados da requisição
    data = request.get_json()
    historico = data.get("historico")
    mensagem = data.get("mensagem")

    convo = model.start_chat(history= [])
    convo.send_message(mensagem)
    resposta = convo.last.text

    return jsonify({"response": resposta}), 200    

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

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))