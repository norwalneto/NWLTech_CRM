// URL padrão do backend
const URL_PADRAO_BACKEND = "https://nwltechcrm-production.up.railway.app";
let API_URL = localStorage.getItem("nwl_backend_url") || URL_PADRAO_BACKEND;
let LEADS_CACHE = [];

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

function escaparHtml(valor) {
    return String(valor || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
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

    if (abaId === "kanban" || abaId === "clientes") {
        carregarLeads();
    }
}

// Buscador (Estado + Cidade opcional)
function executarBusca() {
    const nichoInput = document.getElementById("busca-nicho");
    const estadoInput = document.getElementById("busca-estado");
    const cidadeInput = document.getElementById("busca-cidade");
    const raioInput = document.getElementById("busca-raio");
    const maxInput = document.getElementById("busca-max");
    const semSiteInput = document.getElementById("busca-sem-site");

    const nicho = nichoInput ? nichoInput.value.trim() : "";
    const estado = estadoInput ? estadoInput.value.trim() : "";
    const cidade = cidadeInput ? cidadeInput.value.trim() : "";
    const raio_km = raioInput ? raioInput.value : 15;
    const max_resultados = maxInput ? maxInput.value : 20;
    const apenas_sem_site = semSiteInput ? Boolean(semSiteInput.checked) : false;

    if (!nicho) {
        alert("Preencha o nicho ou palavra-chave.");
        return;
    }
    if (!cidade && !estado) {
        alert("Informe pelo menos a cidade ou o estado.");
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
            estado,
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
                LEADS_CACHE = data.leads;
                renderizarKanban(LEADS_CACHE);
                renderizarClientes(LEADS_CACHE);
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

// Buscar leads do backend e atualizar Kanban + Clientes
function carregarLeads() {
    fetch(`${API_URL}/api/leads`)
        .then(async res => {
            const data = await res.json().catch(() => ({}));
            if (!res.ok) throw new Error(data.detail || `Erro HTTP ${res.status}`);
            return data;
        })
        .then(data => {
            const leads = Array.isArray(data.leads) ? data.leads : [];
            LEADS_CACHE = leads;
            renderizarKanban(leads);
            renderizarClientes(leads);
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
        const nomeSeguro = escaparHtml(lead.nome || "Sem Nome");
        const cidadeSegura = escaparHtml(lead.cidade || "");
        const nichoSeguro = escaparHtml(lead.nicho || "");
        const telefoneSeguro = escaparHtml(lead.telefone || "");
        const whatsappSeguro = escaparHtml(lead.whatsapp_link || "");

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
                <button class="btn-sm" onclick="abrirModalEditarLead('${leadIdSeguro}')">Editar</button>
                <button class="btn-sm" onclick="excluirLead('${leadIdSeguro}')">Excluir</button>
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

// Desenhar lista completa na aba Clientes com filtros
function renderizarClientes(leads = LEADS_CACHE) {
    const lista = document.getElementById("lista-clientes");
    if (!lista) return;

    const termo = (document.getElementById("filtro-cliente-texto")?.value || "").toLowerCase().trim();
    const statusFiltro = (document.getElementById("filtro-cliente-status")?.value || "").toUpperCase().trim();
    const apenasComZap = Boolean(document.getElementById("filtro-cliente-whatsapp")?.checked);

    const filtrados = (leads || []).filter(lead => {
        const nome = (lead.nome || "").toLowerCase();
        const tel = (lead.telefone || "").toLowerCase();
        const cid = (lead.cidade || "").toLowerCase();
        const nicho = (lead.nicho || "").toLowerCase();
        const st = (lead.status_kanban || "NOVO").toUpperCase().trim();
        const temZap = Boolean((lead.whatsapp_link || "").trim() || (lead.telefone || "").trim());

        const bateTexto = !termo || nome.includes(termo) || tel.includes(termo) || cid.includes(termo) || nicho.includes(termo);
        const bateStatus = !statusFiltro || st === statusFiltro;
        const bateZap = !apenasComZap || temZap;

        return bateTexto && bateStatus && bateZap;
    });

    if (!filtrados.length) {
        lista.innerHTML = `<div class="lead-card"><div class="lead-info">Nenhum cliente encontrado com os filtros aplicados.</div></div>`;
        return;
    }

    lista.innerHTML = filtrados.map(lead => {
        const idSeguro = escaparAspas(lead.id || lead.place_id || "");
        const nome = escaparHtml(lead.nome || "Sem Nome");
        const telefone = escaparHtml(lead.telefone || "Sem telefone");
        const cidade = escaparHtml(lead.cidade || "-");
        const nicho = escaparHtml(lead.nicho || "-");
        const status = escaparHtml(lead.status_kanban || "NOVO");
        const obs = escaparHtml(lead.observacoes || "");
        const zap = escaparHtml(lead.whatsapp_link || "");
        const site = escaparHtml(lead.website || "");

        return `
            <div class="lead-card">
                <div class="lead-name">${nome} <span style="font-size:0.75rem; opacity:0.8;">[${status}]</span></div>
                <div class="lead-info">
                    📞 ${telefone} • 📍 ${cidade}<br>
                    🏷️ ${nicho} ${site ? `• <a href="${site}" target="_blank" rel="noopener noreferrer">Site</a>` : "• Sem site"}
                    ${obs ? `<br>📝 ${obs}` : ""}
                </div>
                <div class="lead-actions">
                    ${zap ? `<a href="${zap}" target="_blank" rel="noopener noreferrer" class="btn-whatsapp" style="padding:4px 8px; text-decoration:none; border-radius:4px; font-size:0.75rem;">WhatsApp</a>` : ""}
                    <button class="btn-sm" onclick="abrirModalEditarLead('${idSeguro}')">Editar</button>
                    <button class="btn-sm" onclick="excluirLead('${idSeguro}')">Excluir</button>
                </div>
            </div>
        `;
    }).join("");
}

function abrirModalEditarLead(leadId) {
    const lead = (LEADS_CACHE || []).find(item => String(item.id || item.place_id) === String(leadId));
    if (!lead) return;

    const idInput = document.getElementById("edit-lead-id");
    const nomeInput = document.getElementById("edit-lead-nome");
    const telInput = document.getElementById("edit-lead-telefone");
    const cidInput = document.getElementById("edit-lead-cidade");
    const statusSelect = document.getElementById("edit-lead-status");
    const obsInput = document.getElementById("edit-lead-obs");
    const modal = document.getElementById("modal-editar-lead");

    if (idInput) idInput.value = lead.id ?? lead.place_id ?? "";
    if (nomeInput) nomeInput.value = lead.nome || "";
    if (telInput) telInput.value = lead.telefone || "";
    if (cidInput) cidInput.value = lead.cidade || "";
    if (statusSelect) statusSelect.value = (lead.status_kanban || "NOVO").toUpperCase();
    if (obsInput) obsInput.value = lead.observacoes || "";
    if (modal) modal.classList.remove("hidden");
}

function fecharModalEditarLead() {
    const modal = document.getElementById("modal-editar-lead");
    if (modal) modal.classList.add("hidden");
}

function salvarEdicaoLead() {
    const leadId = document.getElementById("edit-lead-id")?.value;
    if (!leadId) return;

    const payload = {
        nome: document.getElementById("edit-lead-nome")?.value.trim() || "",
        telefone: document.getElementById("edit-lead-telefone")?.value.trim() || "",
        cidade: document.getElementById("edit-lead-cidade")?.value.trim() || "",
        status_kanban: document.getElementById("edit-lead-status")?.value || "NOVO",
        observacoes: document.getElementById("edit-lead-obs")?.value.trim() || ""
    };

    fetch(`${API_URL}/api/leads/${encodeURIComponent(leadId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    })
    .then(async res => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `Erro HTTP ${res.status}`);
        return data;
    })
    .then(() => {
        fecharModalEditarLead();
        carregarLeads();
    })
    .catch(err => alert("Erro ao salvar edição: " + (err.message || "Falha de conexão.")));
}

function excluirLead(leadId) {
    if (!leadId) return;
    if (!confirm("Deseja realmente excluir este cliente?")) return;

    fetch(`${API_URL}/api/leads/${encodeURIComponent(leadId)}`, {
        method: "DELETE"
    })
    .then(async res => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `Erro HTTP ${res.status}`);
        return data;
    })
    .then(() => carregarLeads())
    .catch(err => alert("Erro ao excluir cliente: " + (err.message || "Falha de conexão.")));
}

function limparLeadsSemTelefone() {
    if (!confirm("Excluir todos os clientes que estão sem telefone?")) return;

    fetch(`${API_URL}/api/leads/limpar-sem-telefone`, {
        method: "DELETE"
    })
    .then(async res => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || `Erro HTTP ${res.status}`);
        return data;
    })
    .then(data => {
        alert(`${data.removidos ?? 0} clientes sem telefone removidos.`);
        carregarLeads();
    })
    .catch(err => alert("Erro ao limpar sem telefone: " + (err.message || "Falha de conexão.")));
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