import csv
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, Float, Boolean, Text
from sqlalchemy.orm import declarative_base, sessionmaker

# 1. Detecta a pasta raiz onde este código está salvo
BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "leads.csv"

# 2. Carrega as variáveis do arquivo .env local (se existir)
load_dotenv(BASE_DIR / ".env")

# Identifica se está rodando na nuvem (Railway/Heroku definem a variável PORT)
ESTA_NA_NUVEM = bool(os.getenv("PORT") or os.getenv("RAILWAY_ENVIRONMENT"))

CSV_HEADERS = [
    "id",
    "place_id",
    "nome",
    "telefone",
    "whatsapp_link",
    "endereco",
    "cidade",
    "nicho",
    "website",
    "tem_site",
    "avaliacao",
    "total_avaliacoes",
    "status_kanban",
    "observacoes",
    "criado_em",
]


def obter_url_banco_railway() -> str:
    """Monta a string de conexão para MySQL ou PostgreSQL via URL ou campos separados."""
    url_direta = (
        os.getenv("DATABASE_URL")
        or os.getenv("DATABASE_PUBLIC_URL")
        or os.getenv("POSTGRES_URL")
        or os.getenv("MYSQL_URL")
        or os.getenv("MYSQL_PUBLIC_URL")
        or ""
    ).strip()

    if url_direta:
        if url_direta.startswith("postgres://"):
            return url_direta.replace("postgres://", "postgresql://", 1)
        if url_direta.startswith("mysql://"):
            return url_direta.replace("mysql://", "mysql+pymysql://", 1)
        return url_direta

    # Campos separados MySQL (Railway)
    mysql_host = os.getenv("MYSQLHOST", "").strip()
    mysql_user = os.getenv("MYSQLUSER", "").strip()
    mysql_pass = os.getenv("MYSQLPASSWORD", "").strip()
    mysql_db = os.getenv("MYSQLDATABASE", "railway").strip()
    mysql_port = os.getenv("MYSQLPORT", "3306").strip()

    if mysql_host and mysql_user and mysql_pass:
        senha_segura = quote_plus(mysql_pass)
        return f"mysql+pymysql://{mysql_user}:{senha_segura}@{mysql_host}:{mysql_port}/{mysql_db}"

    # Campos separados PostgreSQL (Railway)
    pg_host = os.getenv("PGHOST", "").strip()
    pg_user = os.getenv("PGUSER", "").strip()
    pg_pass = os.getenv("PGPASSWORD", "").strip()
    pg_db = os.getenv("PGDATABASE", "railway").strip()
    pg_port = os.getenv("PGPORT", "5432").strip()

    if pg_host and pg_user and pg_pass:
        senha_segura = quote_plus(pg_pass)
        return f"postgresql://{pg_user}:{senha_segura}@{pg_host}:{pg_port}/{pg_db}"

    return ""


DATABASE_URL = obter_url_banco_railway()

Base = declarative_base()
engine = None
SessionLocal = None

BANCO_CONECTADO = False
TIPO_BANCO_ATIVO = "NENHUM (CSV / Memória)"
ERRO_CONEXAO_BANCO = ""
TABELA_LEADS_CRIADA = False


