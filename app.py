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
    # Normalizar texto: eliminar acentos (tildes) y diéresis en español
    texto = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('utf-8').lower()
    
    # Mantener solo letras, números y espacios
    texto = re.sub(r'[^\w\s]', '', texto)
    
    # Diccionario de equivalencias para lenguaje estudiantil
    equivalencias = {
        "tec": "tecnologico",
        "it": "instituto",
        "creditos": "actividades complementarias",
        "pago": "costo dinero referencia",
        "papeles": "documentos requisitos"
    }
    
    # Reemplazo seguro usando límites de palabras (\b) para evitar coincidencias parciales
    for corto, largo in equivalencias.items():
        if re.search(rf'\b{corto}\b', texto):
            texto += f" {largo}"
            
    return texto

# Base de conocimiento cargada en memoria
base_conocimiento = []

def cargar_conocimiento():
    global base_conocimiento
    try:
        with open('conocimiento.json', 'r', encoding='utf-8') as f:
            datos_json = json.load(f)
        
        base_conocimiento = []
        for categoria, subcategorias in datos_json.items():
            for subcategoria, respuesta in subcategorias.items():
                # Estructuramos las claves de búsqueda según la lógica de tu pipeline
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

# Carga inicial
cargar_conocimiento()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_response', methods=['POST'])
def get_response():
    # Recargar la base de datos si por algún motivo está vacía
    if not base_conocimiento:
        cargar_conocimiento()
        if not base_conocimiento:
            return jsonify({"response": "Error: La base de datos de conocimiento no pudo ser cargada. Por favor verifica que 'conocimiento.json' exista."})

    mensaje_original = request.json.get("message", "")
    user_msg = limpiar_texto(mensaje_original)
    num_palabras = len(mensaje_original.split())
    
    # 🌟 Manejar cortesías al instante para ahorrar procesamiento y sonar natural
    cortesias = {
        "hola": "¡Hola! Soy tu asistente virtual del ITA. ¿Sobre qué trámite escolar tienes alguna duda hoy?",
        "gracias": "¡De nada! Estoy aquí en la nube para ayudarte en lo que necesites. Éxito en tus trámites.",
        "adios": "¡Hasta luego! Recuerda que puedes volver a consultarme cuando tengas dudas.",
        "buenos dias": "¡Buenos días! Soy tu asistente virtual. ¿En qué te puedo asesorar hoy?",
        "buenas tardes": "¡Buenas tardes! ¿En qué trámite del ITA te puedo apoyar hoy?",
        "buenas noches": "¡Buenas noches! ¿Qué duda escolar tienes hoy?",
        "ayuda": "Pregúntame sobre: Inscripción, Servicio Social, Residencias, Becas, CENEVAL o Titulación."
    }
    
    msg_key = user_msg.strip()
    if msg_key in cortesias:
        return jsonify({"response": cortesias[msg_key]})
    
    # Calcular coincidencia para cada entrada en la base de conocimiento
    candidatos = []
    for item in base_conocimiento:
        mejor_score = 0
        for clave in item["claves_busqueda"]:
            score = fuzz.token_set_ratio(user_msg, clave)
            
            # --- MODIFICACIÓN DE PRECISIÓN ---
            # Si el usuario escribe 1 o 2 palabras (Intención de botón/rama)
            # le damos prioridad a la respuesta general.
            if item["es_general"] and num_palabras <= 2 and user_msg == limpiar_texto(item["categoria"]):
                score += 25
                
            if score > mejor_score:
                mejor_score = score
        
        candidatos.append({
            "item": item,
            "score": mejor_score
        })
    
    # Ordenar por puntaje descendente
    candidatos.sort(key=lambda x: x["score"], reverse=True)
    
    # Umbral de confianza mínimo
    umbral_minimo = 55
    margin = 5  # Margen de tolerancia para detectar ambigüedad
    
    if not candidatos or candidatos[0]["score"] < umbral_minimo:
        # 📝 REGISTRO DE ANALÍTICA (Azure logs)
        print(f"[ANALITICA - DUDA NO RESUELTA] Entrada original: '{mensaje_original}' | Limpio: '{user_msg}' | Puntuación Max: {candidatos[0]['score'] if candidatos else 0}", file=sys.stdout)
        return jsonify({"response": "No estoy seguro de entender tu duda. ¿Te refieres a inscripciones, residencias, servicio social o algún trámite escolar?"})

    # 🌟 LÓGICA DE DECISIÓN (Priority Filter)
    # Si la pregunta es larga (>2 palabras), permitimos que lo específico gane.
    # Si es corta, el bono anterior ya aseguró la respuesta general.
    seleccionado = candidatos[0]
    
    if seleccionado["item"]["es_general"] and num_palabras > 2:
        for i in range(1, min(5, len(candidatos))):
            if candidatos[i]["score"] > 75 and not candidatos[i]["item"]["es_general"]:
                seleccionado = candidatos[i]
                break

    # 🌟 LÓGICA DE DESAMBIGUACIÓN (Ties Detection)
    max_score = seleccionado["score"]
    empates = [c for c in candidatos if c["score"] >= max_score - margin and c["score"] >= 70]
    categorias_candidatas = list(set(c["item"]["categoria"] for c in empates))
    
    if len(categorias_candidatas) > 1 and num_palabras > 2:
        opciones = ", ".join(f"**{cat.title()}**" for cat in categorias_candidatas)
        respuesta = (
            f"Encontré información en varias secciones: {opciones}. "
            "¿Podrías especificar tu duda? "
            f"Por ejemplo: '{empates[0]['item']['categoria']} {empates[0]['item']['subcategoria']}'."
        )
    else:
        respuesta = seleccionado["item"]["respuesta"]

    return jsonify({"response": respuesta})

if __name__ == '__main__':
    app.run()
