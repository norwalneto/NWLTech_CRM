import re
from typing import List, Dict, Optional
import requests

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
PHOTON_SEARCH_URL = "https://photon.komoot.io/api/"

HEADERS_OSM = {
    "User-Agent": "NWLTechCRM/1.0 (contato@nwltecnologia.site)"
}


def formatar_link_whatsapp(telefone: str) -> str:
    """Limpa o telefone, adiciona DDI 55 se necessário e monta o link wa.me."""
    digitos = re.sub(r"\D", "", telefone or "")
    if not digitos:
        return ""
    if not digitos.startswith("55") and len(digitos) in (10, 11):
        digitos = f"55{digitos}"
    return f"https://wa.me/{digitos}"


def obter_coordenadas_cidade(cidade: str) -> Dict:
    """Localiza o centro da cidade via Nominatim."""
    endereco_busca = cidade.strip()
    if "brasil" not in endereco_busca.lower():
        endereco_busca = f"{endereco_busca}, Brasil"

    params = {
        "q": endereco_busca,
        "format": "json",
        "limit": 1,
    }

    resp = requests.get(NOMINATIM_SEARCH_URL, params=params, headers=HEADERS_OSM, timeout=15)
    dados = resp.json()

    if not dados:
        raise ValueError(f"Cidade '{cidade}' não encontrada.")

    resultado = dados[0]
    return {
        "lat": float(resultado["lat"]),
        "lng": float(resultado["lon"]),
        "endereco_formatado": resultado.get("display_name", cidade),
    }


def buscar_via_photon(nicho: str, cidade: str, lat: float, lng: float, max_resultados: int) -> List[Dict]:
    """Busca rápida de estabelecimentos comerciais usando o motor Photon (OpenStreetMap)."""
    query = f"{nicho.strip()} {cidade.strip()}"
    params = {
        "q": query,
        "lat": lat,
        "lon": lng,
        "limit": min(max_resultados * 2, 50),
    }

    resp = requests.get(PHOTON_SEARCH_URL, params=params, headers=HEADERS_OSM, timeout=15)
    if resp.status_code != 200:
        return []

    dados = resp.json()
    features = dados.get("features", [])
    resultados = []

    for feat in features:
        props = feat.get("properties", {})
        nome = props.get("name")
        if not nome:
            continue

        # Filtra para garantir que pertence à cidade ou região próxima
        cidade_item = (props.get("city") or props.get("county") or props.get("state") or "").lower()
        if cidade.strip().lower() not in cidade_item and "pernambuco" not in cidade_item and cidade_item != "":
            continue

        rua = props.get("street", "")
        numero = props.get("housenumber", "")
        bairro = props.get("district") or props.get("suburb") or ""
        cidade_final = props.get("city") or cidade.strip()

        partes_end = [p for p in [f"{rua}, {numero}".strip(", "), bairro, cidade_final] if p]
        endereco_completo = " - ".join(partes_end)

        osm_id = f"photon_{props.get('osm_type', 'N')}_{props.get('osm_id', len(resultados))}"

        resultados.append({
            "place_id": osm_id,
            "nome": nome,
            "telefone": "",
            "whatsapp_link": "",
            "endereco": endereco_completo,
            "cidade": cidade_final,
            "nicho": nicho.strip(),
            "website": "",
            "tem_site": False,
            "avaliacao": 0.0,
            "total_avaliacoes": 0,
            "status_kanban": "NOVO",
        })

    return resultados


def buscar_via_nominatim(nicho: str, cidade: str, max_resultados: int) -> List[Dict]:
    """Busca complementar diretamente no Nominatim com detalhes extras (telefone, site)."""
    query = f"{nicho.strip()} em {cidade.strip()}, Brasil"
    params = {
        "q": query,
        "format": "json",
        "addressdetails": 1,
        "extratags": 1,
        "limit": min(max_resultados * 2, 40),
    }

    resp = requests.get(NOMINATIM_SEARCH_URL, params=params, headers=HEADERS_OSM, timeout=15)
    if resp.status_code != 200:
        return []

    dados = resp.json()
    resultados = []

    for item in dados:
        nome = item.get("name")
        if not nome:
            continue

        extratags = item.get("extratags", {}) or {}
        address = item.get("address", {}) or {}

        website = extratags.get("website") or extratags.get("contact:website") or extratags.get("url") or ""
        telefone = (
            extratags.get("phone")
            or extratags.get("contact:phone")
            or extratags.get("contact:whatsapp")
            or ""
        )

        rua = address.get("road", "")
        numero = address.get("house_number", "")
        bairro = address.get("suburb") or address.get("neighbourhood") or ""
        cidade_final = address.get("city") or address.get("town") or cidade.strip()

        partes_end = [p for p in [f"{rua}, {numero}".strip(", "), bairro, cidade_final] if p]
        endereco_completo = " - ".join(partes_end) or item.get("display_name", "")

        osm_id = f"nom_{item.get('osm_type', 'node')}_{item.get('osm_id')}"

        resultados.append({
            "place_id": osm_id,
            "nome": nome,
            "telefone": telefone,
            "whatsapp_link": formatar_link_whatsapp(telefone),
            "endereco": endereco_completo,
            "cidade": cidade_final,
            "nicho": nicho.strip(),
            "website": website,
            "tem_site": bool(website),
            "avaliacao": 0.0,
            "total_avaliacoes": 0,
            "status_kanban": "NOVO",
        })

    return resultados


def executar_busca_google_maps(
    nicho: str,
    cidade: str,
    raio_km: int = 10,
    max_resultados: int = 20,
    apenas_sem_site: bool = False,
    api_key_override: Optional[str] = None,
) -> Dict:
    """
    Executa a pesquisa rápida combinando Nominatim (com tags de contato) e Photon API,
    eliminando timeouts e erros 504 da Overpass API.
    """
    geo = obter_coordenadas_cidade(cidade)
    lat, lng = geo["lat"], geo["lng"]

    # 1. Tenta primeiro pelo Nominatim (traz telefone e site quando cadastrados)
    leads_brutos = buscar_via_nominatim(nicho, cidade, max_resultados)

    # 2. Complementa com o Photon API se vierem poucos resultados
    if len(leads_brutos) < max_resultados:
        leads_photon = buscar_via_photon(nicho, cidade, lat, lng, max_resultados)
        nomes_existentes = {l["nome"].lower() for l in leads_brutos}
        for lp in leads_photon:
            if lp["nome"].lower() not in nomes_existentes:
                leads_brutos.append(lp)
                nomes_existentes.add(lp["nome"].lower())

    leads_coletados: List[Dict] = []
    for lead in leads_brutos:
        if len(leads_coletados) >= max_resultados:
            break
        if apenas_sem_site and lead["tem_site"]:
            continue
        leads_coletados.append(lead)

    return {
        "coordenadas_cidade": geo,
        "total_encontrados": len(leads_coletados),
        "leads": leads_coletados,
    }