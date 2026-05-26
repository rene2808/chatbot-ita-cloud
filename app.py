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
    
    # Contar palabras para el enrutamiento de intención
    num_palabras = len(mensaje_original.strip().split())
    
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
            
            # --- MÉTODO DE ENRUTAMIENTO POR LONGITUD ---
            # Si es 1 o 2 palabras, priorizamos masivamente la respuesta GENERAL
            if item["es_general"] and num_palabras <= 2:
                score += 35
            
            # Si son más de 2 palabras, le damos un empuje a lo ESPECÍFICO
            if not item["es_general"] and num_palabras > 2:
                score += 10
                
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

    # Seleccionado inicial
    seleccionado = candidatos[0]

    # 🌟 LÓGICA DE DESAMBIGUACIÓN (Ties Detection)
    # Comparamos si el puntaje máximo tiene empates cercanos con otras categorías distintas
    max_score = seleccionado["score"]
    
    # Filtrar candidatos cercanos al puntaje máximo que pertenezcan a alta confianza (>= 70)
    empates = [c for c in candidatos if c["score"] >= max_score - margin and c["score"] >= 70]
    
    # Agrupar las categorías únicas de los empates
    categorias_candidatas = list(set(c["item"]["categoria"] for c in empates))
    
    # Solo mostramos ambigüedad si el usuario fue descriptivo (>2 palabras) 
    # para evitar que los botones generales disparen este mensaje.
    if len(categorias_candidatas) > 1 and num_palabras > 2:
        opciones = ", ".join(f"**{cat.title()}**" for cat in categorias_candidatas)
        respuesta = (
            f"Encontré información que coincide con tu duda en varias secciones: {opciones}. "
            "¿Podrías especificar un poco más tu pregunta? "
            f"Por ejemplo, puedes intentar preguntar sobre '{empates[0]['item']['categoria']} {empates[0]['item']['subcategoria']}'."
        )
    else:
        # No hay ambigüedad o es una sola categoría, tomamos el mejor resultado
        respuesta = seleccionado["item"]["respuesta"]

    return jsonify({"response": respuesta})

if __name__ == '__main__':
    app.run()
