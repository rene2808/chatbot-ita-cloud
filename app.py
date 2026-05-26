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
                base_conocimiento.append({
                    "categoria": categoria,
                    "subcategoria": subcategoria,
                    "claves_busqueda": [
                        limpiar_texto(f"{categoria} {subcategoria}"),
                        limpiar_texto(subcategoria)
                    ],
                    "respuesta": respuesta
                })
        print(f"Base de conocimiento cargada con éxito. Total registros: {len(base_conocimiento)}")
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
    resultados = []
    for item in base_conocimiento:
        mejor_score = 0
        mejor_clave = ""
        for clave in item["claves_busqueda"]:
            # Usamos token_set_ratio ya que es sumamente potente para intenciones desordenadas
            score = fuzz.token_set_ratio(user_msg, clave)
            if score > mejor_score:
                mejor_score = score
                mejor_clave = clave
        
        resultados.append({
            "item": item,
            "score": mejor_score,
            "clave_emparejada": mejor_clave
        })
    
    # Ordenar por puntaje descendente
    resultados.sort(key=lambda x: x["score"], reverse=True)
    
    # Umbral de confianza mínimo
    umbral_minimo = 55
    margin = 5  # Margen de tolerancia para detectar ambigüedad
    
    if not resultados or resultados[0]["score"] < umbral_minimo:
        # 📝 REGISTRO DE ANALÍTICA (Azure logs): Registra dudas no resueltas para mejorar el JSON
        print(f"[ANALITICA - DUDA NO RESUELTA] Entrada original: '{mensaje_original}' | Limpio: '{user_msg}' | Puntuación Max: {resultados[0]['score'] if resultados else 0}", file=sys.stdout)
        
        respuesta = "No estoy seguro de entender tu duda. ¿Te refieres a inscripciones, residencias, servicio social o algún trámite escolar?"
    else:
        max_score = resultados[0]["score"]
        
        # Filtrar candidatos que están muy cerca del puntaje máximo (ambigüedad potencial)
        # Solo consideramos ambigüedad si los candidatos tienen una alta confianza (>= 70)
        candidatos = [r for r in resultados if r["score"] >= max_score - margin and r["score"] >= 70]
        
        # Agrupar las categorías únicas de estos candidatos
        categorias_candidatas = list(set(c["item"]["categoria"] for c in candidatos))
        
        if len(categorias_candidatas) > 1:
            # Ambigüedad detectada: múltiples categorías válidas con puntajes altos similares
            opciones = ", ".join(f"**{cat.title()}**" for cat in categorias_candidatas)
            respuesta = (
                f"Encontré información que coincide con tu duda en varias secciones: {opciones}. "
                "¿Podrías especificar un poco más tu pregunta? "
                f"Por ejemplo, puedes intentar preguntar sobre '{candidatos[0]['item']['categoria']} {candidatos[0]['item']['subcategoria']}'."
            )
        else:
            # No hay ambigüedad o es una sola categoría, tomamos el mejor resultado
            respuesta = resultados[0]["item"]["respuesta"]

    return jsonify({"response": respuesta})

if __name__ == '__main__':
    app.run()