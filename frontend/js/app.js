// URL padrão do backend
const URL_PADRAO_BACKEND = "https://nwltechcrm-production.up.railway.app";
let API_URL = localStorage.getItem("nwl_backend_url") || URL_PADRAO_BACKEND;

function aplicarUrlNoInput() {
    const inputUrl = document.getElementById("config-backend-url");
    if (inputUrl) {
        inputUrl.value = API_URL;
    }
}

function escaparAspas(valor) {
    return String(valor || "")
        .replace(/\\/g, "\\\\")
        .replace(/'/g, "\\'")
        .replace(/"/g, "&quot;");
}

// Testar conexão ao iniciar
function verificarConexao() {
    aplicarUrlNoInput();
    const dot = document.getElementById("status-dot");
    const text = document.getElementById("status-text");

    if (!dot || !text) return;

    fetch(`${API_URL}/`)
        .then(res => {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res.json();
        })
        .then(data => {
            if (data.status === "online") {
                dot.className = "dot online";
                const conectadoNoBanco = data.banco_railway_conectado ?? data.banco_conectado;
                if (conectadoNoBanco === false) {
                    text.innerText = "Online (Sem Banco)";
                } else {
                    text.innerText = "Online (Railway)";
                }
                carregarLeads();
            } else {
                throw new Error("Status inesperado");
            }
        })
        .catch(() => {
            dot.className = "dot offline";
            text.innerText = "Offline / Erro";
        });
}

function salvarConfiguracoes() {
    const inputUrl = document.getElementById("config-backend-url");
    if (!inputUrl) return;

    let url = inputUrl.value.trim();
    if (!url) {
        url = URL_PADRAO_BACKEND;
    }
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
        url = "https://" + url;
    }
    API_URL = url.endsWith("/") ? url.slice(0, -1) : url;
    localStorage.setItem("nwl_backend_url", API_URL);
    inputUrl.value = API_URL;
    alert("URL salva com sucesso!");
    verificarConexao();
}

// Troca de Abas
function mudarAba(abaId, elemento) {
    document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
    document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("active"));

    const abaAlvo = document.getElementById(`tab-${abaId}`);
    if (abaAlvo) abaAlvo.classList.add("active");
    if (elemento) elemento.classList.add("active");

    if (abaId === "kanban") {
        carregarLeads();
    }
}

