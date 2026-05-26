from flask import Flask, render_template, request, jsonify
import json
import re
import sys
import unicodedata
from thefuzz import fuzz

app = Flask(__name__)

def limpiar_texto(texto):
    if not texto: return ""
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8').lower()
    texto = re.sub(r'[^\w\s]', '', texto)
    return texto

base_conocimiento = []

def cargar_conocimiento():
    global base_conocimiento
    try:
        with open('conocimiento.json', 'r', encoding='utf-8') as f:
            datos_json = json.load(f)
        
        base_conocimiento = []
        for categoria, subcategorias in datos_json.items():
            for subcategoria, respuesta in subcategorias.items():
                claves = [limpiar_texto(subcategoria)]
                if subcategoria == "general":
                    claves.append(limpiar_texto(categoria))
                else:
                    claves.append(limpiar_texto(f"{categoria} {subcategoria}"))

                base_conocimiento.append({
                    "categoria": categoria,
                    "subcategoria": subcategoria,
                    "es_general": (subcategoria == "general"),
                    "claves_busqueda": claves,
                    "respuesta": respuesta
                })
        print("Pipeline actualizado: Precisión mejorada.")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

cargar_conocimiento()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_response', methods=['POST'])
def get_response():
    if not base_conocimiento: cargar_conocimiento()
    
    msg_raw = request.json.get("message", "")
    user_msg = limpiar_texto(msg_raw)
    palabras_usuario = msg_raw.split()
    
    # Cortesías
    cortesias = {"hola": "¡Hola! Soy tu asistente del ITA.", "gracias": "¡De nada!", "adios": "¡Suerte!"}
    if user_msg in cortesias: return jsonify({"response": cortesias[user_msg]})

    resultados = []
    for item in base_conocimiento:
        max_score = 0
        for clave in item["claves_busqueda"]:
            score = fuzz.token_set_ratio(user_msg, clave)
            
            # CRÍTICO: Solo dar bonus si la pregunta es CORTA (Intención de rama)
            if len(palabras_usuario) <= 2 and user_msg == clave and item["es_general"]:
                score += 20
            
            if score > max_score: max_score = score
        resultados.append({"item": item, "score": max_score})

    resultados.sort(key=lambda x: x["score"], reverse=True)

    if not resultados or resultados[0]["score"] < 50:
        respuesta = "No entiendo. Prueba con algo como 'Requisitos de inscripción' o 'Servicio Social'."
    else:
        # Si la pregunta es LARGA, ignoramos el desempate hacia lo general
        if len(palabras_usuario) > 2:
            mejor_opcion = resultados[0]
        else:
            # Si es corta, el desempate ayuda a la respuesta Maestra
            mejor_opcion = resultados[0]
            if len(resultados) > 1 and resultados[1]["item"]["es_general"]:
                if (resultados[0]["score"] - resultados[1]["score"]) < 15:
                    mejor_opcion = resultados[1]
        
        respuesta = mejor_opcion["item"]["respuesta"]

    return jsonify({"response": respuesta})

if __name__ == '__main__':
    app.run()
