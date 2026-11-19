// URL padrão do backend
const URL_PADRAO_BACKEND = "https://nwltechcrm-production.up.railway.app";
let API_URL = localStorage.getItem("nwl_backend_url") || URL_PADRAO_BACKEND;
let LEADS_CACHE = [];

// Estado do WhatsApp (Conversas & Envios)
let WA_CONVERSAS = JSON.parse(localStorage.getItem("nwl_wa_conversas") || "[]");
let WA_FILTRO_ATUAL = "TODOS";
let WA_CONVERSA_ATIVA_ID = null;

const WA_TEMPLATES_INFO = {
    hello_world: {
        label: "hello_world",
        lang: "en_US",
        preview: "Hello World — Welcome and congratulations! This message demonstrates template delivery."
    },
    apresentacao_nwl: {
        label: "apresentacao_nwl",
        lang: "pt_BR",
        preview: "Olá! Aqui é da NWL Tech. Ajudamos empresas a crescer com sites, sistemas, redes e segurança."
    },
    proposta_site: {
        label: "proposta_site",
        lang: "pt_BR",
        preview: "Olá! Notamos que sua empresa pode ganhar mais clientes com presença digital profissional. Posso te mostrar?"
    }
};

function aplicarUrlNoInput() {
    const inputUrl = document.getElementById("config-backend-url");
    if (inputUrl) {
        inputUrl.value = API_URL;
    }
    atualizarUrlWebhookNaTela();
    carregarConfiguracoesMetaSalvas();
}

