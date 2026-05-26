from flask import Flask, render_template, request, jsonify
import json
import re
import sys
import unicodedata
from thefuzz import fuzz

app = Flask(__name__)

def limpiar_texto(texto):
    if not texto:
        return ""
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8').lower()
    texto = re.sub(r'[^\w\s]', '', texto)
    
    equivalencias = {
        "tec": "tecnologico",
        "it": "instituto",
        "creditos": "actividades complementarias",
        "pago": "costo dinero referencia",
        "papeles": "documentos requisitos"
    }
    for corto, largo in equivalencias.items():
        if re.search(rf'\b{corto}\b', texto):
            texto += f" {largo}"
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
        print("Pipeline de precisión institucional cargado con éxito.")
    except Exception as e:
        print(f"Error al cargar conocimiento.json: {e}", file=sys.stderr)
        base_conocimiento = []

cargar_conocimiento()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_response', methods=['POST'])
def get_response():
    if not base_conocimiento:
        cargar_conocimiento()
    
    mensaje_original = request.json.get("message", "")
    user_msg = limpiar_texto(mensaje_original)
    palabras = mensaje_original.strip().split() # Contamos palabras originales

    # Cortesías
    cortesias = {
        "hola": "¡Hola! Soy tu asistente virtual del ITA. ¿Sobre qué trámite escolar tienes alguna duda hoy?",
        "gracias": "¡De nada! Éxito en tus trámites.",
        "adios": "¡Hasta luego!",
        "ayuda": "Pregúntame sobre: Inscripción, Servicio Social, Residencias, Becas o Titulación."
    }
    if user_msg in cortesias:
        return jsonify({"response": cortesias[user_msg]})

    # 1. VIA DE PRIORIDAD EXACTA: Si el usuario pone solo 1 palabra (ej. "Residencias")
    # Buscamos si coincide con una CATEGORIA General.
    if len(palabras) == 1:
        for item in base_conocimiento:
            if item["es_general"] and user_msg == limpiar_texto(item["categoria"]):
                return jsonify({"response": item["respuesta"]})

    # 2. BUSQUEDA POR SIMILITUD (PIPELINE NORMAL)
    candidatos = []
    for item in base_conocimiento:
        mejor_score = 0
        for clave in item["claves_busqueda"]:
            score = fuzz.token_set_ratio(user_msg, clave)
            if score > mejor_score:
                mejor_score = score
        candidatos.append({"item": item, "score": mejor_score})

    candidatos.sort(key=lambda x: x["score"], reverse=True)

    if not candidatos or candidatos[0]["score"] < 55:
        return jsonify({"response": "No estoy seguro de entender tu duda. ¿Te refieres a inscripciones, residencias o servicio social?"})

    # Si es una pregunta de varias palabras, aplicamos la lógica de "específico gana a general"
    seleccionado = candidatos[0]
    if seleccionado["item"]["es_general"] and len(palabras) > 1:
        for i in range(1, min(5, len(candidatos))):
            if candidatos[i]["score"] > 75 and not candidatos[i]["item"]["es_general"]:
                seleccionado = candidatos[i]
                break

    return jsonify({"response": seleccionado["item"]["respuesta"]})

if __name__ == '__main__':
    app.run()
