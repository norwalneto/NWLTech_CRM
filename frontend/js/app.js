// URL padrão do backend (substitua pela sua URL gerada no Railway)
let API_URL = localStorage.getItem("nwl_backend_url") || "https://seu-app.up.railway.app";
document.getElementById("config-backend-url").value = API_URL;

// Testar conexão ao iniciar
verificarConexao();

function verificarConexao() {
    const dot = document.getElementById("status-dot");
    const text = document.getElementById("status-text");

    fetch(`${API_URL}/`)
        .then(res => res.json())
        .then(data => {
            if(data.status === "online") {
                dot.className = "dot online";
                text.innerText = "Online (Railway)";
                carregarLeads();
            } else {
                throw new Error();
            }
        })
        .catch(() => {
            dot.className = "dot offline";
            text.innerText = "Offline / Erro";
        });
}

function salvarConfiguracoes() {
    const url = document.getElementById("config-backend-url").value.trim();
    if(url) {
        API_URL = url.endsWith("/") ? url.slice(0, -1) : url;
        localStorage.setItem("nwl_backend_url", API_URL);
        alert("URL salva com sucesso!");
        verificarConexao();
    }
}

// Troca de Abas
function mudarAba(abaId, elemento) {
    document.querySelectorAll(".tab-content").forEach(el => el.classList.remove("active"));
    document.querySelectorAll(".nav-item").forEach(el => el.classList.remove("active"));

    document.getElementById(`tab-${abaId}`).classList.add("active");
    elemento.classList.add("active");

    if(abaId === 'kanban') {
        carregarLeads();
    }
}

// Buscador
function executarBusca() {
    const nicho = document.getElementById("busca-nicho").value;
    const cidade = document.getElementById("busca-cidade").value;
    const raio_km = document.getElementById("busca-raio").value;
    const max_resultados = document.getElementById("busca-max").value;
    const apenas_sem_site = document.getElementById("busca-sem-site").checked;

    if(!nicho || !cidade) {
        alert("Preencha o nicho e a cidade.");
        return;
    }

    const box = document.getElementById("busca-resultado-box");
    const msg = document.getElementById("busca-status-msg");
    box.classList.remove("hidden");
    msg.innerText = "Minerando leads no Google Maps... Aguarde.";

    fetch(`${API_URL}/api/buscar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nicho, cidade, raio_km: parseInt(raio_km), max_resultados: parseInt(max_resultados), apenas_sem_site })
    })
    .then(res => res.json())
    .then(data => {
        if(data.sucesso) {
            msg.innerText = `Busca concluída! ${data.novos_salvos} novos leads salvos.`;
            carregarLeads();
        } else {
            msg.innerText = "Erro na busca: " + (data.detail || "Desconhecido");
        }
    })
    .catch(err => {
        msg.innerText = "Erro de conexão com o servidor.";
        console.error(err);
    });
}

// Carregar Kanban
function carregarLeads() {
    fetch(`${API_URL}/api/leads`)
        .then(res => res.json())
        .then(data => {
            const leads = data.leads || [];
            
            const colunas = {
                "NOVO": document.getElementById("list-novo"),
                "PENDENTE": document.getElementById("list-pendente"),
                "CONTATO": document.getElementById("list-contato"),
                "FECHADO": document.getElementById("list-fechado")
            };

            const contadores = { "NOVO": 0, "PENDENTE": 0, "CONTATO": 0, "FECHADO": 0 };

            // Limpar colunas
            Object.values(colunas).forEach(col => col.innerHTML = "");

            leads.forEach(lead => {
                const status = (lead.status_kanban || "NOVO").toUpperCase();
                if(contadores[status] !== undefined) contadores[status]++;

                const card = document.createElement("div");
                card.className = "lead-card";
                card.innerHTML = `
                    <div class="lead-name">${lead.nome}</div>
                    <div class="lead-info">${lead.cidade || ''} - ${lead.nicho || ''}</div>
                    <div class="lead-actions">
                        ${lead.whatsapp_link ? `<a href="${lead.whatsapp_link}" target="_blank" class="btn-whatsapp" style="padding:4px 8px; text-decoration:none; border-radius:4px; font-size:0.75rem;"><i class="fa-brands fa-whatsapp"></i></a>` : ''}
                        <button class="btn-sm" onclick="mudarStatusLead('${lead.id}', 'PENDENTE')">Pend.</button>
                        <button class="btn-sm" onclick="mudarStatusLead('${lead.id}', 'CONTATO')">Contato</button>
                        <button class="btn-sm" onclick="mudarStatusLead('${lead.id}', 'FECHADO')">Fechado</button>
                    </div>
                `;
                if(colunas[status]) colunas[status].appendChild(card);
            });

            document.getElementById("count-novo").innerText = contadores["NOVO"];
            document.getElementById("count-pendente").innerText = contadores["PENDENTE"];
            document.getElementById("count-contato").innerText = contadores["CONTATO"];
            document.getElementById("count-fechado").innerText = contadores["FECHADO"];
        })
        .catch(err => console.error("Erro ao carregar leads:", err));
}

function mudarStatusLead(leadId, novoStatus) {
    fetch(`${API_URL}/api/leads/${leadId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status_kanban: novoStatus })
    })
    .then(res => res.json())
    .then(() => carregarLeads())
    .catch(err => console.error(err));
}

// Enviar Mensagem WhatsApp API
function enviarMensagemWhatsApp() {
    const telefone = document.getElementById("chat-telefone").value;
    const mensagem = document.getElementById("chat-mensagem").value;

    if(!telefone || !mensagem) {
        alert("Preencha o telefone e a mensagem.");
        return;
    }

    fetch(`${API_URL}/api/whatsapp/enviar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ telefone, mensagem })
    })
    .then(res => res.json())
    .then(data => {
        if(data.sucesso) {
            alert("Mensagem enviada com sucesso pela API do WhatsApp!");
            document.getElementById("chat-mensagem").value = "";
        } else {
            alert("Erro ao enviar: " + (data.detail || "Erro na Meta"));
        }
    })
    .catch(err => alert("Erro de conexão ao disparar mensagem."));
}

function iniciarEmbeddedSignup() {
    alert("Fluxo de Cadastro Incorporado da Meta pronto para ser ativado via SDK oficial.");
}