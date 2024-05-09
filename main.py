from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv

load_dotenv()  # Carrega variáveis de ambiente do arquivo .env

app = Flask(__name__)

@app.route("/chat", methods=["POST"])
def chat():
        
    data = request.get_json()
    historico = data.get("Historico")
    mensagem = data.get("Mensagem")
    api_key = os.environ.get("API_KEY")       

    # Retorna uma resposta em formato JSON
    resposta = {
        "mensagem": "Mensagem recebida com sucesso!",
        "historico_atualizado": historico + "\n" + mensagem,
        "chave ": api_key,
    }

    return jsonify({"resposta": resposta})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))