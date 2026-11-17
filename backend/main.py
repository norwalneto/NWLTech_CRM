import os
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
    version="1.0.0",
    description="Backend híbrido (CSV Raiz + Railway DB) para Mobile CRM e Buscador de Leads",
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


@app.get("/")
def health_check():
    return {
        "status": "online",
        "servico": "NWL Tech CRM Backend",
        "pasta_raiz_detectada": str(BASE_DIR),
        "arquivo_csv": str(CSV_PATH),
        "banco_railway_conectado": bool(DATABASE_URL),
        "google_api_configurada": bool(os.getenv("GOOGLE_MAPS_API_KEY")),
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


@app.get("/api/webhook/whatsapp")
def verificar_webhook_meta(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    token_esperado = os.getenv("WHATSAPP_VERIFY_TOKEN", "nwltech_verify_token")
    if hub_mode == "subscribe" and hub_verify_token == token_esperado:
        return PlainTextResponse(content=hub_challenge or "", status_code=200)
    raise HTTPException(status_code=403, detail="Token de verificação inválido.")


@app.post("/api/webhook/whatsapp")
async def receber_eventos_whatsapp(request: Request):
    payload = await request.json()
    return {"status": "recebido", "eventos": len(payload.get("entry", []))}