function atualizarUrlWebhookNaTela() {
    const webhookInput = document.getElementById("config-webhook-url");
    if (webhookInput) {
        webhookInput.value = `${API_URL}/webhook`;
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

function normalizarTelefone(tel) {
    return String(tel || "").replace(/\D/g, "");
}

function obterIniciais(nome) {
    const partes = String(nome || "CL").trim().split(/\s+/);
    if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
    return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
}

function formatarHoraAtual() {
    const agora = new Date();
    return agora.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function salvarConversasLocalmente() {
    localStorage.setItem("nwl_wa_conversas", JSON.stringify(WA_CONVERSAS));
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
                carregarConversasWhatsApp();
            } else {
                throw new Error("Status inesperado");
            }
        })
        .catch(() => {
            dot.className = "dot offline";
            text.innerText = "Offline / Erro";
            renderizarConversasWhatsApp();
            atualizarPreviewTemplateChat();
            alternarTipoEnvio();
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
    atualizarUrlWebhookNaTela();
    alert("URL salva com sucesso!");
    verificarConexao();
}

function carregarConfiguracoesMetaSalvas() {
    const salvo = JSON.parse(localStorage.getItem("nwl_meta_config") || "{}");
    const verifyEl = document.getElementById("config-verify-token");
    const phoneIdEl = document.getElementById("config-phone-number-id");
    const wabaIdEl = document.getElementById("config-waba-id");
    const tokenEl = document.getElementById("config-access-token");

    if (verifyEl && salvo.verify_token) verifyEl.value = salvo.verify_token;
    if (phoneIdEl && salvo.phone_number_id) phoneIdEl.value = salvo.phone_number_id;
    if (wabaIdEl && salvo.waba_id) wabaIdEl.value = salvo.waba_id;
    if (tokenEl && salvo.access_token) tokenEl.value = salvo.access_token;
}

function salvarConfiguracoesMeta() {
    const payload = {
        verify_token: document.getElementById("config-verify-token")?.value.trim() || "",
        phone_number_id: document.getElementById("config-phone-number-id")?.value.trim() || "",
        waba_id: document.getElementById("config-waba-id")?.value.trim() || "",
        access_token: document.getElementById("config-access-token")?.value.trim() || ""
    };

    localStorage.setItem("nwl_meta_config", JSON.stringify(payload));

    fetch(`${API_URL}/api/whatsapp/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    })
    .then(async res => {
        if (res.ok) return res.json().catch(() => ({}));
        return null;
    })
    .then(() => {
        alert("Configurações da Meta salvas com sucesso!");
    })
    .catch(() => {
        alert("Configurações salvas localmente no navegador!");
    });
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
    } else if (abaId === "chat") {
        popularSelectClientesEnvio();
        carregarConversasWhatsApp();
    } else if (abaId === "config") {
        aplicarUrlNoInput();
    }
}

// Buscador (Estado + Cidade opcional)
function executarBusca() {
    const nichoInput = document.getElementById("busca-nicho");
    const estadoInput = document.getElementById("busca-estado");
    const cidadeInput = document.getElementById("busca-cidade");
    const maxInput = document.getElementById("busca-max");
    const semSiteInput = document.getElementById("busca-sem-site");

    const nicho = nichoInput ? nichoInput.value.trim() : "";
    const estado = estadoInput ? estadoInput.value.trim() : "";
    const cidade = cidadeInput ? cidadeInput.value.trim() : "";
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
                popularSelectClientesEnvio();
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
            popularSelectClientesEnvio();
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

// ==========================================
// WHATSAPP: CONVERSAS, FILTROS & ENVIOS
// ==========================================

function mudarSubAbaWhatsApp(subAba, botaoEl) {
    document.querySelectorAll(".wa-subnav-btn").forEach(btn => btn.classList.remove("active"));
    if (botaoEl) botaoEl.classList.add("active");

    const viewConversas = document.getElementById("wa-view-conversas");
    const viewEnvios = document.getElementById("wa-view-envios");

    if (subAba === "envios") {
        viewConversas?.classList.remove("active");
        viewConversas?.classList.add("hidden");
        viewEnvios?.classList.remove("hidden");
        viewEnvios?.classList.add("active");
        popularSelectClientesEnvio();
        alternarTipoEnvio();
    } else {
        viewEnvios?.classList.remove("active");
        viewEnvios?.classList.add("hidden");
        viewConversas?.classList.remove("hidden");
        viewConversas?.classList.add("active");
        renderizarConversasWhatsApp();
    }
}

function selecionarFiltroConversa(filtro, pillEl) {
    WA_FILTRO_ATUAL = filtro;
    document.querySelectorAll(".wa-pill").forEach(p => p.classList.remove("active"));
    if (pillEl) pillEl.classList.add("active");
    renderizarConversasWhatsApp();
}

function carregarConversasWhatsApp() {
    fetch(`${API_URL}/api/whatsapp/conversas`)
        .then(async res => {
            if (!res.ok) throw new Error("Endpoint não disponível");
            return res.json();
        })
        .then(data => {
            if (Array.isArray(data.conversas)) {
                WA_CONVERSAS = data.conversas;
                salvarConversasLocalmente();
            }
            renderizarConversasWhatsApp();
            if (WA_CONVERSA_ATIVA_ID) {
                renderizarMensagensConversaAtiva();
            }
        })
        .catch(() => {
            renderizarConversasWhatsApp();
            if (WA_CONVERSA_ATIVA_ID) {
                renderizarMensagensConversaAtiva();
            }
        });
}

function garantirConversa(nome, telefone) {
    const telLimpo = normalizarTelefone(telefone);
    const nomeFinal = (nome || "").trim() || telLimpo || "Cliente";

    let conversa = WA_CONVERSAS.find(c => normalizarTelefone(c.telefone) === telLimpo);
    if (!conversa) {
        conversa = {
            id: telLimpo || String(Date.now()),
            nome: nomeFinal,
            telefone: telefone || telLimpo,
            ultima_mensagem: "Conversa iniciada",
            hora: formatarHoraAtual(),
            nao_lidas: 0,
            janela_24h: false,
            mensagens: []
        };
        WA_CONVERSAS.unshift(conversa);
        salvarConversasLocalmente();
    }
    return conversa;
}

function renderizarConversasWhatsApp() {
    const container = document.getElementById("wa-lista-conversas");
    if (!container) return;

    const termo = (document.getElementById("wa-filtro-busca")?.value || "").toLowerCase().trim();

    const filtradas = (WA_CONVERSAS || []).filter(conv => {
        const nome = (conv.nome || "").toLowerCase();
        const tel = (conv.telefone || "").toLowerCase();
        const ultima = (conv.ultima_mensagem || "").toLowerCase();

        const bateTexto = !termo || nome.includes(termo) || tel.includes(termo) || ultima.includes(termo);
        if (!bateTexto) return false;

        if (WA_FILTRO_ATUAL === "NAO_LIDAS") return (conv.nao_lidas || 0) > 0;
        if (WA_FILTRO_ATUAL === "JANELA_24H") return Boolean(conv.janela_24h);
        if (WA_FILTRO_ATUAL === "AGUARDANDO") {
            const msgs = conv.mensagens || [];
            const ultimaMsg = msgs[msgs.length - 1];
            return ultimaMsg && ultimaMsg.direcao === "sent";
        }
        return true;
    });

    if (!filtradas.length) {
        container.innerHTML = `
            <div class="lead-card">
                <div class="lead-info">
                    Nenhuma conversa encontrada. Clique em <strong>+ Nova Conversa</strong> para selecionar um cliente e iniciar o contato.
                </div>
            </div>
        `;
        return;
    }

    container.innerHTML = filtradas.map(conv => {
        const idSeguro = escaparAspas(conv.id);
        const iniciais = escaparHtml(obterIniciais(conv.nome));
        const nome = escaparHtml(conv.nome || conv.telefone || "Contato");
        const ultima = escaparHtml(conv.ultima_mensagem || "Sem mensagens");
        const hora = escaparHtml(conv.hora || "");
        const naoLidas = Number(conv.nao_lidas || 0);

        return `
            <div class="wa-chat-item" onclick="abrirConversaWhatsApp('${idSeguro}')">
                <div class="wa-avatar">${iniciais}</div>
                <div class="wa-chat-main">
                    <div class="wa-chat-top">
                        <span class="wa-chat-name">${nome}</span>
                        <span class="wa-chat-time">${hora}</span>
                    </div>
                    <div class="wa-chat-bottom">
                        <span class="wa-chat-preview">${ultima}</span>
                        ${naoLidas > 0 ? `<span class="wa-unread-badge">${naoLidas}</span>` : ""}
                    </div>
                </div>
            </div>
        `;
    }).join("");
}

function abrirConversaWhatsApp(conversaId) {
    const conv = WA_CONVERSAS.find(c => String(c.id) === String(conversaId));
    if (!conv) return;

    WA_CONVERSA_ATIVA_ID = conv.id;
    conv.nao_lidas = 0;
    salvarConversasLocalmente();
    renderizarConversasWhatsApp();

    document.getElementById("wa-lista-view")?.classList.add("hidden");
    document.getElementById("wa-thread-view")?.classList.remove("hidden");

    const nomeEl = document.getElementById("wa-chat-contato-nome");
    const infoEl = document.getElementById("wa-chat-contato-info");
    const badgeEl = document.getElementById("wa-janela-badge");

    if (nomeEl) nomeEl.innerText = conv.nome || conv.telefone;
    if (infoEl) infoEl.innerText = `${conv.telefone} • ${conv.janela_24h ? "Janela 24h ativa" : "Use modelo para iniciar"}`;

    if (badgeEl) {
        if (conv.janela_24h) {
            badgeEl.innerText = "24h Ativa";
            badgeEl.classList.remove("expired");
        } else {
            badgeEl.innerText = "Fora 24h / Modelo";
            badgeEl.classList.add("expired");
        }
    }

    atualizarPreviewTemplateChat();
    renderizarMensagensConversaAtiva();
}

function voltarParaListaConversas() {
    WA_CONVERSA_ATIVA_ID = null;
    document.getElementById("wa-templates-drawer")?.classList.add("hidden");
    document.getElementById("wa-thread-view")?.classList.add("hidden");
    document.getElementById("wa-lista-view")?.classList.remove("hidden");
    renderizarConversasWhatsApp();
}

function renderizarMensagensConversaAtiva() {
    const box = document.getElementById("wa-mensagens-box");
    if (!box || !WA_CONVERSA_ATIVA_ID) return;

    const conv = WA_CONVERSAS.find(c => String(c.id) === String(WA_CONVERSA_ATIVA_ID));
    if (!conv) return;

    const msgs = conv.mensagens || [];
    if (!msgs.length) {
        box.innerHTML = `
            <div class="lead-info" style="text-align:center; margin:auto; padding:16px;">
                Nenhuma mensagem ainda.<br>
                Envie um <strong>Modelo (ícone de documento)</strong> para iniciar a conversa ou digite abaixo.
            </div>
        `;
        return;
    }

    box.innerHTML = msgs.map(m => {
        const direcao = m.direcao === "received" ? "received" : "sent";
        const texto = escaparHtml(m.texto || "");
        const hora = escaparHtml(m.hora || "");
        const checkIcon = direcao === "sent" ? `<i class="fa-solid fa-check-double"></i>` : "";

        return `
            <div class="wa-bubble ${direcao}">
                <div>${texto}</div>
                <div class="wa-bubble-meta">
                    <span>${hora}</span>
                    ${checkIcon}
                </div>
            </div>
        `;
    }).join("");

    box.scrollTop = box.scrollHeight;
}

function alternarGavetaTemplates() {
    const drawer = document.getElementById("wa-templates-drawer");
    if (!drawer) return;
    drawer.classList.toggle("hidden");
    atualizarPreviewTemplateChat();
}

function atualizarPreviewTemplateChat() {
    const selectEl = document.getElementById("wa-chat-template-select");
    const previewEl = document.getElementById("wa-chat-template-preview");
    if (!selectEl || !previewEl) return;

    const info = WA_TEMPLATES_INFO[selectEl.value];
    previewEl.innerText = info ? info.preview : "";
}

function enviarTemplateNaConversa() {
    const conv = WA_CONVERSAS.find(c => String(c.id) === String(WA_CONVERSA_ATIVA_ID));
    if (!conv) return;

    const templateName = document.getElementById("wa-chat-template-select")?.value || "hello_world";
    const info = WA_TEMPLATES_INFO[templateName] || { label: templateName, lang: "pt_BR", preview: `Modelo: ${templateName}` };
    const telefone = normalizarTelefone(conv.telefone);

    fetch(`${API_URL}/api/whatsapp/enviar-template`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            telefone,
            template_nome: templateName,
            idioma: info.lang
        })
    })
    .then(async res => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || "Erro ao enviar modelo");
        return data;
    })
    .catch(() => {
        // Permite registrar no fluxo visual mesmo antes do endpoint estar no backend
        return { simulado: true };
    })
    .then(() => {
        const hora = formatarHoraAtual();
        const textoRegistro = `[Modelo: ${info.label}] ${info.preview}`;
        conv.mensagens = conv.mensagens || [];
        conv.mensagens.push({ direcao: "sent", texto: textoRegistro, hora });
        conv.ultima_mensagem = textoRegistro;
        conv.hora = hora;
        salvarConversasLocalmente();

        document.getElementById("wa-templates-drawer")?.classList.add("hidden");
        renderizarMensagensConversaAtiva();
        renderizarConversasWhatsApp();
    });
}

function enviarMensagemConversaAtiva() {
    const conv = WA_CONVERSAS.find(c => String(c.id) === String(WA_CONVERSA_ATIVA_ID));
    const inputEl = document.getElementById("wa-input-mensagem");
    if (!conv || !inputEl) return;

    const mensagem = inputEl.value.trim();
    if (!mensagem) return;

    const telefone = normalizarTelefone(conv.telefone);
    inputEl.value = "";

    fetch(`${API_URL}/api/whatsapp/enviar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ telefone, mensagem })
    })
    .then(async res => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || "Erro na Meta");
        return data;
    })
    .catch(() => ({ simulado: true }))
    .then(() => {
        const hora = formatarHoraAtual();
        conv.mensagens = conv.mensagens || [];
        conv.mensagens.push({ direcao: "sent", texto: mensagem, hora });
        conv.ultima_mensagem = mensagem;
        conv.hora = hora;
        salvarConversasLocalmente();

        renderizarMensagensConversaAtiva();
        renderizarConversasWhatsApp();
    });
}

