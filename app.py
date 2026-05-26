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
        print("Pipeline de precisión cargado.")
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
    
    # Cortesías rápidas
    cortesias = {"hola": "¡Hola! Soy tu asistente del ITA.", "gracias": "¡De nada!", "adios": "¡Hasta pronto!"}
    if user_msg in cortesias: return jsonify({"response": cortesias[user_msg]})

    # Buscamos coincidencias
    candidatos = []
    for item in base_conocimiento:
        mejor_score = 0
        for clave in item["claves_busqueda"]:
            # Usamos ratio normal para mayor precisión en palabras clave
            score = fuzz.token_set_ratio(user_msg, clave)
            if score > mejor_score: mejor_score = score
        candidatos.append({"item": item, "score": mejor_score})

    # Ordenar por puntaje
    candidatos.sort(key=lambda x: x["score"], reverse=True)

    if not candidatos or candidatos[0]["score"] < 55:
        return jsonify({"response": "No encontré información exacta. ¿Podrías ser más específico?"})

    # LÓGICA DE DECISIÓN CRÍTICA
    # Si la mejor opción es 'general', pero la segunda opción tiene un score alto (>70) 
    # y NO es general, significa que el usuario preguntó algo específico.
    
    seleccionado = candidatos[0]
    
    if seleccionado["item"]["es_general"]:
        # Revisamos si entre los primeros 5 hay algo específico que coincida bien
        for i in range(1, min(5, len(candidatos))):
            if candidatos[i]["score"] > 70 and not candidatos[i]["item"]["es_general"]:
                seleccionado = candidatos[i]
                break

    return jsonify({"response": seleccionado["item"]["respuesta"]})

if __name__ == '__main__':
    app.run()
