import re
from typing import List, Dict, Optional
import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Apenas os servidores estáveis com suporte IPv4 garantido
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
]

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
    """Localiza a cidade via Nominatim (OpenStreetMap) e obtém o osm_id da área."""
    endereco_busca = cidade.strip()
    if "brasil" not in endereco_busca.lower():
        endereco_busca = f"{endereco_busca}, Brasil"

    params = {
        "q": endereco_busca,
        "format": "json",
        "limit": 1,
        "addressdetails": 1,
    }

    resp = requests.get(NOMINATIM_URL, params=params, headers=HEADERS_OSM, timeout=15)
    dados = resp.json()

    if not dados:
        raise ValueError(f"OpenStreetMap não encontrou a cidade '{cidade}'.")

    resultado = dados[0]
    
    # Calcula o ID de área do Overpass se o resultado for uma relação administrativa
    osm_type = resultado.get("osm_type", "")
    osm_id = int(resultado.get("osm_id", 0))
    area_id = None
    if osm_type == "relation" and osm_id > 0:
        area_id = 3600000000 + osm_id

    return {
        "lat": float(resultado["lat"]),
        "lng": float(resultado["lon"]),
        "area_id": area_id,
        "endereco_formatado": resultado.get("display_name", cidade),
    }


def mapear_tags_nicho(nicho: str) -> str:
    """Mapeia palavras-chave em português para tags comerciais do OpenStreetMap."""
    termo = nicho.lower().strip()
    
    mapa = {
        "academia": '["leisure"="fitness_centre"]',
        "clinica": '["amenity"~"clinic|doctors|dentist|hospital"]',
        "clínica": '["amenity"~"clinic|doctors|dentist|hospital"]',
        "dentista": '["amenity"="dentist"]',
        "odontologia": '["amenity"="dentist"]',
        "restaurante": '["amenity"~"restaurant|fast_food|cafe"]',
        "pizzaria": '["amenity"="restaurant"]["cuisine"~"pizza",i]',
        "farmacia": '["amenity"="pharmacy"]',
        "farmácia": '["amenity"="pharmacy"]',
        "oficina": '["shop"~"car_repair|tyres|car_parts"]',
        "mecanica": '["shop"="car_repair"]',
        "supermercado": '["shop"~"supermarket|convenience"]',
        "mercado": '["shop"~"supermarket|convenience"]',
        "padaria": '["shop"="bakery"]',
        "salao": '["shop"~"hairdresser|beauty"]',
        "salão": '["shop"~"hairdresser|beauty"]',
        "barbearia": '["shop"="hairdresser"]',
        "hotel": '["tourism"~"hotel|guest_house|hostel"]',
        "pousada": '["tourism"~"guest_house|hotel"]',
        "escola": '["amenity"~"school|kindergarten|language_school"]',
        "pet": '["shop"="pet"]',
        "petshop": '["shop"="pet"]',
        "loja": '["shop"]',
    }

    for chave, filtro in mapa.items():
        if chave in termo:
            return filtro

    return f'["name"~"{nicho.strip()}",i]'


def executar_busca_google_maps(
    nicho: str,
    cidade: str,
    raio_km: int = 10,
    max_resultados: int = 20,
    apenas_sem_site: bool = False,
    api_key_override: Optional[str] = None,
) -> Dict:
    """
    Executa a pesquisa ultrarrápida por área administrativa da cidade no OpenStreetMap.
    """
    geo = obter_coordenadas_cidade(cidade)
    lat, lng = geo["lat"], geo["lng"]
    area_id = geo.get("area_id")
    filtro_osm = mapear_tags_nicho(nicho)

    # Se encontrou o ID oficial do município, usa busca por área (instantânea).
    # Caso contrário, usa um raio curto e seguro de no máximo 5km.
    if area_id:
        overpass_query = f"""
        [out:json][timeout:25];
        area({area_id})->.searchArea;
        (
          node{filtro_osm}(area.searchArea);
          way{filtro_osm}(area.searchArea);
        );
        out center {max_resultados * 2};
        """
    else:
        raio_metros = max(1000, min(int(raio_km) * 1000, 5000))
        overpass_query = f"""
        [out:json][timeout:25];
        (
          node{filtro_osm}(around:{raio_metros},{lat},{lng});
          way{filtro_osm}(around:{raio_metros},{lat},{lng});
        );
        out center {max_resultados * 2};
        """

    resp = None
    erro_ultimo = None

    for url in OVERPASS_URLS:
        try:
            resp = requests.post(
                url,
                data={"data": overpass_query},
                headers=HEADERS_OSM,
                timeout=30,
            )
            if resp.status_code == 200:
                break
            else:
                erro_ultimo = f"HTTP {resp.status_code} em {url}"
        except Exception as e:
            erro_ultimo = str(e)
            continue

    if not resp or resp.status_code != 200:
        raise ValueError(f"Falha nos servidores Overpass: {erro_ultimo}")

    dados = resp.json()
    elementos = dados.get("elements", [])

    leads_coletados: List[Dict] = []

    for el in elementos:
        if len(leads_coletados) >= max_resultados:
            break

        tags = el.get("tags", {})
        nome = tags.get("name")
        if not nome:
            continue

        website = tags.get("website") or tags.get("contact:website") or tags.get("url") or ""
        if apenas_sem_site and website:
            continue

        telefone = (
            tags.get("phone")
            or tags.get("contact:phone")
            or tags.get("contact:whatsapp")
            or tags.get("mobile")
            or ""
        )

        rua = tags.get("addr:street", "")
        numero = tags.get("addr:housenumber", "")
        bairro = tags.get("addr:suburb", "")
        partes_end = [p for p in [f"{rua}, {numero}".strip(", "), bairro, cidade.strip()] if p]
        endereco_completo = " - ".join(partes_end)

        osm_id = f"osm_{el.get('type', 'node')}_{el.get('id')}"

        lead = {
            "place_id": osm_id,
            "nome": nome,
            "telefone": telefone,
            "whatsapp_link": formatar_link_whatsapp(telefone),
            "endereco": endereco_completo,
            "cidade": cidade.strip(),
            "nicho": nicho.strip(),
            "website": website,
            "tem_site": bool(website),
            "avaliacao": 0.0,
            "total_avaliacoes": 0,
            "status_kanban": "NOVO",
        }
        leads_coletados.append(lead)

    return {
        "coordenadas_cidade": geo,
        "total_encontrados": len(leads_coletados),
        "leads": leads_coletados,
    }