// Modal: Selecionar Cliente para Iniciar Conversa
function abrirModalNovaConversa() {
    document.getElementById("modal-nova-conversa")?.classList.remove("hidden");
    const buscaInput = document.getElementById("busca-cliente-nova-conversa");
    if (buscaInput) buscaInput.value = "";
    renderizarListaNovaConversa();
}

function fecharModalNovaConversa() {
    document.getElementById("modal-nova-conversa")?.classList.add("hidden");
}

function renderizarListaNovaConversa() {
    const listaEl = document.getElementById("lista-clientes-nova-conversa");
    if (!listaEl) return;

    const termo = (document.getElementById("busca-cliente-nova-conversa")?.value || "").toLowerCase().trim();

    const clientesComTel = (LEADS_CACHE || []).filter(lead => {
        const tel = normalizarTelefone(lead.telefone);
        if (!tel) return false;
        const nome = (lead.nome || "").toLowerCase();
        return !termo || nome.includes(termo) || tel.includes(termo);
    });

    if (!clientesComTel.length) {
        listaEl.innerHTML = `<div class="lead-info">Nenhum cliente com telefone encontrado.</div>`;
        return;
    }

    listaEl.innerHTML = clientesComTel.map(lead => {
        const nomeSeguro = escaparAspas(lead.nome || "Cliente");
        const telSeguro = escaparAspas(lead.telefone || "");
        const nomeHtml = escaparHtml(lead.nome || "Sem Nome");
        const telHtml = escaparHtml(lead.telefone || "");

        return `
            <div class="lead-card" style="margin-bottom: 8px; cursor: pointer;" onclick="iniciarConversaComLead('${nomeSeguro}', '${telSeguro}')">
                <div class="lead-name">${nomeHtml}</div>
                <div class="lead-info">📞 ${telHtml}</div>
            </div>
        `;
    }).join("");
}

