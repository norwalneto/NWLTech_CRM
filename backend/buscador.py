import os
import re
from typing import Dict, List, Optional

import requests

APIFY_ACTOR_SYNC_URL = (
    "https://api.apify.com/v2/acts/compass~crawler-google-places/run-sync-get-dataset-items"
)


def formatar_link_whatsapp(telefone: Optional[str]) -> str:
    """Limpa o telefone, adiciona DDI 55 se necessário e monta o link wa.me."""
    digitos = re.sub(r"\D", "", telefone or "")
    if not digitos:
        return ""
    if not digitos.startswith("55") and len(digitos) in (10, 11):
        digitos = f"55{digitos}"
    return f"https://wa.me/{digitos}"


def _obter_token_apify(api_key_override: Optional[str] = None) -> str:
    """Obtém o token da Apify a partir do override ou das variáveis de ambiente."""
    token = (
        (api_key_override or "").strip()
        or os.getenv("APIFY_API_TOKEN", "").strip()
        or os.getenv("APIFY_TOKEN", "").strip()
    )
    if not token:
        raise ValueError(
            "Token da Apify não encontrado. Configure APIFY_API_TOKEN nas variáveis do Railway ou nos Ajustes."
        )
    return token


def _montar_consulta_local(
    nicho: str, cidade: str = "", estado: str = ""
) -> tuple[str, str]:
    """
    Monta termo de busca e localização:
    - Cidade + Estado: busca focada na cidade dentro do estado.
    - Apenas Estado: busca em todo o estado.
    - Apenas Cidade: busca na cidade.
    """
    nicho_limpo = (nicho or "").strip()
    cidade_limpa = (cidade or "").strip()
    estado_limpo = (estado or "").strip()

    if cidade_limpa and estado_limpo:
        local = f"{cidade_limpa}, {estado_limpo}, Brasil"
    elif estado_limpo:
        local = f"{estado_limpo}, Brasil"
    elif cidade_limpa:
        local = f"{cidade_limpa}, Brasil"
    else:
        local = "Brasil"

    termo = f"{nicho_limpo} {local}".strip() if nicho_limpo else local
    return termo, local


def executar_busca_google_maps(
    nicho: str,
    cidade: str = "",
    estado: str = "",
    raio_km: int = 15,
    max_resultados: int = 20,
    apenas_sem_site: bool = False,
    api_key_override: Optional[str] = None,
) -> Dict:
    """
    Executa a mineração de estabelecimentos no Google Maps via Apify
    (compass/crawler-google-places) e retorna leads padronizados para o CRM.
    """
    token = _obter_token_apify(api_key_override)
    limite = max(1, min(int(max_resultados or 20), 80))
    termo, local = _montar_consulta_local(nicho=nicho, cidade=cidade, estado=estado)

    payload = {
        "searchStringsArray": [termo],
        "locationQuery": local,
        "maxCrawledPlacesPerSearch": limite,
        "language": "pt-BR",
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    resp = requests.post(
        APIFY_ACTOR_SYNC_URL,
        json=payload,
        headers=headers,
        timeout=160,
    )
    resp.raise_for_status()
    itens = resp.json() or []

    leads: List[Dict] = []
    vistos = set()

    for item in itens:
        if not isinstance(item, dict):
            continue

        nome = (item.get("title") or item.get("name") or "").strip()
        if not nome:
            continue

        website = (item.get("website") or "").strip()
        if website and not website.startswith(("http://", "https://")):
            website = f"https://{website}"

        tem_site = bool(website)
        if apenas_sem_site and tem_site:
            continue

        telefone = (item.get("phone") or item.get("phoneUnformatted") or "").strip()
        place_id_raw = str(item.get("placeId") or "").strip()
        place_id = f"apify_{place_id_raw}" if place_id_raw else ""
        endereco = (item.get("address") or "").strip()

        chave = place_id or f"{nome.lower()}|{endereco.lower()}"
        if chave in vistos:
            continue
        vistos.add(chave)

        cidade_item = (item.get("city") or cidade or estado or "").strip()

        leads.append(
            {
                "place_id": place_id,
                "nome": nome,
                "telefone": telefone,
                "whatsapp_link": formatar_link_whatsapp(telefone),
                "endereco": endereco,
                "cidade": cidade_item,
                "nicho": (nicho or "").strip(),
                "website": website,
                "tem_site": tem_site,
                "avaliacao": float(item.get("totalScore") or 0.0),
                "total_avaliacoes": str(item.get("reviewsCount") or "0"),
                "status_kanban": "NOVO",
                "observacoes": "",
            }
        )

        if len(leads) >= limite:
            break

    return {
        "coordenadas_cidade": {
            "endereco_formatado": local,
            "raio_km": raio_km,
        },
        "total_encontrados": len(leads),
        "leads": leads,
    }