// Buscador
function executarBusca() {
    const nichoInput = document.getElementById("busca-nicho");
    const cidadeInput = document.getElementById("busca-cidade");
    const raioInput = document.getElementById("busca-raio");
    const maxInput = document.getElementById("busca-max");
    const semSiteInput = document.getElementById("busca-sem-site");

    const nicho = nichoInput ? nichoInput.value.trim() : "";
    const cidade = cidadeInput ? cidadeInput.value.trim() : "";
    const raio_km = raioInput ? raioInput.value : 15;
    const max_resultados = maxInput ? maxInput.value : 20;
    const apenas_sem_site = semSiteInput ? Boolean(semSiteInput.checked) : false;

    if (!nicho || !cidade) {
        alert("Preencha o nicho e a cidade.");
        return;
    }

    const box = document.getElementById("busca-resultado-box");
    const msg = document.getElementById("busca-status-msg");
    if (box) box.classList.remove("hidden");
    if (msg) msg.innerText = "Minerando leads... Aguarde.";

    fetch(`${API_URL}/api/buscar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            nicho,
            cidade,
            raio_km: parseInt(raio_km, 10) || 15,
            max_resultados: parseInt(max_resultados, 10) || 20,
            apenas_sem_site
        })
    })
    .then(async res => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            throw new Error(data.detail || `Erro HTTP ${res.status}`);
        }
        return data;
    })
    .then(data => {
        if (data.sucesso) {
            if (msg) {
                msg.innerText = `Busca concluída! ${data.novos_salvos} novos leads salvos (${data.duplicados_ignorados || 0} já existiam).`;
            }

            if (Array.isArray(data.leads) && data.leads.length > 0) {
                renderizarKanban(data.leads);
            } else {
                carregarLeads();
            }
        } else if (msg) {
            msg.innerText = "Erro na busca: " + (data.detail || "Desconhecido");
        }
    })
    .catch(err => {
        if (msg) msg.innerText = "Erro na busca: " + (err.message || "Falha de conexão com o servidor.");
        console.error(err);
    });
}

// Buscar leads do backend e atualizar Kanban
function carregarLeads() {
    fetch(`${API_URL}/api/leads`)
        .then(async res => {
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || `Erro HTTP ${res.status}`);
            return data;
        })
        .then(data => {
            const leads = Array.isArray(data.leads) ? data.leads : [];
            renderizarKanban(leads);
        })
        .catch(err => console.error("Erro ao carregar leads:", err));
}

// Desenhar os cards nas colunas do Kanban
function renderizarKanban(leads) {
    const colunas = {
        "NOVO": document.getElementById("list-novo"),
        "PENDENTE": document.getElementById("list-pendente"),
        "CONTATO": document.getElementById("list-contato"),
        "FECHADO": document.getElementById("list-fechado")
    };

    const contadores = { "NOVO": 0, "PENDENTE": 0, "CONTATO": 0, "FECHADO": 0 };

    Object.values(colunas).forEach(col => {
        if (col) col.innerHTML = "";
    });

    (leads || []).forEach(lead => {
        let status = (lead.status_kanban || "NOVO").toUpperCase().trim();
        if (!colunas[status]) {
            status = "NOVO";
        }

        contadores[status]++;
        const leadIdSeguro = escaparAspas(lead.id || lead.place_id || "");
        const nomeSeguro = escaparAspas(lead.nome || "Sem Nome");
        const cidadeSegura = escaparAspas(lead.cidade || "");
        const nichoSeguro = escaparAspas(lead.nicho || "");
        const telefoneSeguro = escaparAspas(lead.telefone || "");
        const whatsappSeguro = escaparAspas(lead.whatsapp_link || "");

        const card = document.createElement("div");
        card.className = "lead-card";
        card.innerHTML = `
            <div class="lead-name">${nomeSeguro}</div>
            <div class="lead-info">
                ${cidadeSegura} ${nichoSeguro ? "• " + nichoSeguro : ""}<br>
                ${telefoneSeguro
                    ? `<span style="color: var(--accent-green);"><i class="fa-solid fa-phone"></i> ${telefoneSeguro}</span>`
                    : '<span style="opacity:0.6;">Sem telefone cadastrado</span>'}
            </div>
            <div class="lead-actions">
                ${whatsappSeguro
                    ? `<a href="${whatsappSeguro}" target="_blank" rel="noopener noreferrer" class="btn-whatsapp" style="padding:4px 8px; text-decoration:none; border-radius:4px; font-size:0.75rem;"><i class="fa-brands fa-whatsapp"></i></a>`
                    : ""}
                ${status !== "PENDENTE" ? `<button class="btn-sm" onclick="mudarStatusLead('${leadIdSeguro}', 'PENDENTE')">Pend.</button>` : ""}
                ${status !== "CONTATO" ? `<button class="btn-sm" onclick="mudarStatusLead('${leadIdSeguro}', 'CONTATO')">Contato</button>` : ""}
                ${status !== "FECHADO" ? `<button class="btn-sm" onclick="mudarStatusLead('${leadIdSeguro}', 'FECHADO')">Fechado</button>` : ""}
            </div>
        `;

        if (colunas[status]) {
            colunas[status].appendChild(card);
        }
    });

    const cNovo = document.getElementById("count-novo");
    const cPend = document.getElementById("count-pendente");
    const cCont = document.getElementById("count-contato");
    const cFech = document.getElementById("count-fechado");

    if (cNovo) cNovo.innerText = contadores["NOVO"];
    if (cPend) cPend.innerText = contadores["PENDENTE"];
    if (cCont) cCont.innerText = contadores["CONTATO"];
    if (cFech) cFech.innerText = contadores["FECHADO"];
}

function mudarStatusLead(leadId, novoStatus) {
    if (!leadId) return;

    fetch(`${API_URL}/api/leads/${encodeURIComponent(leadId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status_kanban: novoStatus })
    })
    .then(async res => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `Erro HTTP ${res.status}`);
        return data;
    })
    .then(() => carregarLeads())
    .catch(err => console.error("Erro ao atualizar status:", err));
}

// Enviar Mensagem WhatsApp API
function enviarMensagemWhatsApp() {
    const telInput = document.getElementById("chat-telefone");
    const msgInput = document.getElementById("chat-mensagem");

    const telefone = telInput ? telInput.value.trim() : "";
    const mensagem = msgInput ? msgInput.value.trim() : "";

    if (!telefone || !mensagem) {
        alert("Preencha o telefone e a mensagem.");
        return;
    }

    fetch(`${API_URL}/api/whatsapp/enviar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ telefone, mensagem })
    })
    .then(async res => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            throw new Error(data.detail || "Erro na Meta");
        }
        return data;
    })
    .then(data => {
        if (data.sucesso) {
            alert("Mensagem enviada com sucesso pela API do WhatsApp!");
            if (msgInput) msgInput.value = "";
        } else {
            alert("Erro ao enviar: " + (data.detail || "Erro na Meta"));
        }
    })
    .catch(err => alert("Erro ao disparar mensagem: " + (err.message || "Falha de conexão.")));
}

function iniciarEmbeddedSignup() {
    alert("Fluxo de Cadastro Incorporado da Meta pronto para ser ativado via SDK oficial.");
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", verificarConexao);
} else {
    verificarConexao();
}