function iniciarConversaComLead(nome, telefone) {
    const conv = garantirConversa(nome, telefone);
    fecharModalNovaConversa();
    mudarSubAbaWhatsApp("conversas", document.getElementById("wa-tab-btn-conversas"));
    abrirConversaWhatsApp(conv.id);
}

// Sub-aba Envios / Modelos
function popularSelectClientesEnvio() {
    const selectEl = document.getElementById("envio-cliente-select");
    if (!selectEl) return;

    const clientesComTel = (LEADS_CACHE || []).filter(l => normalizarTelefone(l.telefone));
    selectEl.innerHTML = `<option value="">-- Selecione um cliente salvo --</option>` + clientesComTel.map((lead, idx) => {
        const nome = escaparHtml(lead.nome || "Cliente");
        const tel = escaparHtml(lead.telefone || "");
        return `<option value="${idx}">${nome} (${tel})</option>`;
    }).join("");
}

function preencherDestinoEnvio() {
    const selectEl = document.getElementById("envio-cliente-select");
    const telInput = document.getElementById("chat-telefone");
    if (!selectEl || !telInput) return;

    const clientesComTel = (LEADS_CACHE || []).filter(l => normalizarTelefone(l.telefone));
    const idx = parseInt(selectEl.value, 10);
    if (!Number.isNaN(idx) && clientesComTel[idx]) {
        telInput.value = clientesComTel[idx].telefone || "";
    }
}

