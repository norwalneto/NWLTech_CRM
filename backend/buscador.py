import os
import re
import time
from typing import List, Dict, Optional
import requests

GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
TEXTSEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"


def formatar_link_whatsapp(telefone: str) -> str:
    """Limpa o telefone, adiciona DDI 55 se necessário e monta o link wa.me."""
    digitos = re.sub(r"\D", "", telefone or "")
    if not digitos:
        return ""
    if not digitos.startswith("55") and len(digitos) in (10, 11):
        digitos = f"55{digitos}"
    return f"https://wa.me/{digitos}"


def obter_coordenadas_cidade(cidade: str, api_key: str) -> Dict:
    """Localiza o centro da cidade via Geocoding API sem precisar especificar bairro."""
    endereco_busca = cidade.strip()
    if "brasil" not in endereco_busca.lower() and "br" not in endereco_busca.lower():
        endereco_busca = f"{endereco_busca}, Brasil"

    params = {
        "address": endereco_busca,
        "language": "pt-BR",
        "region": "br",
        "key": api_key,
    }

    resp = requests.get(GEOCODE_URL, params=params, timeout=15)
    dados = resp.json()

    if dados.get("status") != "OK" or not dados.get("results"):
        raise ValueError(
            f"Geocoding não encontrou a cidade '{cidade}'. Status: {dados.get('status')} - {dados.get('error_message', '')}"
        )

    resultado = dados["results"][0]
    loc = resultado["geometry"]["location"]
    return {
        "lat": loc["lat"],
        "lng": loc["lng"],
        "endereco_formatado": resultado.get("formatted_address", cidade),
    }


def obter_detalhes_lugar(place_id: str, api_key: str) -> Dict:
    """Consulta telefone e site do estabelecimento na Place Details API."""
    params = {
        "place_id": place_id,
        "fields": "name,formatted_phone_number,international_phone_number,website,formatted_address,rating,user_ratings_total",
        "language": "pt-BR",
        "key": api_key,
    }
    try:
        resp = requests.get(DETAILS_URL, params=params, timeout=12)
        dados = resp.json()
        if dados.get("status") == "OK":
            return dados.get("result", {})
    except Exception as e:
        print(f"[AVISO] Falha ao buscar detalhes do place_id {place_id}: {e}")
    return {}


def executar_busca_google_maps(
    nicho: str,
    cidade: str,
    raio_km: int = 15,
    max_resultados: int = 20,
    apenas_sem_site: bool = False,
    api_key_override: Optional[str] = None,
) -> Dict:
    """Busca estabelecimentos pela palavra-chave em toda a cidade informada."""
    api_key = (api_key_override or os.getenv("GOOGLE_MAPS_API_KEY", "")).strip()
    if not api_key:
        raise ValueError(
            "GOOGLE_MAPS_API_KEY não configurada no arquivo .env ou nas variáveis do Railway."
        )

    geo = obter_coordenadas_cidade(cidade, api_key)
    lat, lng = geo["lat"], geo["lng"]
    raio_metros = max(1000, min(int(raio_km) * 1000, 50000))

    query_texto = f"{nicho.strip()} em {cidade.strip()}"
    params = {
        "query": query_texto,
        "location": f"{lat},{lng}",
        "radius": raio_metros,
        "language": "pt-BR",
        "region": "br",
        "key": api_key,
    }

    leads_coletados: List[Dict] = []
    proximo_token = None

    while len(leads_coletados) < max_resultados:
        if proximo_token:
            time.sleep(2)
            params = {"pagetoken": proximo_token, "key": api_key}

        resp = requests.get(TEXTSEARCH_URL, params=params, timeout=15)
        dados = resp.json()
        status = dados.get("status")

        if status not in ("OK", "ZERO_RESULTS"):
            raise ValueError(
                f"Erro na Places API: {status} - {dados.get('error_message', '')}"
            )

        resultados = dados.get("results", [])
        if not resultados:
            break

        for item in resultados:
            if len(leads_coletados) >= max_resultados:
                break

            place_id = item.get("place_id")
            if not place_id:
                continue

            detalhes = obter_detalhes_lugar(place_id, api_key)
            website = detalhes.get("website", "") or ""

            if apenas_sem_site and website:
                continue

            telefone = (
                detalhes.get("formatted_phone_number")
                or detalhes.get("international_phone_number")
                or ""
            )
            nome = detalhes.get("name") or item.get("name") or "Sem Nome"

            lead = {
                "place_id": place_id,
                "nome": nome,
                "telefone": telefone,
                "whatsapp_link": formatar_link_whatsapp(telefone),
                "endereco": detalhes.get("formatted_address") or item.get("formatted_address") or "",
                "cidade": cidade.strip(),
                "nicho": nicho.strip(),
                "website": website,
                "tem_site": bool(website),
                "avaliacao": detalhes.get("rating") or item.get("rating") or 0.0,
                "total_avaliacoes": detalhes.get("user_ratings_total") or item.get("user_ratings_total") or 0,
                "status_kanban": "NOVO",
            }
            leads_coletados.append(lead)

        proximo_token = dados.get("next_page_token")
        if not proximo_token:
            break

    return {
        "coordenadas_cidade": geo,
        "total_encontrados": len(leads_coletados),
        "leads": leads_coletados,
    }