class LeadModel(Base):
    __tablename__ = "leads"

    id = Column(String(36), primary_key=True, index=True)
    place_id = Column(String(120), unique=True, index=True, nullable=True)
    nome = Column(String(255), nullable=False)
    telefone = Column(String(60), nullable=True, index=True)
    whatsapp_link = Column(String(255), nullable=True)
    endereco = Column(Text, nullable=True)
    cidade = Column(String(120), nullable=True)
    nicho = Column(String(120), nullable=True)
    website = Column(Text, nullable=True)
    tem_site = Column(Boolean, default=False)
    avaliacao = Column(Float, default=0.0)
    total_avaliacoes = Column(String(30), default="0")
    status_kanban = Column(String(40), default="NOVO")
    observacoes = Column(Text, default="")
    criado_em = Column(String(40), default=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def _regravar_csv(leads: List[Dict]):
    if ESTA_NA_NUVEM:
        return  # Na nuvem não mexe com arquivo CSV local
    with open(CSV_PATH, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for lead in leads:
            row = {k: lead.get(k, "") for k in CSV_HEADERS}
            writer.writerow(row)


def sincronizar_banco_para_csv():
    """Espelha os dados do banco para o CSV apenas quando rodando localmente."""
    if ESTA_NA_NUVEM or not SessionLocal:
        return
    try:
        db = SessionLocal()
        registros = db.query(LeadModel).order_by(LeadModel.criado_em.desc()).all()
        db.close()
        leads_nuvem = [{col: getattr(r, col) for col in CSV_HEADERS} for r in registros]
        if leads_nuvem or not CSV_PATH.exists():
            _regravar_csv(leads_nuvem)
    except Exception as e:
        print(f"[AVISO] Falha ao sincronizar banco para CSV local: {e}")


def init_storage():
    """Inicializa o armazenamento e força a criação das tabelas no banco conectado."""
    global engine, SessionLocal, DATABASE_URL
    global BANCO_CONECTADO, TIPO_BANCO_ATIVO, ERRO_CONEXAO_BANCO, TABELA_LEADS_CRIADA

    DATABASE_URL = obter_url_banco_railway()

    if not ESTA_NA_NUVEM and not CSV_PATH.exists():
        with open(CSV_PATH, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()

    if not DATABASE_URL:
        BANCO_CONECTADO = False
        TIPO_BANCO_ATIVO = "NENHUM (Variáveis de banco ausentes)"
        ERRO_CONEXAO_BANCO = "Nenhuma URL ou credencial de MySQL/PostgreSQL encontrada nas variáveis de ambiente."
        TABELA_LEADS_CRIADA = False
        print(f"[AVISO] {ERRO_CONEXAO_BANCO}")
        return

    if engine is None or SessionLocal is None:
        try:
            engine = create_engine(DATABASE_URL, pool_pre_ping=True)
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            Base.metadata.create_all(bind=engine)

            BANCO_CONECTADO = True
            ERRO_CONEXAO_BANCO = ""
            TIPO_BANCO_ATIVO = (
                "MySQL"
                if "mysql" in DATABASE_URL
                else ("PostgreSQL" if "postgres" in DATABASE_URL else "SQL")
            )
            TABELA_LEADS_CRIADA = True

            sincronizar_banco_para_csv()
            print(f"[OK] Conectado ao {TIPO_BANCO_ATIVO} e tabela 'leads' verificada/criada com sucesso!")
        except Exception as e:
            BANCO_CONECTADO = False
            TABELA_LEADS_CRIADA = False
            ERRO_CONEXAO_BANCO = str(e)
            engine = None
            SessionLocal = None
            print(f"[ERRO] Falha ao conectar ou criar tabelas no banco: {e}")


def _ler_csv() -> List[Dict]:
    if ESTA_NA_NUVEM or not CSV_PATH.exists():
        return []
    with open(CSV_PATH, mode="r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        leads = []
        for row in reader:
            row["tem_site"] = str(row.get("tem_site", "")).lower() in ("true", "1", "sim")
            try:
                row["avaliacao"] = float(row.get("avaliacao") or 0.0)
            except ValueError:
                row["avaliacao"] = 0.0
            leads.append(row)
        return leads


def listar_leads(
    status: Optional[str] = None,
    cidade: Optional[str] = None,
    nicho: Optional[str] = None,
    apenas_sem_site: bool = False,
) -> List[Dict]:
    init_storage()

    # Se estiver na nuvem ou com banco ativo, lê direto do Banco de Dados
    if SessionLocal:
        try:
            db = SessionLocal()
            query = db.query(LeadModel)
            if status:
                query = query.filter(LeadModel.status_kanban == status.upper())
            if cidade:
                query = query.filter(LeadModel.cidade.ilike(f"%{cidade}%"))
            if nicho:
                query = query.filter(LeadModel.nicho.ilike(f"%{nicho}%"))
            if apenas_sem_site:
                query = query.filter(LeadModel.tem_site.is_(False))
            registros = query.order_by(LeadModel.criado_em.desc()).all()
            db.close()
            return [{col: getattr(r, col) for col in CSV_HEADERS} for r in registros]
        except Exception as e:
            print(f"[AVISO] Erro ao consultar Banco, tentando CSV local: {e}")

    # Fallback para CSV local (apenas quando rodando no celular/PC sem banco)
    leads = _ler_csv()
    if status:
        leads = [l for l in leads if l.get("status_kanban", "").upper() == status.upper()]
    if cidade:
        leads = [l for l in leads if cidade.lower() in l.get("cidade", "").lower()]
    if nicho:
        leads = [l for l in leads if nicho.lower() in l.get("nicho", "").lower()]
    if apenas_sem_site:
        leads = [l for l in leads if not l.get("tem_site")]
    return leads


def salvar_novos_leads(novos_leads: List[Dict]) -> Dict[str, int]:
    init_storage()
    atuais = listar_leads()

    place_ids_existentes = {l.get("place_id") for l in atuais if l.get("place_id")}
    telefones_existentes = {
        "".join(filter(str.isdigit, str(l.get("telefone", ""))))
        for l in atuais
        if l.get("telefone")
    }

    inseridos = 0
    ignorados = 0
    para_adicionar = []

    for item in novos_leads:
        pid = item.get("place_id", "")
        tel_limpo = "".join(filter(str.isdigit, str(item.get("telefone", ""))))

        if (pid and pid in place_ids_existentes) or (tel_limpo and tel_limpo in telefones_existentes):
            ignorados += 1
            continue

        novo = {
            "id": str(uuid.uuid4()),
            "place_id": pid or f"manual_{uuid.uuid4().hex[:10]}",
            "nome": item.get("nome", "Sem Nome"),
            "telefone": item.get("telefone", ""),
            "whatsapp_link": item.get("whatsapp_link", ""),
            "endereco": item.get("endereco", ""),
            "cidade": item.get("cidade", ""),
            "nicho": item.get("nicho", ""),
            "website": item.get("website", ""),
            "tem_site": bool(item.get("website")),
            "avaliacao": float(item.get("avaliacao") or 0.0),
            "total_avaliacoes": str(item.get("total_avaliacoes") or "0"),
            "status_kanban": item.get("status_kanban", "NOVO"),
            "observacoes": item.get("observacoes", ""),
            "criado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        para_adicionar.append(novo)
        if pid:
            place_ids_existentes.add(pid)
        if tel_limpo:
            telefones_existentes.add(tel_limpo)
        inseridos += 1

    # Salva no CSV local APENAS se estiver rodando localmente
    if para_adicionar and not ESTA_NA_NUVEM and CSV_PATH.exists():
        with open(CSV_PATH, mode="a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            for lead in para_adicionar:
                writer.writerow(lead)

    # Salva no Banco de Dados (Nuvem ou Local conectado ao Railway)
    if SessionLocal and para_adicionar:
        try:
            db = SessionLocal()
            for lead in para_adicionar:
                existe = db.query(LeadModel).filter(LeadModel.place_id == lead["place_id"]).first()
                if not existe:
                    db.add(LeadModel(**lead))
            db.commit()
            db.close()
        except Exception as e:
            print(f"[AVISO] Erro ao salvar no Banco de Dados: {e}")

    return {"inseridos": inseridos, "duplicados_ignorados": ignorados}


def atualizar_lead(
    lead_id: str,
    status_kanban: Optional[str] = None,
    observacoes: Optional[str] = None,
) -> Optional[Dict]:
    init_storage()
    lead_atualizado = None

    if SessionLocal:
        try:
            db = SessionLocal()
            item = db.query(LeadModel).filter(LeadModel.id == lead_id).first()
            if item:
                if status_kanban is not None:
                    item.status_kanban = status_kanban.upper()
                if observacoes is not None:
                    item.observacoes = observacoes
                db.commit()
                db.refresh(item)
                lead_atualizado = {col: getattr(item, col) for col in CSV_HEADERS}
            db.close()
        except Exception as e:
            print(f"[AVISO] Erro ao atualizar no Banco: {e}")

    if not ESTA_NA_NUVEM:
        leads = _ler_csv()
        for lead in leads:
            if lead.get("id") == lead_id:
                if status_kanban is not None:
                    lead["status_kanban"] = status_kanban.upper()
                if observacoes is not None:
                    lead["observacoes"] = observacoes
                if not lead_atualizado:
                    lead_atualizado = lead
                break
        _regravar_csv(leads)

    return lead_atualizado


def deletar_lead(lead_id: str) -> bool:
    init_storage()
    removido = False

    if SessionLocal:
        try:
            db = SessionLocal()
            item = db.query(LeadModel).filter(LeadModel.id == lead_id).first()
            if item:
                db.delete(item)
                db.commit()
                removido = True
            db.close()
        except Exception as e:
            print(f"[AVISO] Erro ao deletar no Banco: {e}")

    if not ESTA_NA_NUVEM:
        leads = _ler_csv()
        novos = [l for l in leads if l.get("id") != lead_id]
        if len(novos) != len(leads):
            _regravar_csv(novos)
            removido = True

    return removido