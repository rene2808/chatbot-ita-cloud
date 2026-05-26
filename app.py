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
                # Lógica: Si es "general", su clave principal es solo el nombre de la categoría
                if subcategoria == "general":
                    claves = [limpiar_texto(categoria), limpiar_texto(subcategoria)]
                else:
                    claves = [limpiar_texto(f"{categoria} {subcategoria}"), limpiar_texto(subcategoria)]

                base_conocimiento.append({
                    "categoria": categoria,
                    "subcategoria": subcategoria,
                    "claves_busqueda": claves,
                    "respuesta": respuesta
                })
        print(f"Base cargada. Registros: {len(base_conocimiento)}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

cargar_conocimiento()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_response', methods=['POST'])
def get_response():
    if not base_conocimiento: cargar_conocimiento()

    mensaje_original = request.json.get("message", "")
    user_msg = limpiar_texto(mensaje_original)
    
    cortesias = {
        "hola": "¡Hola! Soy tu asistente virtual del ITA. ¿Sobre qué trámite escolar tienes duda?",
        "gracias": "¡De nada! Éxito en tus trámites.",
        "adios": "¡Hasta luego! Vuelve pronto.",
        "ayuda": "Pregúntame sobre: Inscripción, Servicio Social, Residencias o Becas."
    }
    
    if user_msg in cortesias:
        return jsonify({"response": cortesias[user_msg]})
    
    # Buscar el mejor resultado
    resultados = []
    for item in base_conocimiento:
        mejor_score = 0
        for clave in item["claves_busqueda"]:
            score = fuzz.token_set_ratio(user_msg, clave)
            # Bonus de precisión para palabras exactas
            if user_msg == clave: score += 10 
            if score > mejor_score: mejor_score = score
        
        resultados.append({"item": item, "score": mejor_score})
    
    resultados.sort(key=lambda x: x["score"], reverse=True)
    
    if not resultados or resultados[0]["score"] < 55:
        respuesta = "No estoy seguro de entender. ¿Te refieres a inscripciones, residencias o servicio social?"
    else:
        # Si hay un empate cercano y uno es 'general', preferimos el general
        if len(resultados) > 1 and resultados[1]["item"]["subcategoria"] == "general":
            if resultados[0]["score"] - resultados[1]["score"] < 5:
                respuesta = resultados[1]["item"]["respuesta"]
            else:
                respuesta = resultados[0]["item"]["respuesta"]
        else:
            respuesta = resultados[0]["item"]["respuesta"]

    return jsonify({"response": respuesta})

if __name__ == '__main__':
    app.run()
