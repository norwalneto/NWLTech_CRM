import os
import requests
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from database import (
    BASE_DIR,
    CSV_PATH,
    DATABASE_URL,
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

app = FastAPI(
    title="NWL Tech CRM & Buscador API",
    version="1.1.0",
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
    cidade: str
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
    status_kanban: Optional[str] = None
    observacoes: Optional[str] = None


class EnviarMensagemWhatsAppRequest(BaseModel):
    telefone: str
    mensagem: str


@app.get("/")
def health_check():
    return {
        "status": "online",
        "servico": "NWL Tech CRM Backend",
        "pasta_raiz_detectada": str(BASE_DIR),
        "arquivo_csv": str(CSV_PATH),
        "banco_railway_conectado": bool(DATABASE_URL),
        "google_api_configurada": bool(os.getenv("GOOGLE_MAPS_API_KEY")),
        "whatsapp_api_configurada": bool(os.getenv("WHATSAPP_ACCESS_TOKEN") and os.getenv("WHATSAPP_PHONE_NUMBER_ID")),
    }


@app.post("/api/buscar")
def iniciar_buscador(req: BuscaRequest):
    if not req.nicho.strip() or not req.cidade.strip():
        raise HTTPException(status_code=400, detail="Informe a palavra-chave (nicho) e a cidade.")

    try:
        resultado_busca = executar_busca_google_maps(
            nicho=req.nicho,
            cidade=req.cidade,
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


@app.patch("/api/leads/{lead_id}")
def editar_lead_kanban(lead_id: str, body: AtualizarLeadRequest):
    atualizado = atualizar_lead(
        lead_id=lead_id,
        status_kanban=body.status_kanban,
        observacoes=body.observacoes,
    )
    if not atualizado:
        raise HTTPException(status_code=404, detail="Lead não encontrado.")
    return {"sucesso": True, "lead": atualizado}


@app.delete("/api/leads/{lead_id}")
def excluir_lead(lead_id: str):
    removido = deletar_lead(lead_id)
    if not removido:
        raise HTTPException(status_code=404, detail="Lead não encontrado.")
    return {"sucesso": True}


@app.get("/api/leads/exportar/csv")
def baixar_csv():
    init_storage()
    sincronizar_banco_para_csv()
    return FileResponse(
        path=CSV_PATH,
        media_type="text/csv",
        filename="leads.csv",
    )


# --- WHATSAPP CLOUD API: ENVIO DE MENSAGENS ---

@app.post("/api/whatsapp/enviar")
def enviar_mensagem_whatsapp(req: EnviarMensagemWhatsAppRequest):
    """Dispara mensagens oficiais através da WhatsApp Business Platform (Cloud API)."""
    token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()

    if not token or not phone_number_id:
        raise HTTPException(
            status_code=400,
            detail="Credenciais do WhatsApp (WHATSAPP_ACCESS_TOKEN ou PHONE_NUMBER_ID) não configuradas no ambiente."
        )

    # Limpa o telefone para conter apenas números com DDI (ex: 5581999999999)
    telefone_limpo = "".join(filter(str.isdigit, req.telefone))
    if not telefone_limpo.startswith("55") and len(telefone_limpo) in (10, 11):
        telefone_limpo = f"55{telefone_limpo}"

    url = f"https://graph.facebook.com/v17.0/{phone_number_id}/messages"
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

        if response.status_code != 200:
            erro_msg = resposta_meta.get("error", {}).get("message", "Erro desconhecido na API da Meta")
            raise HTTPException(status_code=400, detail=f"Erro Meta WhatsApp: {erro_msg}")

        return {"sucesso": True, "resposta_meta": resposta_meta}
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Falha de conexão com a API do WhatsApp: {str(e)}")


# --- WEBHOOK DA META (WHATSAPP) ---

@app.get("/api/webhook/whatsapp")
def verificar_webhook_meta(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """Validação inicial exigida pelo painel do desenvolvedor da Meta."""
    token_esperado = os.getenv("WHATSAPP_VERIFY_TOKEN", "nwltech_verify_token")
    if hub_mode == "subscribe" and hub_verify_token == token_esperado:
        return PlainTextResponse(content=hub_challenge or "", status_code=200)
    raise HTTPException(status_code=403, detail="Token de verificação do Webhook inválido.")


@app.post("/api/webhook/whatsapp")
async def receber_eventos_whatsapp(request: Request):
    """Processa mensagens recebidas dos clientes e atualizações de entrega."""
    try:
        payload = await request.json()
        
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                
                # 1. Mensagens recebidas dos clientes
                messages = value.get("messages", [])
                if messages:
                    for msg in messages:
                        remetente = msg.get("from")
                        texto_msg = msg.get("text", {}).get("body", "")
                        print(f"[WHATSAPP CHAT] Mensagem recebida de {remetente}: {texto_msg}")
                
                # 2. Status de entrega (enviado, entregue, lido)
                statuses = value.get("statuses", [])
                if statuses:
                    for status in statuses:
                        msg_id = status.get("id")
                        estado = status.get("status") # sent, delivered, read
                        print(f"[WHATSAPP STATUS] Mensagem {msg_id} atualizada para: {estado}")

        return {"status": "recebido"}
    except Exception as e:
        print(f"[ERRO WEBHOOK WHATSAPP]: {e}")
        return {"status": "erro", "detalhe": str(e)}