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
                # Generamos las claves de búsqueda
                claves = [limpiar_texto(subcategoria)]
                if subcategoria == "general":
                    claves.append(limpiar_texto(categoria))
                else:
                    # Incluimos la categoría en la clave para mayor precisión
                    claves.append(limpiar_texto(f"{categoria} {subcategoria}"))

                base_conocimiento.append({
                    "categoria": categoria,
                    "subcategoria": subcategoria,
                    "es_general": (subcategoria == "general"),
                    "claves_busqueda": claves,
                    "respuesta": respuesta
                })
        print("Pipeline de conocimiento cargado correctamente con respuestas maestras.")
    except Exception as e:
        print(f"Error al cargar conocimiento.json: {e}", file=sys.stderr)

cargar_conocimiento()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_response', methods=['POST'])
def get_response():
    if not base_conocimiento: cargar_conocimiento()
    
    mensaje_usuario_original = request.json.get("message", "")
    user_msg = limpiar_texto(mensaje_usuario_original)
    
    # Manejo de cortesías básicas
    cortesias = {
        "hola": "¡Hola! Soy tu asistente virtual del ITA. ¿En qué trámite puedo ayudarte hoy?",
        "gracias": "¡De nada! Espero haberte ayudado. Mucho éxito en tu semestre.",
        "adios": "¡Hasta luego! Recuerda consultar el SIIAU para tus trámites."
    }
    
    if user_msg in cortesias:
        return jsonify({"response": cortesias[user_msg]})

    # Proceso de búsqueda en el pipeline
    resultados = []
    for item in base_conocimiento:
        mejor_score_item = 0
        for clave in item["claves_busqueda"]:
            # Usamos token_set_ratio para manejar frases fuera de orden
            score = fuzz.token_set_ratio(user_msg, clave)
            
            # Bonificación de prioridad: si la pregunta coincide exactamente con la categoría principal
            if user_msg == clave and item["es_general"]:
                score += 15
                
            if score > mejor_score_item:
                mejor_score_item = score
        
        resultados.append({"item": item, "score": mejor_score_item})

    # Ordenamos por los mejores resultados
    resultados.sort(key=lambda x: x["score"], reverse=True)

    # Lógica de respuesta basada en umbral
    if not resultados or resultados[0]["score"] < 50:
        respuesta = "Lo siento, no tengo información exacta sobre eso. Intenta preguntando por temas generales como 'Servicio Social', 'Inscripciones' o 'Residencias'."
    else:
        # Selección del mejor resultado (con desempate para respuestas maestras)
        mejor_opcion = resultados[0]
        
        if len(resultados) > 1 and resultados[1]["item"]["es_general"]:
            # Si el puntaje es casi el mismo, preferimos la respuesta general
            if (resultados[0]["score"] - resultados[1]["score"]) < 10:
                mejor_opcion = resultados[1]
                
        respuesta = mejor_opcion["item"]["respuesta"]

    return jsonify({"response": respuesta})

if __name__ == '__main__':
    # El puerto lo maneja Azure automáticamente, pero dejamos el inicio estándar
    app.run()