function alternarTipoEnvio() {
    const tipo = document.getElementById("envio-tipo")?.value || "TEMPLATE";
    const boxTemplate = document.getElementById("envio-box-template");
    const boxTexto = document.getElementById("envio-box-texto");

    if (tipo === "TEMPLATE") {
        boxTemplate?.classList.remove("hidden");
        boxTexto?.classList.add("hidden");
    } else {
        boxTemplate?.classList.add("hidden");
        boxTexto?.classList.remove("hidden");
    }
}

// Enviar Mensagem ou Modelo via WhatsApp API
function enviarMensagemWhatsApp() {
    const telInput = document.getElementById("chat-telefone");
    const msgInput = document.getElementById("chat-mensagem");
    const tipo = document.getElementById("envio-tipo")?.value || "TEMPLATE";
    const templateNome = document.getElementById("envio-template-nome")?.value || "hello_world";

    const telefoneBruto = telInput ? telInput.value.trim() : "";
    const telefone = normalizarTelefone(telefoneBruto);
    const mensagem = msgInput ? msgInput.value.trim() : "";

    if (!telefone) {
        alert("Preencha o número de destino com DDI e DDD.");
        return;
    }

    if (tipo === "TEXTO" && !mensagem) {
        alert("Preencha a mensagem para envio livre.");
        return;
    }

    const endpoint = tipo === "TEMPLATE"
        ? `${API_URL}/api/whatsapp/enviar-template`
        : `${API_URL}/api/whatsapp/enviar`;

    const payload = tipo === "TEMPLATE"
        ? {
            telefone,
            template_nome: templateNome,
            idioma: WA_TEMPLATES_INFO[templateNome]?.lang || "pt_BR"
        }
        : { telefone, mensagem };

    fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    })
    .then(async res => {
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            throw new Error(data.detail || "Erro na Meta");
        }
        return data;
    })
    .then(data => {
        if (data.sucesso !== false) {
            const selectEl = document.getElementById("envio-cliente-select");
            const clientesComTel = (LEADS_CACHE || []).filter(l => normalizarTelefone(l.telefone));
            const idx = parseInt(selectEl?.value ?? "", 10);
            const nomeCliente = (!Number.isNaN(idx) && clientesComTel[idx]) ? clientesComTel[idx].nome : telefoneBruto;

            const conv = garantirConversa(nomeCliente, telefoneBruto);
            const hora = formatarHoraAtual();
            const textoRegistrado = tipo === "TEMPLATE"
                ? `[Modelo: ${templateNome}] ${WA_TEMPLATES_INFO[templateNome]?.preview || ""}`
                : mensagem;

            conv.mensagens = conv.mensagens || [];
            conv.mensagens.push({ direcao: "sent", texto: textoRegistrado, hora });
            conv.ultima_mensagem = textoRegistrado;
            conv.hora = hora;
            salvarConversasLocalmente();

            alert(tipo === "TEMPLATE" ? "Modelo disparado com sucesso!" : "Mensagem enviada com sucesso!");
            if (msgInput) msgInput.value = "";
            renderizarConversasWhatsApp();
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