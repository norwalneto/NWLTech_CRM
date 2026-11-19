import math
import os
import re
import unicodedata
from typing import Dict, List, Optional
from urllib.parse import quote

import requests

MAPBOX_GEOCODING_URL = "https://api.mapbox.com/geocoding/v5/mapbox.places"
MAPBOX_SEARCHBOX_URL = "https://api.mapbox.com/search/searchbox/v1/forward"


def formatar_link_whatsapp(telefone: Optional[str]) -> str:
    """Limpa o telefone, adiciona DDI 55 se necessário e monta o link wa.me."""
    digitos = re.sub(r"\D", "", telefone or "")
    if not digitos:
        return ""
    if not digitos.startswith("55") and len(digitos) in (10, 11):
        digitos = f"55{digitos}"
    return f"https://wa.me/{digitos}"


def _remover_acentos(texto: str) -> str:
    """Remove acentos para melhorar correspondências em buscas textuais."""
    nfkd = unicodedata.normalize("NFKD", texto or "")
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def _calcular_distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula a distância aproximada em km entre duas coordenadas (fórmula de Haversine)."""
    raio_terra_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * raio_terra_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _deslocar_coordenada(
    lat: float, lng: float, dist_km: float, angulo_graus: float
) -> tuple[float, float]:
    """Desloca um ponto (lat, lng) por dist_km em determinado ângulo para varrer o raio."""
    rad = math.radians(angulo_graus)
    d_lat = (dist_km / 111.32) * math.cos(rad)
    cos_lat = max(math.cos(math.radians(lat)), 0.1)
    d_lng = (dist_km / (111.32 * cos_lat)) * math.sin(rad)
    return lat + d_lat, lng + d_lng


def _obter_token_mapbox(api_key_override: Optional[str] = None) -> str:
    """Obtém o token da Mapbox a partir do override ou das variáveis de ambiente."""
    token = (
        (api_key_override or "").strip()
        or os.getenv("MAPBOX_ACCESS_TOKEN", "").strip()
        or os.getenv("MAPBOX_API_KEY", "").strip()
    )
    if not token:
        raise ValueError(
            "Token da Mapbox não encontrado. Configure MAPBOX_ACCESS_TOKEN nas Variables do Railway ou na chave da API."
        )
    return token


def obter_coordenadas_cidade(cidade: str, token: str) -> Dict:
    """Resolve latitude, longitude e endereço formatado da cidade via Mapbox Geocoding."""
    cidade_limpa = cidade.strip()
    if not cidade_limpa:
        raise ValueError("Cidade não informada.")

    termo_codificado = quote(f"{cidade_limpa}, Brasil", safe="")
    url = f"{MAPBOX_GEOCODING_URL}/{termo_codificado}.json"
    params = {
        "access_token": token,
        "country": "br",
        "types": "place,locality,neighborhood,region",
        "language": "pt",
        "limit": 1,
    }

    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    dados = resp.json()

    features = dados.get("features") or []
    if not features:
        raise ValueError(f"Cidade '{cidade}' não encontrada na Mapbox.")

    feat = features[0]
    center = feat.get("center") or [0.0, 0.0]  # Mapbox retorna [lon, lat]
    lon, lat = float(center[0]), float(center[1])

    return {
        "lat": lat,
        "lng": lon,
        "endereco_formatado": feat.get("place_name") or cidade_limpa,
    }


def _extrair_telefone(props: Dict) -> str:
    """Extrai telefone caso a feature retorne algum campo de contato."""
    candidatos = [
        props.get("phone"),
        props.get("tel"),
        props.get("contact_phone"),
    ]
    for cand in candidatos:
        if cand and str(cand).strip():
            return str(cand).strip()
    return ""


def _extrair_website(props: Dict) -> str:
    """Extrai website caso a feature retorne URL."""
    candidatos = [
        props.get("website"),
        props.get("url"),
    ]
    for cand in candidatos:
        if cand and str(cand).strip():
            url = str(cand).strip()
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url
            return url
    return ""


def _extrair_cidade_feature(feat: Dict, cidade_padrao: str) -> str:
    """Extrai a cidade a partir do contexto da Mapbox."""
    ctx = feat.get("context")
    if isinstance(ctx, list):
        for item in ctx:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id") or "")
            if item_id.startswith("place.") or item_id.startswith("locality."):
                if item.get("text"):
                    return str(item.get("text")).strip()
    elif isinstance(ctx, dict):
        place_obj = ctx.get("place") or ctx.get("locality")
        if isinstance(place_obj, dict) and place_obj.get("name"):
            return str(place_obj.get("name")).strip()
    return cidade_padrao.strip()


def _extrair_coordenadas_feature(feat: Dict) -> Optional[tuple[float, float]]:
    """Extrai (lat, lon) de features da Geocoding API ou Search Box API."""
    geom = feat.get("geometry") or {}
    coords = geom.get("coordinates")
    if isinstance(coords, (list, tuple)) and len(coords) >= 2:
        return float(coords[1]), float(coords[0])

    props = feat.get("properties") or {}
    coords_prop = props.get("coordinates") or {}
    if isinstance(coords_prop, dict):
        lat = coords_prop.get("latitude") or coords_prop.get("lat")
        lon = coords_prop.get("longitude") or coords_prop.get("lng") or coords_prop.get("lon")
        if lat is not None and lon is not None:
            return float(lat), float(lon)

    return None


def _montar_pontos_varredura(
    lat: float, lng: float, raio_max: float, alvo: int
) -> List[tuple[float, float]]:
    """Gera o ponto central e pontos deslocados dentro do raio para ampliar a coleta."""
    pontos = [(lat, lng)]
    if alvo <= 10:
        return pontos

    passo_proximo = max(1.5, min(raio_max * 0.35, 5.0))
    for angulo in (0, 60, 120, 180, 240, 300):
        pontos.append(_deslocar_coordenada(lat, lng, passo_proximo, angulo))

    if alvo > 20 and raio_max >= 5.0:
        passo_afastado = min(raio_max * 0.75, max(passo_proximo * 1.8, 6.0))
        for angulo in (30, 90, 150, 210, 270, 330):
            pontos.append(_deslocar_coordenada(lat, lng, passo_afastado, angulo))

    return pontos


def _montar_variacoes_consulta(nicho: str, cidade: str) -> List[str]:
    """Cria variações do termo de busca para o loop tentar caso venha vazio ou pouco."""
    nicho_limpo = nicho.strip()
    cidade_limpa = cidade.strip()
    nicho_sem_acento = _remover_acentos(nicho_limpo)
    cidade_sem_acento = _remover_acentos(cidade_limpa)

    candidatos = [
        f"{nicho_limpo} {cidade_limpa}".strip(),
        f"{nicho_sem_acento} {cidade_sem_acento}".strip(),
        nicho_limpo,
        nicho_sem_acento,
    ]

    palavras = [p for p in re.split(r"\s+", nicho_sem_acento) if len(p) >= 3]
    if len(palavras) >= 2:
        candidatos.append(f"{palavras[-1]} {cidade_sem_acento}".strip())
        candidatos.append(palavras[-1])

    variacoes_unicas: List[str] = []
    vistas = set()
    for item in candidatos:
        chave = item.lower().strip()
        if chave and chave not in vistas:
            vistas.add(chave)
            variacoes_unicas.append(item.strip())

    return variacoes_unicas


def _consultar_geocoding_ponto(
    termo: str,
    p_lat: float,
    p_lng: float,
    token: str,
    usar_types_poi: bool = True,
) -> List[Dict]:
    """Primeira URL: Mapbox Geocoding API."""
    termo_codificado = quote(termo, safe="")
    url = f"{MAPBOX_GEOCODING_URL}/{termo_codificado}.json"
    params = {
        "access_token": token,
        "country": "br",
        "language": "pt",
        "proximity": f"{p_lng:.6f},{p_lat:.6f}",
        "limit": 10,
    }
    if usar_types_poi:
        params["types"] = "poi"

    resp = requests.get(url, params=params, timeout=15)
    if resp.status_code == 400 and usar_types_poi:
        return _consultar_geocoding_ponto(termo, p_lat, p_lng, token, usar_types_poi=False)

    resp.raise_for_status()
    payload = resp.json()
    return payload.get("features") or []


def _consultar_searchbox_ponto(
    termo: str,
    p_lat: float,
    p_lng: float,
    token: str,
) -> List[Dict]:
    """Segunda URL (após Geocoding): Mapbox Search Box /forward com limit=10."""
    params = {
        "q": termo,
        "access_token": token,
        "country": "BR",
        "language": "pt",
        "proximity": f"{p_lng:.6f},{p_lat:.6f}",
        "limit": 10,
    }
    try:
        resp = requests.get(MAPBOX_SEARCHBOX_URL, params=params, timeout=15)
        if resp.status_code == 400:
            return []
        resp.raise_for_status()
        payload = resp.json()
        return payload.get("features") or []
    except requests.RequestException:
        return []


def _processar_features(
    features: List[Dict],
    lat_centro: float,
    lng_centro: float,
    raio_max: float,
    cidade: str,
    nicho: str,
    apenas_sem_site: bool,
    alvo: int,
    leads_formatados: List[Dict],
    ids_vistos: set,
) -> None:
    """Normaliza e adiciona leads únicos dentro do raio até atingir o alvo."""
    for feat in features:
        if len(leads_formatados) >= alvo:
            break

        props = feat.get("properties") or {}
        coordenadas = _extrair_coordenadas_feature(feat)

        if coordenadas is not None:
            lat_item, lon_item = coordenadas
            distancia = _calcular_distancia_km(lat_centro, lng_centro, lat_item, lon_item)
            if distancia > raio_max:
                continue
        else:
            lon_item, lat_item = 0.0, 0.0

        nome = (
            feat.get("text")
            or props.get("name")
            or props.get("name_preferred")
            or ""
        ).strip()
        if not nome:
            continue

        mapbox_id = str(feat.get("id") or props.get("mapbox_id") or "").strip()
        chave_unica = mapbox_id or f"{nome.lower()}|{lat_item:.5f},{lon_item:.5f}"
        if chave_unica in ids_vistos:
            continue
        ids_vistos.add(chave_unica)

        endereco = str(
            feat.get("place_name")
            or props.get("full_address")
            or props.get("address")
            or ""
        ).strip()
        cidade_item = _extrair_cidade_feature(feat, cidade)

        telefone = _extrair_telefone(props)
        website = _extrair_website(props)
        tem_site = bool(website)

        if apenas_sem_site and tem_site:
            continue

        place_id = f"mapbox_{mapbox_id}" if mapbox_id else ""

        leads_formatados.append(
            {
                "place_id": place_id,
                "nome": nome,
                "telefone": telefone,
                "whatsapp_link": formatar_link_whatsapp(telefone),
                "endereco": endereco,
                "cidade": cidade_item,
                "nicho": nicho.strip(),
                "website": website,
                "tem_site": tem_site,
                "avaliacao": 0.0,
                "total_avaliacoes": "0",
                "status_kanban": "NOVO",
                "observacoes": "",
            }
        )


def buscar_via_mapbox(
    nicho: str,
    cidade: str,
    lat: float,
    lng: float,
    raio_km: int,
    max_resultados: int,
    apenas_sem_site: bool = False,
    token: str = "",
) -> List[Dict]:
    """
    Loop de busca:
    1) Varre pontos e variações na Mapbox Geocoding API.
    2) Caso ainda falte para atingir max_resultados, chama a segunda URL (Search Box /forward).
    """
    alvo = max(1, min(int(max_resultados or 20), 60))
    raio_max = max(1.0, float(raio_km or 15))
    pontos_busca = _montar_pontos_varredura(lat, lng, raio_max, alvo)
    variacoes_termo = _montar_variacoes_consulta(nicho, cidade)

    leads_formatados: List[Dict] = []
    ids_vistos = set()

    # Etapa 1: Loop na Mapbox Geocoding API
    for idx_termo, termo in enumerate(variacoes_termo):
        if len(leads_formatados) >= alvo:
            break

        pontos_da_rodada = pontos_busca if idx_termo == 0 else pontos_busca[:4]

        for p_lat, p_lng in pontos_da_rodada:
            if len(leads_formatados) >= alvo:
                break

            features = _consultar_geocoding_ponto(
                termo=termo,
                p_lat=p_lat,
                p_lng=p_lng,
                token=token,
                usar_types_poi=True,
            )
            _processar_features(
                features=features,
                lat_centro=lat,
                lng_centro=lng,
                raio_max=raio_max,
                cidade=cidade,
                nicho=nicho,
                apenas_sem_site=apenas_sem_site,
                alvo=alvo,
                leads_formatados=leads_formatados,
                ids_vistos=ids_vistos,
            )

    # Etapa 2: Segunda URL após Geocoding (Search Box /forward com limit=10)
    if len(leads_formatados) < alvo:
        for termo in variacoes_termo[:3]:
            if len(leads_formatados) >= alvo:
                break

            for p_lat, p_lng in pontos_busca[:5]:
                if len(leads_formatados) >= alvo:
                    break

                features_sb = _consultar_searchbox_ponto(
                    termo=termo,
                    p_lat=p_lat,
                    p_lng=p_lng,
                    token=token,
                )
                _processar_features(
                    features=features_sb,
                    lat_centro=lat,
                    lng_centro=lng,
                    raio_max=raio_max,
                    cidade=cidade,
                    nicho=nicho,
                    apenas_sem_site=apenas_sem_site,
                    alvo=alvo,
                    leads_formatados=leads_formatados,
                    ids_vistos=ids_vistos,
                )

    return leads_formatados


def executar_busca_google_maps(
    nicho: str,
    cidade: str,
    raio_km: int = 15,
    max_resultados: int = 20,
    apenas_sem_site: bool = False,
    api_key_override: Optional[str] = None,
) -> Dict:
    """
    Executa a busca de estabelecimentos/clínicas utilizando a Mapbox Geocoding API
    e, em seguida, a Search Box API como segunda etapa no loop.
    """
    token = _obter_token_mapbox(api_key_override)
    geo = obter_coordenadas_cidade(cidade=cidade, token=token)

    leads_coletados = buscar_via_mapbox(
        nicho=nicho,
        cidade=cidade,
        lat=geo["lat"],
        lng=geo["lng"],
        raio_km=raio_km,
        max_resultados=max_resultados,
        apenas_sem_site=apenas_sem_site,
        token=token,
    )

    return {
        "coordenadas_cidade": geo,
        "total_encontrados": len(leads_coletados),
        "leads": leads_coletados,
    }