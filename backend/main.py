import json
import os
from datetime import datetime
from typing import Optional
import requests
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from database import (
    BASE_DIR,
    CSV_PATH,
    DATABASE_URL,
    BANCO_CONECTADO,
    TIPO_BANCO_ATIVO,
    TABELA_LEADS_CRIADA,
    ERRO_CONEXAO_BANCO,
    init_storage,
    sincronizar_banco_para_csv,
    listar_leads,
    salvar_novos_leads,
    atualizar_lead,
    deletar_lead,
)
from buscador import executar_busca_google_maps, formatar_link_whatsapp

load_dotenv(BASE_DIR / ".env")
init_storage()

WHATSAPP_STORE_PATH = BASE_DIR / "whatsapp_conversas.json"
WHATSAPP_CONFIG_PATH = BASE_DIR / "whatsapp_config.json"

app = FastAPI(
    title="NWL Tech CRM & Buscador API",
    version="1.3.0",
    description="Backend híbrido (CSV Raiz + Railway DB) para Mobile CRM, Buscador e WhatsApp Cloud API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BuscaRequest(BaseModel):
    nicho: str
    cidade: Optional[str] = ""
    estado: Optional[str] = ""
    raio_km: int = 15
    max_resultados: int = 20
    apenas_sem_site: bool = False
    api_key: Optional[str] = None


class NovoLeadManualRequest(BaseModel):
    nome: str
    telefone: str = ""
    cidade: str = ""
    nicho: str = ""
    website: str = ""
    observacoes: str = ""
    status_kanban: str = "NOVO"


class AtualizarLeadRequest(BaseModel):
    nome: Optional[str] = None
    telefone: Optional[str] = None
    endereco: Optional[str] = None
    cidade: Optional[str] = None
    nicho: Optional[str] = None
    website: Optional[str] = None
    status_kanban: Optional[str] = None
    observacoes: Optional[str] = None


class EnviarMensagemWhatsAppRequest(BaseModel):
    telefone: str
    mensagem: str


class EnviarTemplateWhatsAppRequest(BaseModel):
    telefone: str
    template_nome: str = "hello_world"
    idioma: str = "pt_BR"


class CriarTemplateWhatsAppRequest(BaseModel):
    nome: str
    categoria: str = "MARKETING"
    idioma: str = "pt_BR"
    corpo: str


class ConfigWhatsAppRequest(BaseModel):
    verify_token: Optional[str] = ""
    phone_number_id: Optional[str] = ""
    waba_id: Optional[str] = ""
    access_token: Optional[str] = ""


def _normalizar_telefone(telefone: str) -> str:
    digitos = "".join(filter(str.isdigit, str(telefone or "")))
    if digitos and not digitos.startswith("55") and len(digitos) in (10, 11):
        return f"55{digitos}"
    return digitos


def _hora_atual() -> str:
    return datetime.now().strftime("%H:%M")


def _carregar_config_meta() -> dict:
    salvo = {}
    if WHATSAPP_CONFIG_PATH.exists():
        try:
            salvo = json.loads(WHATSAPP_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            salvo = {}

    return {
        "verify_token": (os.getenv("WHATSAPP_VERIFY_TOKEN") or salvo.get("verify_token") or "nwltech_verify_token").strip(),
        "phone_number_id": (os.getenv("WHATSAPP_PHONE_NUMBER_ID") or salvo.get("phone_number_id") or "").strip(),
        "waba_id": (os.getenv("WHATSAPP_WABA_ID") or salvo.get("waba_id") or "").strip(),
        "access_token": (os.getenv("WHATSAPP_ACCESS_TOKEN") or salvo.get("access_token") or "").strip(),
    }


def _salvar_config_meta(dados: dict) -> dict:
    atual = _carregar_config_meta()
    for chave in ("verify_token", "phone_number_id", "waba_id", "access_token"):
        valor = (dados.get(chave) or "").strip()
        if valor:
            atual[chave] = valor
        elif chave in dados and dados[chave] == "":
            atual[chave] = ""
    WHATSAPP_CONFIG_PATH.write_text(json.dumps(atual, ensure_ascii=False, indent=2), encoding="utf-8")
    return atual


def _carregar_conversas() -> list:
    if not WHATSAPP_STORE_PATH.exists():
        return []
    try:
        dados = json.loads(WHATSAPP_STORE_PATH.read_text(encoding="utf-8"))
        return dados if isinstance(dados, list) else []
    except Exception:
        return []


def _salvar_conversas(conversas: list) -> None:
    WHATSAPP_STORE_PATH.write_text(json.dumps(conversas, ensure_ascii=False, indent=2), encoding="utf-8")


def _buscar_nome_lead_por_telefone(tel_normalizado: str) -> str:
    if not tel_normalizado:
        return ""
    for lead in listar_leads():
        if _normalizar_telefone(lead.get("telefone") or "") == tel_normalizado:
            return (lead.get("nome") or "").strip()
    return ""


def _registrar_mensagem_conversa(
    telefone: str,
    texto: str,
    direcao: str = "sent",
    nome_contato: Optional[str] = None,
    abrir_janela_24h: Optional[bool] = None,
    incrementar_nao_lidas: bool = False,
) -> dict:
    tel_norm = _normalizar_telefone(telefone) or str(telefone or "").strip()
    conversas = _carregar_conversas()
    hora = _hora_atual()

    conversa = next((c for c in conversas if _normalizar_telefone(c.get("telefone") or "") == tel_norm), None)

    if not conversa:
        nome_resolvido = (nome_contato or "").strip() or _buscar_nome_lead_por_telefone(tel_norm) or (telefone or tel_norm)
        conversa = {
            "id": tel_norm or str(int(datetime.now().timestamp())),
            "nome": nome_resolvido,
            "telefone": telefone or tel_norm,
            "ultima_mensagem": texto,
            "hora": hora,
            "nao_lidas": 1 if incrementar_nao_lidas else 0,
            "janela_24h": bool(abrir_janela_24h) if abrir_janela_24h is not None else (direcao == "received"),
            "mensagens": [],
        }
        conversas.insert(0, conversa)
    else:
        if nome_contato and nome_contato.strip():
            conversa["nome"] = nome_contato.strip()
        conversa["ultima_mensagem"] = texto
        conversa["hora"] = hora
        if abrir_janela_24h is not None:
            conversa["janela_24h"] = bool(abrir_janela_24h)
        elif direcao == "received":
            conversa["janela_24h"] = True

        if incrementar_nao_lidas and direcao == "received":
            conversa["nao_lidas"] = int(conversa.get("nao_lidas") or 0) + 1

        conversas = [conversa] + [c for c in conversas if c.get("id") != conversa.get("id")]

    mensagens = conversa.get("mensagens")
    if not isinstance(mensagens, list):
        mensagens = []
    mensagens.append({
        "direcao": direcao,
        "texto": texto,
        "hora": hora,
    })
    conversa["mensagens"] = mensagens

    _salvar_conversas(conversas)
    return conversa


@app.get("/")
def health_check():
    init_storage()
    cfg = _carregar_config_meta()
    return {
        "status": "online",
        "servico": "NWL Tech CRM Backend",
        "pasta_raiz_detectada": str(BASE_DIR),
        "arquivo_csv": str(CSV_PATH),
        "banco_railway_conectado": BANCO_CONECTADO,
        "tipo_banco": TIPO_BANCO_ATIVO,
        "tabela_leads_criada": TABELA_LEADS_CRIADA,
        "erro_banco": ERRO_CONEXAO_BANCO or None,
        "apify_api_configurada": bool(
            os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_TOKEN")
        ),
        "google_api_configurada": bool(os.getenv("GOOGLE_MAPS_API_KEY")),
        "whatsapp_api_configurada": bool(cfg.get("access_token") and cfg.get("phone_number_id")),
    }


@app.post("/api/buscar")
def iniciar_buscador(req: BuscaRequest):
    if not req.nicho.strip():
        raise HTTPException(status_code=400, detail="Informe a palavra-chave (nicho).")
    if not (req.cidade or "").strip() and not (req.estado or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Informe pelo menos a cidade ou o estado.",
        )

    try:
        resultado_busca = executar_busca_google_maps(
            nicho=req.nicho,
            cidade=(req.cidade or "").strip(),
            estado=(req.estado or "").strip(),
            raio_km=req.raio_km,
            max_resultados=req.max_resultados,
            apenas_sem_site=req.apenas_sem_site,
            api_key_override=req.api_key,
        )
        resumo_banco = salvar_novos_leads(resultado_busca["leads"])

        return {
            "sucesso": True,
            "cidade_resolvida": resultado_busca["coordenadas_cidade"]["endereco_formatado"],
            "encontrados_na_busca": resultado_busca["total_encontrados"],
            "novos_salvos": resumo_banco["inseridos"],
            "duplicados_ignorados": resumo_banco["duplicados_ignorados"],
            "leads": listar_leads(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno no buscador: {str(e)}")


@app.get("/api/leads")
def obter_leads(
    status: Optional[str] = Query(None),
    cidade: Optional[str] = Query(None),
    nicho: Optional[str] = Query(None),
    apenas_sem_site: bool = Query(False),
):
    leads = listar_leads(
        status=status,
        cidade=cidade,
        nicho=nicho,
        apenas_sem_site=apenas_sem_site,
    )
    return {"total": len(leads), "leads": leads}


@app.post("/api/leads")
def adicionar_lead_manual(req: NovoLeadManualRequest):
    if not req.nome.strip():
        raise HTTPException(status_code=400, detail="O nome do lead é obrigatório.")

    novo = {
        "nome": req.nome.strip(),
        "telefone": req.telefone.strip(),
        "whatsapp_link": formatar_link_whatsapp(req.telefone),
        "cidade": req.cidade.strip(),
        "nicho": req.nicho.strip(),
        "website": req.website.strip(),
        "observacoes": req.observacoes.strip(),
        "status_kanban": req.status_kanban.upper(),
    }
    resumo = salvar_novos_leads([novo])
    return {"sucesso": True, "resumo": resumo, "leads": listar_leads()}


def _executar_atualizacao_lead(lead_id: str, body: AtualizarLeadRequest):
    try:
        atualizado = atualizar_lead(
            lead_id=lead_id,
            nome=body.nome,
            telefone=body.telefone,
            whatsapp_link=formatar_link_whatsapp(body.telefone) if body.telefone is not None else None,
            endereco=body.endereco,
            cidade=body.cidade,
            nicho=body.nicho,
            website=body.website,
            status_kanban=body.status_kanban.upper() if body.status_kanban else None,
            observacoes=body.observacoes,
        )
    except TypeError:
        atualizado = atualizar_lead(
            lead_id=lead_id,
            status_kanban=body.status_kanban.upper() if body.status_kanban else None,
            observacoes=body.observacoes,
        )

    if not atualizado:
        raise HTTPException(status_code=404, detail="Lead não encontrado.")
    return {"sucesso": True, "lead": atualizado, "leads": listar_leads()}


@app.put("/api/leads/{lead_id}")
def editar_lead_completo(lead_id: str, body: AtualizarLeadRequest):
    return _executar_atualizacao_lead(lead_id, body)


@app.patch("/api/leads/{lead_id}")
def editar_lead_kanban(lead_id: str, body: AtualizarLeadRequest):
    return _executar_atualizacao_lead(lead_id, body)


@app.delete("/api/leads/limpar-sem-telefone")
def limpar_leads_sem_telefone():
    leads = listar_leads()
    removidos = 0
    for item in leads:
        tel_digitos = "".join(filter(str.isdigit, str(item.get("telefone") or "")))
        if not tel_digitos:
            lead_id = str(item.get("id") or item.get("place_id") or "")
            if lead_id and deletar_lead(lead_id):
                removidos += 1
    return {"sucesso": True, "removidos": removidos, "leads": listar_leads()}


@app.delete("/api/leads/{lead_id}")
def excluir_lead(lead_id: str):
    removido = deletar_lead(lead_id)
    if not removido:
        raise HTTPException(status_code=404, detail="Lead não encontrado.")
    return {"sucesso": True, "leads": listar_leads()}


@app.get("/api/leads/exportar/csv")
def baixar_csv():
    init_storage()
    sincronizar_banco_para_csv()
    return FileResponse(
        path=CSV_PATH,
        media_type="text/csv",
        filename="leads.csv",
    )


# --- WHATSAPP CLOUD API: CONFIGURAÇÕES, CONVERSAS E ENVIO ---

@app.get("/api/whatsapp/config")
def obter_config_whatsapp():
    cfg = _carregar_config_meta()
    return {
        "sucesso": True,
        "verify_token": cfg.get("verify_token", ""),
        "phone_number_id": cfg.get("phone_number_id", ""),
        "waba_id": cfg.get("waba_id", ""),
        "access_token_configurado": bool(cfg.get("access_token")),
    }


@app.post("/api/whatsapp/config")
def salvar_config_whatsapp(req: ConfigWhatsAppRequest):
    cfg = _salvar_config_meta(req.model_dump())
    return {
        "sucesso": True,
        "phone_number_id": cfg.get("phone_number_id", ""),
        "waba_id": cfg.get("waba_id", ""),
        "verify_token": cfg.get("verify_token", ""),
        "access_token_configurado": bool(cfg.get("access_token")),
    }


@app.get("/api/whatsapp/conversas")
def listar_conversas_whatsapp():
    conversas = _carregar_conversas()
    return {"sucesso": True, "total": len(conversas), "conversas": conversas}


@app.post("/api/whatsapp/enviar")
def enviar_mensagem_whatsapp(req: EnviarMensagemWhatsAppRequest):
    """Dispara mensagens de texto livre através da WhatsApp Business Platform (Cloud API)."""
    cfg = _carregar_config_meta()
    token = cfg.get("access_token", "")
    phone_number_id = cfg.get("phone_number_id", "")

    if not token or not phone_number_id:
        raise HTTPException(
            status_code=400,
            detail="Credenciais do WhatsApp (WHATSAPP_ACCESS_TOKEN ou PHONE_NUMBER_ID) não configuradas.",
        )

    telefone_limpo = _normalizar_telefone(req.telefone)
    if not telefone_limpo:
        raise HTTPException(status_code=400, detail="Número de telefone inválido.")

    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefone_limpo,
        "type": "text",
        "text": {"preview_url": True, "body": req.mensagem},
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        resposta_meta = response.json()

        if response.status_code not in (200, 201):
            erro_msg = resposta_meta.get("error", {}).get("message", "Erro desconhecido na API da Meta")
            raise HTTPException(status_code=400, detail=f"Erro Meta WhatsApp: {erro_msg}")

        conversa = _registrar_mensagem_conversa(
            telefone=req.telefone,
            texto=req.mensagem,
            direcao="sent",
        )
        return {"sucesso": True, "resposta_meta": resposta_meta, "conversa": conversa}
    except HTTPException:
        raise
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Falha de conexão com a API do WhatsApp: {str(e)}")


@app.post("/api/whatsapp/enviar-template")
def enviar_template_whatsapp(req: EnviarTemplateWhatsAppRequest):
    """Dispara modelo (template) aprovado na Meta para iniciar conversa fora da janela de 24h."""
    cfg = _carregar_config_meta()
    token = cfg.get("access_token", "")
    phone_number_id = cfg.get("phone_number_id", "")

    if not token or not phone_number_id:
        raise HTTPException(
            status_code=400,
            detail="Credenciais do WhatsApp (WHATSAPP_ACCESS_TOKEN ou PHONE_NUMBER_ID) não configuradas.",
        )

    telefone_limpo = _normalizar_telefone(req.telefone)
    if not telefone_limpo:
        raise HTTPException(status_code=400, detail="Número de telefone inválido.")

    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefone_limpo,
        "type": "template",
        "template": {
            "name": (req.template_nome or "hello_world").strip(),
            "language": {"code": (req.idioma or "pt_BR").strip()},
        },
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        resposta_meta = response.json()

        if response.status_code not in (200, 201):
            erro_msg = resposta_meta.get("error", {}).get("message", "Erro desconhecido na API da Meta")
            raise HTTPException(status_code=400, detail=f"Erro Meta Template: {erro_msg}")

        texto_historico = f"[Modelo: {req.template_nome}] ({req.idioma})"
        conversa = _registrar_mensagem_conversa(
            telefone=req.telefone,
            texto=texto_historico,
            direcao="sent",
        )
        return {"sucesso": True, "resposta_meta": resposta_meta, "conversa": conversa}
    except HTTPException:
        raise
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Falha de conexão com a API do WhatsApp: {str(e)}")


@app.post("/api/whatsapp/criar-template")
def criar_template_whatsapp(req: CriarTemplateWhatsAppRequest):
    """Cria um novo modelo de mensagem (template) na WABA via Graph API da Meta."""
    cfg = _carregar_config_meta()
    token = cfg.get("access_token", "")
    waba_id = cfg.get("waba_id", "")

    if not token or not waba_id:
        raise HTTPException(
            status_code=400,
            detail="Configure o WABA ID e o Access Token na aba Ajustes (ou no Railway) antes de criar modelos.",
        )

    nome_limpo = "".join(c if (c.isalnum() or c == "_") else "_" for c in req.nome.strip().lower()).strip("_")
    if not nome_limpo:
        raise HTTPException(status_code=400, detail="Nome do modelo inválido.")
    if not req.corpo.strip():
        raise HTTPException(status_code=400, detail="O texto do modelo não pode ficar vazio.")

    url = f"https://graph.facebook.com/v19.0/{waba_id}/message_templates"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "name": nome_limpo,
        "language": (req.idioma or "pt_BR").strip(),
        "category": (req.categoria or "MARKETING").strip().upper(),
        "components": [
            {
                "type": "BODY",
                "text": req.corpo.strip(),
            }
        ],
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        resposta_meta = response.json()

        if response.status_code not in (200, 201):
            erro_msg = resposta_meta.get("error", {}).get("message", "Erro desconhecido ao criar template na Meta")
            raise HTTPException(status_code=400, detail=f"Erro Meta Template: {erro_msg}")

        return {
            "sucesso": True,
            "id_meta": resposta_meta.get("id"),
            "status_meta": resposta_meta.get("status", "PENDING"),
            "categoria_meta": resposta_meta.get("category", req.categoria),
            "resposta_meta": resposta_meta,
        }
    except HTTPException:
        raise
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Falha de conexão com a Graph API da Meta: {str(e)}")


# --- WEBHOOK DA META (WHATSAPP) ---

def _validar_token_webhook(hub_mode: Optional[str], hub_verify_token: Optional[str], hub_challenge: Optional[str]):
    cfg = _carregar_config_meta()
    token_esperado = cfg.get("verify_token") or "nwltech_verify_token"
    if hub_mode == "subscribe" and hub_verify_token == token_esperado:
        return PlainTextResponse(content=hub_challenge or "", status_code=200)
    raise HTTPException(status_code=403, detail="Token de verificação do Webhook inválido.")


async def _processar_evento_webhook(request: Request):
    try:
        payload = await request.json()

        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                contatos_meta = {}
                for c in value.get("contacts", []) or []:
                    wa_id = _normalizar_telefone(c.get("wa_id") or "")
                    nome_perfil = (c.get("profile") or {}).get("name") or ""
                    if wa_id and nome_perfil:
                        contatos_meta[wa_id] = nome_perfil

                for msg in value.get("messages", []) or []:
                    remetente = msg.get("from")
                    tipo_msg = msg.get("type", "text")

                    if tipo_msg == "text":
                        texto_msg = (msg.get("text") or {}).get("body", "")
                    elif tipo_msg == "button":
                        texto_msg = (msg.get("button") or {}).get("text", "[Botão]")
                    elif tipo_msg == "interactive":
                        inter = msg.get("interactive") or {}
                        texto_msg = (
                            (inter.get("button_reply") or {}).get("title")
                            or (inter.get("list_reply") or {}).get("title")
                            or "[Resposta interativa]"
                        )
                    else:
                        texto_msg = f"[{tipo_msg}]"

                    if remetente:
                        tel_norm = _normalizar_telefone(remetente)
                        _registrar_mensagem_conversa(
                            telefone=remetente,
                            texto=texto_msg,
                            direcao="received",
                            nome_contato=contatos_meta.get(tel_norm),
                            abrir_janela_24h=True,
                            incrementar_nao_lidas=True,
                        )
                        print(f"[WHATSAPP CHAT] Mensagem recebida de {remetente}: {texto_msg}")

                for status in value.get("statuses", []) or []:
                    msg_id = status.get("id")
                    estado = status.get("status")
                    print(f"[WHATSAPP STATUS] Mensagem {msg_id} atualizada para: {estado}")

        return {"status": "recebido"}
    except Exception as e:
        print(f"[ERRO WEBHOOK WHATSAPP]: {e}")
        return {"status": "erro", "detalhe": str(e)}


@app.get("/webhook")
def verificar_webhook_raiz(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    return _validar_token_webhook(hub_mode, hub_verify_token, hub_challenge)


@app.post("/webhook")
async def receber_eventos_webhook_raiz(request: Request):
    return await _processar_evento_webhook(request)


@app.get("/api/webhook/whatsapp")
def verificar_webhook_meta(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """Validação inicial exigida pelo painel do desenvolvedor da Meta."""
    return _validar_token_webhook(hub_mode, hub_verify_token, hub_challenge)


@app.post("/api/webhook/whatsapp")
async def receber_eventos_whatsapp(request: Request):
    """Processa mensagens recebidas dos clientes e atualizações de entrega."""
    return await _processar_evento_webhook(request)