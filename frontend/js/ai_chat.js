/**
 * js/ai_chat.js
 * Component AI Chat dung chung giua base.html (home), control.html, monitor.html,
 * settings.html va history.html (AI Panel ben phai HMI).
 *
 * Component nay quan ly:
 *   - Badge provider + tier (#aiProvBadge, #aiTierLbl hoac #aiTier)
 *   - Gui/nhan tin nhan AI Chat (poll /api/ai/chat/{id} cho toi khi done)
 *   - (tuy chon) Upload anh phoi truoc khi chat
 *   - (tuy chon) Luu G-Code AI sinh ra + gui sang Toolpath Preview (#toolpathFrame)
 *   - Sidebar status (Edge online / so luong alarm) — #sEdgeDot/#sEdgeTxt, #sAlmDot/#sAlmTxt
 *   - User bar (#aiUser, #aiRoleLbl) + nut Logout (window.doLogout)
 */

import { api } from '/static/js/api.js';
import { DigitalTwinViewer } from '/static/js/digital_twin.js';
import { evaluateIntentContract, verifyIntentPayloadHashes } from '/static/js/intent_contract_gate.js';

// ── User bar (ten + role tren AI panel) ─────────────────────────────────────
export function initUserBar(auth) {
    const u = document.getElementById('aiUser');
    if (u) u.textContent = auth.username();
    const r = document.getElementById('aiRoleLbl');
    if (r) r.textContent = `[${auth.role()}]`;
}

/** Gan window.doLogout dung chung cho moi trang (nut LOGOUT trong AI panel). */
export function initLogout(auth) {
    window.doLogout = async () => {
        if (confirm('Đăng xuất?')) await auth.logout();
    };
}

// ── Sidebar status (Edge online + so alarm) ─────────────────────────────────
export function initSidebarStatus(intervalMs = 15000) {
    async function fetchStatus() {
        try {
            const [system, d] = await Promise.all([
                api.get('/api/system/status'),
                api.get('/api/monitor/status'),
            ]);
            const edge = system?.connection?.edge_runtime || {};
            const online = Boolean(edge.connected);
            const conflict = String(edge.status || '').toLowerCase() === 'conflict';
            const n = d.alarms?.unresolved || 0;
            const c = d.alarms?.critical || 0;

            const sE = document.getElementById('sEdgeDot');
            const sT = document.getElementById('sEdgeTxt');
            if (sE) {
                sE.className = 'sdot ' + (online ? 'on' : conflict ? 'warn' : 'off');
                if (sT) sT.textContent = online
                    ? `Edge ${edge.active_entrypoint || 'online'}`
                    : conflict ? 'Edge conflict' : 'Edge offline';
            }

            const sA = document.getElementById('sAlmDot');
            const sAt = document.getElementById('sAlmTxt');
            if (sA) {
                sA.className = 'sdot ' + (c > 0 ? 'off' : n > 0 ? 'warn' : 'on');
                sAt.textContent = c > 0 ? `${c} critical` : n > 0 ? `${n} alarm` : 'No alarm';
            }
            return d;
        } catch (_) { return null; }
    }
    fetchStatus();
    setInterval(fetchStatus, intervalMs);
    return { fetchStatus };
}

// ── AI Provider badge ────────────────────────────────────────────────────────
export async function fetchProviderBadge() {
    try {
        const d = await api.get('/api/ai/provider/status');
        const badge = document.getElementById('aiProvBadge');
        if (badge) badge.textContent = `${d.provider || 'gemini'} ▾`;
        const tier = document.getElementById('aiTierLbl') || document.getElementById('aiTier');
        if (tier) tier.textContent = `tier: ${d.tier || 'cloud'}`;
        return d;
    } catch (_) { return null; }
}

/**
 * Làm mới provider badge trên tất cả các panel
 * Gọi từ settings.js khi đổi provider
 */
export async function refreshProviderBadge() {
    try {
        const d = await api.get('/api/ai/provider/status');
        const provider = d.provider || 'gemini';
        const tier = d.tier || 'cloud';
        
        // Cập nhật tất cả badge
        document.querySelectorAll('#aiProvBadge').forEach(el => {
            el.textContent = `${provider} ▾`;
        });
        
        document.querySelectorAll('#aiTierLbl, #aiTier').forEach(el => {
            el.textContent = `tier: ${tier}`;
        });
        
        // Cập nhật pill trong settings
        const tierPill = document.getElementById('tierPill');
        if (tierPill) {
            tierPill.textContent = tier;
            tierPill.className = `tier-pill ${tier === 'cloud' ? 'tier-cloud' : tier === 'local' ? 'tier-local' : 'tier-emergency'}`;
        }
        
        const provNameLbl = document.getElementById('provNameLbl');
        if (provNameLbl) provNameLbl.textContent = provider;
        
        // Highlight provider card trong settings
        document.querySelectorAll('.prov-card').forEach(c => {
            c.classList.toggle('active', c.getAttribute('data-p') === provider);
        });
        
        // Cập nhật context badge trong AI panel nếu có
        const ctxBadge = document.querySelector('.ai-ctx-bar .ai-ctx-dot');
        if (ctxBadge) {
            ctxBadge.style.background = provider === 'ollama' ? 'var(--status-active)' : 'var(--cyan-portal)';
        }
        
        return d;
    } catch (_) {
        return null;
    }
}

// Gán vào window để settings.js có thể gọi
window.refreshProviderBadge = refreshProviderBadge;

/**
 * Khoi tao AI Chat widget day du.
 *
 * @param {object} opts
 * @param {boolean} opts.enableUpload       - hien nut upload anh phoi (#aiFile phai co trong DOM)
 * @param {boolean} opts.enableGcodeActions - khi AI tra ve G-code: hien nut "Luu G-Code" + "Preview" (gui sang #toolpathFrame)
 * @param {Function} [opts.onAfterChat]     - callback chay sau khi 1 luot chat hoan tat (vd: refresh danh sach G-code)
 * @param {number} [opts.pollIntervalMs]    - chu ky poll ket qua AI (mac dinh 2000ms)
 * @param {number} [opts.maxPollTries]      - so lan poll toi da truoc khi bo cuoc (mac dinh 40)
 * @param {string} [opts.context]           - context: 'monitor' | 'control' | 'history' | 'home' | 'settings'
 */
export function initAiChat(opts = {}) {
    let _gcodeAttachment = null;
    let _collisionRepairContext = null;

    function _setCollisionRepairContext(contract) {
        const ctx = contract || {};
        if (!ctx.collision_id || !ctx.failed_check_id || !ctx.gcode_id || !ctx.base_gcode_sha256 || !ctx.base_version) {
            _collisionRepairContext = null;
            return null;
        }
        _collisionRepairContext = {
            base_gcode_id: String(ctx.gcode_id),
            base_gcode_sha256: String(ctx.base_gcode_sha256).toLowerCase(),
            base_version: Number(ctx.base_version),
            failed_check_id: String(ctx.failed_check_id),
            collision_id: String(ctx.collision_id),
        };
        return _collisionRepairContext;
    }

    function attachGCode(gcode, filename, sha256) {
        const text = String(gcode || "");
        if (!text.trim()) { _gcodeAttachment = null; return; }
        _gcodeAttachment = {
            gcode: text,
            filename: String(filename || "attached.nc"),
            sha256: String(sha256 || "").toLowerCase(),
        };
    }

    function clearGCodeAttachment() { _gcodeAttachment = null; }
    function clearCollisionRepairContext() { _collisionRepairContext = null; }
    window.aiSetCollisionRepairContext = _setCollisionRepairContext;
    window.aiClearCollisionRepairContext = clearCollisionRepairContext;
    const {
        enableUpload = false,
        enableGcodeActions = false,
        onAfterChat = null,
        pollIntervalMs = 2000,
        maxPollTries = 40,
        context = 'home',
    } = opts;

    let _busy = false;
    let _imgId = '';
    let _intentCounter = 0;
    const _pendingIntentContracts = new Map();
    const _conversationStorageKey = `cnc_ai_conversation_${context}`;
    const _presentationStorageKey = `cnc_ai_presentation_${context}`;
    let _currentConvId = localStorage.getItem(_conversationStorageKey) || null;
    let _presentationMode = localStorage.getItem(_presentationStorageKey) === 'technical'
        ? 'technical' : 'simple';

    function _setConversationId(value) {
        _currentConvId = value ? String(value) : null;
        if (_currentConvId) localStorage.setItem(_conversationStorageKey, _currentConvId);
        else localStorage.removeItem(_conversationStorageKey);
        return _currentConvId;
    }
    window.aiGetConversationId = () => _currentConvId;
    window.aiSetConversationId = value => _setConversationId(value);

    function _applyPresentationMode(mode) {
        _presentationMode = mode === 'technical' ? 'technical' : 'simple';
        localStorage.setItem(_presentationStorageKey, _presentationMode);
        document.body.classList.toggle('ai-presentation-technical', _presentationMode === 'technical');
        document.querySelectorAll('[data-ai-presentation]').forEach(button => {
            button.classList.toggle('active', button.getAttribute('data-ai-presentation') === _presentationMode);
        });
        document.querySelectorAll('details.ai-technical-view').forEach(details => {
            details.open = _presentationMode === 'technical';
        });
        return _presentationMode;
    }
    window.setAiPresentationMode = _applyPresentationMode;

    const _el = id => document.getElementById(id);

    // ── Set context ──
    const ctxEl = document.getElementById('aiCtx');
    if (ctxEl) {
        const ctxMap = {
            monitor: 'GIÁM SÁT REALTIME',
            control: 'ĐIỀU KHIỂN + G-CODE',
            history: 'LỊCH SỬ DỮ LIỆU',
            home: 'HOME',
            settings: 'CẤU HÌNH HỆ THỐNG'
        };
        ctxEl.textContent = ctxMap[context] || 'HMI';
    }

    function _escapeHtml(value) {
        return String(value ?? '').replace(/[&<>"']/g, ch => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        })[ch]);
    }

    function _appendMsg(role, value, trustedHtml = false) {
        const c = _el('aiMsgs');
        if (!c) return null;
        const d = document.createElement('div');
        d.className = `ai-msg ${role}`;
        if (trustedHtml) d.innerHTML = value;
        else d.textContent = String(value ?? '');
        c.appendChild(d);
        c.scrollTop = c.scrollHeight;
        return d;
    }

    function _renderMessageCoaching(contract, { allowApply = true } = {}) {
        const data = contract || {};
        const missing = Array.isArray(data.missing_details) ? data.missing_details : [];
        const notes = Array.isArray(data.notes) ? data.notes : [];
        if (!data.changed && !missing.length && !notes.length) return '';
        const suggested = _escapeHtml(data.suggested_message || data.normalized_message || '');
        const missingHtml = missing.length
            ? `<div class="ai-coach-missing"><b>Còn thiếu:</b> ${missing.map(_escapeHtml).join('; ')}</div>` : '';
        const notesHtml = notes.length
            ? `<div class="ai-coach-notes">${notes.map(item => `• ${_escapeHtml(item)}`).join('<br>')}</div>` : '';
        const encoded = encodeURIComponent(String(data.suggested_message || ''));
        const apply = allowApply && encoded
            ? `<button class="ai-coach-apply" onclick="aiUseCoachedMessage('${encoded}')">Dùng câu đã sửa</button>` : '';
        return `<div class="ai-coach-card ${data.blocking ? 'blocking' : ''}">
            <div class="ai-coach-title">✍️ Agent làm rõ câu bạn viết</div>
            ${suggested ? `<div class="ai-coach-suggestion">${suggested}</div>` : ''}
            ${missingHtml}${notesHtml}${apply}
        </div>`;
    }

    function _renderContextualResponse(contract) {
        const data = contract || {};
        if (data.schema !== 'contextual-action-response-v1') return '';
        const answer = _escapeHtml(data.direct_answer || '');
        const actions = Array.isArray(data.actions_completed) ? data.actions_completed : [];
        const remaining = Array.isArray(data.remaining_user_decisions) ? data.remaining_user_decisions : [];
        const question = _escapeHtml(data.question || '');
        const actionHtml = actions.length
            ? `<div class="ai-action-section"><b>Đã thực hiện</b>${actions.map(item => `<div class="ai-action-item">✓ ${_escapeHtml(item)}</div>`).join('')}</div>` : '';
        const remainingHtml = remaining.length
            ? `<div class="ai-action-section remaining"><b>Còn cần bạn quyết định</b>${remaining.map(item => `<div class="ai-action-item">• ${_escapeHtml(item)}</div>`).join('')}</div>` : '';
        const technical = data.technical_details || {};
        const clarificationOptions = Array.isArray(technical.clarification_options)
            ? technical.clarification_options.filter(item => item && item.label) : [];
        const optionHtml = clarificationOptions.length
            ? `<div class="ai-clarification-options">${clarificationOptions.map(item => {
                const encoded = encodeURIComponent(String(item.label || ''));
                return `<button type="button" class="ai-clarification-option" onclick="aiUseClarificationOption('${encoded}')">${_escapeHtml(item.label)}</button>`;
            }).join('')}</div>` : '';
        const questionHtml = question ? `<div class="ai-action-question">${question}${optionHtml}</div>` : '';
        const technicalHtml = Object.keys(technical).length
            ? `<details class="ai-technical-details"><summary>Chi tiết kỹ thuật</summary><pre>${_escapeHtml(JSON.stringify(technical, null, 2))}</pre></details>` : '';
        return `<div class="ai-action-card">
            ${answer ? `<div class="ai-action-answer">${answer}</div>` : ''}
            ${actionHtml}${remainingHtml}${questionHtml}${technicalHtml}
        </div>`;
    }

    window.aiUseClarificationOption = function (encoded) {
        const input = _el('aiIn');
        if (!input) return;
        input.value = decodeURIComponent(String(encoded || ''));
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
    };

    window.aiUseCoachedMessage = function (encoded) {
        const input = _el('aiIn');
        if (!input) return;
        input.value = decodeURIComponent(String(encoded || ''));
        input.focus();
        input.setSelectionRange(input.value.length, input.value.length);
    };

    async function coachDraft() {
        const input = _el('aiIn');
        if (!input || !input.value.trim()) return;
        try {
            const result = await api.post('/api/ai/chat/coach', {
                message: input.value.trim(),
                has_gcode: Boolean(_gcodeAttachment?.gcode),
                collision_context: _collisionRepairContext || {},
                page_context: context,
            });
            const card = _renderMessageCoaching(result);
            if (card) _appendMsg('ai', card, true);
            if (result.suggested_message) {
                input.value = result.suggested_message;
                input.focus();
            }
        } catch (error) {
            _appendMsg('sys', `Không thể sửa câu: ${error.message}`);
        }
    }
    window.aiCoachDraft = coachDraft;

    function _displayNumber(value) {
        const number = Number(value);
        return Number.isFinite(number) ? String(number) : 'CHƯA CÓ';
    }

    function _featureDimensions(feature) {
        const xb = Array.isArray(feature?.x_bounds) ? feature.x_bounds : null;
        const yb = Array.isArray(feature?.y_bounds) ? feature.y_bounds : null;
        if (!xb || !yb || xb.length < 2 || yb.length < 2) return '';
        const width = Math.abs(Number(xb[1]) - Number(xb[0]));
        const height = Math.abs(Number(yb[1]) - Number(yb[0]));
        if (!Number.isFinite(width) || !Number.isFinite(height)) return '';
        return `${_displayNumber(width)} × ${_displayNumber(height)} mm`;
    }

    function _customerOperationLabel(feature) {
        const operation = String(feature?.operation || '');
        const labels = {
            RECTANGULAR_CONTOUR_OUTSIDE: 'Giữ lại phần hình chữ nhật; dao chạy bên ngoài đường biên',
            RECTANGULAR_CONTOUR_INSIDE: 'Dao chạy phía trong đường biên hình chữ nhật',
            RECTANGULAR_POCKET: 'Khoét bỏ vật liệu bên trong hình chữ nhật',
            ROUNDED_RECT_POCKET: 'Khoét một khay chữ nhật có bo góc',
            CIRCULAR_POCKET: 'Khoét một hốc tròn',
            CIRCULAR_OUTSIDE_KEEP_ISLAND: 'Giữ lại phần tròn ở giữa',
            CIRCULAR_CONTOUR_INSIDE: 'Dao chạy phía trong đường tròn',
            CIRCULAR_CONTOUR_OUTSIDE: 'Dao chạy phía ngoài đường tròn',
            CIRCULAR_THROUGH_MILL: 'Phay xuyên phần tròn bằng dao phay ngón',
            CROSS_SLOT_MILL: 'Phay rãnh hình chữ thập',
            SLOT_MILL: 'Phay rãnh thẳng',
            REFERENCE_ONLY: 'Chỉ dùng làm đường tham chiếu',
        };
        if (operation === 'RECTANGULAR_CONTOUR_OUTSIDE' && (!feature?.x_bounds || !feature?.y_bounds)) {
            return 'Cắt theo viền ngoài của sản phẩm; chưa có kích thước cuối';
        }
        if (labels[operation]) return labels[operation];
        if (feature?.type === 'rectangular_contour') {
            return 'Chưa rõ bạn muốn giữ lại hay khoét bỏ phần hình chữ nhật';
        }
        if (feature?.type === 'circular_feature') {
            return 'Chưa rõ phần tròn là hốc, đường biên hay phần cần giữ lại';
        }
        return 'Đã nhận hình học nhưng chưa khóa cách gia công';
    }

    function _customerIssueText(key) {
        const value = String(key || '');
        if (value.startsWith('conflict:')) return 'Có hai giá trị khác nhau cho cùng một thông tin; cần chọn giá trị đúng';
        if (value.endsWith('.role')) return 'Cần bạn quyết định phần vật liệu nào được giữ lại hoặc loại bỏ';
        if (value.endsWith('.depth')) return 'Cần chiều sâu của chi tiết này';
        if (value.endsWith('.corner_radius')) return 'Cần mức bo góc của khay';
        if (value.endsWith('.diameter')) return 'Cần đường kính của các phần tròn';
        if (value.startsWith('group:') && value.endsWith('.collinear_positions')) return 'Đã giữ đúng số lượng và yêu cầu thẳng hàng; cần khoảng cách hoặc vị trí các tâm';
        if (value.endsWith('.x_bounds') || value.endsWith('.y_bounds') || value.endsWith('.extent')) return 'Cần thêm kích thước hoặc vị trí của hình';
        if (value === 'stock.dimensions') return 'Cần kích thước phôi';
        if (value === 'work_coordinate.origin') return 'Cần biết điểm đặt gốc trên phôi';
        if (value === 'work_coordinate.z0') return 'Cần xác định mặt Z0 trước khi khóa đường chạy dao';
        if (value === 'part.retention') return 'Cần cách giữ chi tiết khi đường cắt có thể làm chi tiết rời ra';
        if (value === 'feature.interaction') return 'Cần quyết định các hình được phép cắt giao nhau như thế nào';
        if (value === 'tool.id' || value === 'tool.diameter' || value === 'safe_z' || value === 'stock.material') {
            return 'Hệ thống sẽ tự tra hoặc đề xuất từ cấu hình dự án trước khi hỏi bạn';
        }
        return value;
    }

    function _customerQuestion(payload) {
        const next = payload?.next_clarification || {};
        const key = String(next.key || '');
        const spec = payload?.job_spec || {};
        const featureId = key.match(/^(F\d+)\./i)?.[1];
        const feature = (spec.features || []).find(item => String(item.id || '').toUpperCase() === String(featureId || '').toUpperCase());
        const dimensions = _featureDimensions(feature);
        if (key.startsWith('conflict:') && key.endsWith('.depth')) {
            return 'Bạn đã đưa ra nhiều giá trị chiều sâu khác nhau. Chiều sâu cuối cùng cần dùng là bao nhiêu mm?';
        }
        if (key.endsWith('.role') && feature?.type === 'rectangular_contour') {
            return `Sau khi gia công ${dimensions ? `hình chữ nhật ${dimensions}` : 'hình chữ nhật này'}, bạn muốn giữ lại phần ở giữa, khoét bỏ phần ở giữa, hay chỉ tạo một rãnh chạy quanh mép phía trong?`;
        }
        if (key.endsWith('.role') && feature?.type === 'circular_feature') {
            return 'Phần tròn này là chỗ cần khoét đi, đường biên cần chạy dao, hay phần tròn cần giữ lại?';
        }
        return String(next.question_vi || '');
    }

    function _customerMaterialLabel(value) {
        const material = String(value || '');
        if (/^alumin(?:um|ium)/i.test(material)) {
            return material.replace(/^alumin(?:um|ium)/i, 'Nhôm');
        }
        return material;
    }

    function _customerProcessError(value) {
        const text = String(value || '');
        const stepdown = text.match(/requested exact step-down\s+([0-9.]+)mm\s+exceeds Neo4j maximum\s+([0-9.]+)mm/i);
        if (stepdown) {
            return `Mỗi lớp ${stepdown[1]} mm vượt giới hạn ${stepdown[2]} mm từ dữ liệu kỹ thuật; hệ thống đã chặn và không tự đổi giá trị bạn nhập`;
        }
        if (/END_MILL_ONLY/i.test(text)) {
            return 'Bạn đã yêu cầu nguyên công khoan; phiên bản hiện tại chỉ hỗ trợ phay bằng dao phay ngón và sẽ không tự đổi yêu cầu khoan thành một nguyên công khác';
        }
        if (/unsupported_units:INCH/i.test(text)) {
            return 'Hệ thống hiện chỉ nhận kích thước theo milimét; chưa tự đổi đơn vị inch để tránh sai kích thước';
        }
        return _customerIssueText(text);
    }

    function _customerFeatureCards(features, ambiguities) {
        const rows = Array.isArray(features) ? features : [];
        const unresolved = new Set((ambiguities || []).map(String));
        const consumed = new Set();
        const cards = [];
        rows.forEach((feature, index) => {
            if (consumed.has(index)) return;
            if (feature?.type === 'circular_feature') {
                const provenance = Array.isArray(feature.provenance) ? String(feature.provenance[0] || '') : '';
                const group = rows.map((item, itemIndex) => ({ item, itemIndex })).filter(({ item, itemIndex }) => {
                    if (consumed.has(itemIndex) || item?.type !== 'circular_feature') return false;
                    const itemProvenance = Array.isArray(item.provenance) ? String(item.provenance[0] || '') : '';
                    return String(item.operation || '') === String(feature.operation || '')
                        && Number(item.diameter_mm || 0) === Number(feature.diameter_mm || 0)
                        && Number(item.depth_mm) === Number(feature.depth_mm)
                        && itemProvenance === provenance;
                });
                if (group.length > 1) {
                    group.forEach(({ itemIndex }) => consumed.add(itemIndex));
                    const relation = /thẳng\s*hàng|thang\s*hang|collinear|straight\s+line/i.test(provenance)
                        ? ' thẳng hàng' : '';
                    const diameter = Number(feature.diameter_mm) > 0 ? `Ø${_displayNumber(feature.diameter_mm)} mm` : 'chưa có đường kính';
                    const depth = Number(feature.depth_mm) > 0 ? `sâu ${_displayNumber(feature.depth_mm)} mm` : 'chưa có chiều sâu';
                    const groupPositionUnknown = [...unresolved].some(key => key.startsWith('group:') && key.endsWith('.collinear_positions'));
                    const centers = !groupPositionUnknown
                        ? group.map(({ item }) => `X${_displayNumber(item.center_mm?.[0])} Y${_displayNumber(item.center_mm?.[1])}`).join(' · ')
                        : '';
                    cards.push(`<div class="customer-feature-item">
                        <div class="customer-feature-name">${group.length} phần tròn${relation} — ${_escapeHtml(_customerOperationLabel(feature))}</div>
                        <div class="customer-feature-meta">${[diameter, depth, centers].filter(Boolean).map(_escapeHtml).join(' · ')}</div>
                    </div>`);
                    return;
                }
            }
            consumed.add(index);
            const dimensions = _featureDimensions(feature);
            const diameter = Number(feature.diameter_mm) > 0 ? `Ø${_displayNumber(feature.diameter_mm)} mm` : '';
            const depth = Number(feature.depth_mm) > 0 ? `sâu ${_displayNumber(feature.depth_mm)} mm` : 'chưa có chiều sâu';
            const geometry = dimensions || diameter || '';
            cards.push(`<div class="customer-feature-item">
                <div class="customer-feature-name">${_escapeHtml(_customerOperationLabel(feature))}</div>
                <div class="customer-feature-meta">${[geometry, depth].filter(Boolean).map(_escapeHtml).join(' · ')}</div>
            </div>`);
        });
        return cards.join('');
    }

    function _customerStatus(payload, evaluation) {
        const status = String(payload?.status || '');
        if (status === 'VALIDATED_DRAFT') {
            return { css: 'customer-status-good', text: 'Đã hiểu yêu cầu và tạo bản nháp để bạn kiểm tra' };
        }
        if (status === 'NEEDS_CLARIFICATION') {
            return { css: 'customer-status-warn', text: 'Đã giữ phần chính; tôi sẽ hỏi từng quyết định còn thiếu' };
        }
        if (status === 'CONTEXT_REQUIRED' || status === 'CONTEXT_INCOMPLETE' || status === 'CONTEXT_RESOLVING') {
            return { css: 'customer-status-warn', text: 'Đã hiểu sản phẩm; hệ thống đang thiếu dữ liệu kỹ thuật cần tự tra' };
        }
        if (evaluation?.confirmable) {
            return { css: 'customer-status-warn', text: 'Đã dựng cách hiểu; cần bạn kiểm tra trước khi dùng G-code' };
        }
        return { css: 'customer-status-block', text: 'Chưa thể tạo bản nháp an toàn từ thông tin hiện có' };
    }

    function _renderSemanticClauses(payload) {
        const clauses = Array.isArray(payload?.semantic_clause_accounting)
            ? payload.semantic_clause_accounting : [];
        if (!clauses.length) {
            return '<div style="margin-top:6px;color:var(--status-alarm)"><b>Clause accounting:</b> CHƯA NHẬN TỪ BACKEND</div>';
        }
        const rows = clauses.map(item => {
            const disposition = _escapeHtml(item.disposition || 'CHƯA CÓ');
            const binding = _escapeHtml(item.binding || '—');
            const text = _escapeHtml(item.text || '');
            const safety = item.safety_relevant ? '⚠' : '·';
            return `<tr><td>${_escapeHtml(item.clause_id || '?')}</td><td>${safety} ${text}</td><td>${disposition}</td><td>${binding}</td></tr>`;
        }).join('');
        return `<details style="margin-top:7px"><summary style="cursor:pointer"><b>Clause → binding/disposition</b></summary>
            <div style="overflow:auto;max-height:190px;margin-top:5px"><table style="width:100%;border-collapse:collapse;font-size:9px">
            <thead><tr><th>ID</th><th>Clause</th><th>Disposition</th><th>Binding</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
    }

    function _renderProcessContract(payload) {
        const contract = payload?.resolved_process_contract;
        const features = Array.isArray(contract?.features) ? contract.features : [];
        if (!features.length) {
            return '<div style="margin-top:6px;color:var(--status-alarm)"><b>ResolvedProcessContract:</b> CHƯA CÓ</div>';
        }
        const rows = features.map(item => `<tr>
            <td>${_escapeHtml(item.feature_id || '?')}</td>
            <td>${_escapeHtml(item.operation || '?')}</td>
            <td>${_escapeHtml(item.range_id || '?')}</td>
            <td>${_displayNumber(item.feed_min_mm_min)}–${_displayNumber(item.feed_max_mm_min)}</td>
            <td>${_displayNumber(item.spindle_min_rpm)}–${_displayNumber(item.spindle_max_rpm)}</td>
            <td>${_displayNumber(item.max_stepdown_mm)}</td>
        </tr>`).join('');
        return `<details style="margin-top:7px"><summary style="cursor:pointer"><b>ResolvedProcessContract dùng chung</b></summary>
            <div style="font-size:9px;margin-top:4px;color:var(--text-muted)">Nguồn: ${_escapeHtml(contract.source || '?')} · Generator: ${_escapeHtml(contract.generator_consumer || '?')} · Validator: ${_escapeHtml(contract.validator_consumer || '?')}</div>
            <div style="overflow:auto;max-height:180px;margin-top:5px"><table style="width:100%;border-collapse:collapse;font-size:9px">
            <thead><tr><th>Feature</th><th>Operation</th><th>Range</th><th>Feed</th><th>Spindle</th><th>Max step-down</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
    }

    function _renderGcodeReview(report) {
        if (!report || !Array.isArray(report.findings)) return '';
        const reviewKey = String(report.gcode_sha256 || 'review-without-hash');
        if (document.querySelector(`[data-gcode-review-key="${reviewKey}"]`)) return '';
        const metrics = report.metrics || {};
        const rows = report.findings.map(item => {
            const lines = Array.isArray(item.evidence_lines) && item.evidence_lines.length
                ? item.evidence_lines.join(', ') : '—';
            return `<tr>
                <td>${_escapeHtml(item.severity || '?')}</td>
                <td>${_escapeHtml(item.category || '?')}</td>
                <td>${_escapeHtml(item.title || item.code || '?')}</td>
                <td>${_escapeHtml(lines)}</td>
                <td>${_escapeHtml(item.recommendation || '')}</td>
            </tr>`;
        }).join('');
        const unknowns = (report.unknowns || []).map(item => `<li>${_escapeHtml(item)}</li>`).join('');
        return `<div class="gcode-review-card" data-gcode-review-key="${_escapeHtml(reviewKey)}" style="border:1px solid var(--cyan-portal);padding:8px;border-radius:4px;margin-top:5px">
            <b>READ-ONLY G-CODE OPTIMIZATION REVIEW</b>
            <div style="margin-top:4px">Mode: ${_escapeHtml(report.analysis_mode || '?')} · blocks: ${_escapeHtml(metrics.executable_lines ?? '?')} · focus: ${_escapeHtml(metrics.question_focus || 'GENERAL')}</div>
            <div style="overflow:auto;max-height:260px;margin-top:6px"><table style="width:100%;border-collapse:collapse;font-size:9px">
                <thead><tr><th>Severity</th><th>Category</th><th>Finding</th><th>Dòng</th><th>Khuyến nghị</th></tr></thead>
                <tbody>${rows || '<tr><td colspan="5">Không phát hiện finding static rõ ràng.</td></tr>'}</tbody>
            </table></div>
            ${unknowns ? `<details style="margin-top:6px"><summary>Điều chưa thể kết luận</summary><ul>${unknowns}</ul></details>` : ''}
            <div style="margin-top:6px;font-size:9px;word-break:break-all">Source SHA-256: ${_escapeHtml(report.gcode_sha256 || '')}</div>
            <div style="margin-top:5px;color:var(--status-warning)">Không sửa byte G-code; không cấp quyền máy/RUN.</div>
        </div>`;
    }

    function renderFeatureGraph(payload, token = '', rawMessage = '') {
        const spec = payload?.job_spec;
        if (!spec || !Array.isArray(spec.features)) return '';
        const evaluation = evaluateIntentContract(payload);
        const featureRows = spec.features.map(feature => {
            const id = _escapeHtml(feature.id || '?');
            const type = _escapeHtml(feature.type || 'CHƯA CÓ');
            const op = _escapeHtml(feature.operation || 'NEEDS_ROLE');
            const depth = _displayNumber(feature.depth_mm);
            return `<li><b>${id}</b> — ${type} / ${op} / depth ${depth} mm</li>`;
        }).join('');
        const ambiguities = Array.isArray(payload.ambiguities) ? payload.ambiguities : [];
        const warnings = Array.isArray(payload.warnings) ? payload.warnings : [];
        const errors = Array.isArray(payload.errors) ? payload.errors : [];
        const status = _escapeHtml(payload.status || 'CHƯA CÓ');
        const stateHtml = evaluation.confirmable
            ? '<div data-intent-state style="margin-top:5px;color:var(--status-warning)"><b>CHỜ NGƯỜI DÙNG XÁC NHẬN CÁCH HIỂU</b></div>'
            : `<div data-intent-state style="margin-top:5px;color:var(--status-alarm)"><b>CHƯA ĐỦ ĐIỀU KIỆN XÁC NHẬN:</b> ${evaluation.reasons.map(_escapeHtml).join(', ')}</div>`;
        const issueHtml = [
            ...ambiguities.map(item => `Mơ hồ: ${item}`),
            ...errors.map(item => `Lỗi: ${item}`),
            ...warnings.map(item => `Cảnh báo: ${item}`),
        ].length
            ? `<div style="margin-top:5px;color:var(--status-warning)">${[...ambiguities, ...errors, ...warnings].map(_escapeHtml).join('; ')}</div>`
            : '';
        const stock = spec.stock || {};
        const stockHtml = `<div style="margin-top:5px;">Stock: ${_displayNumber(stock.x_mm)} × ${_displayNumber(stock.y_mm)} × ${_displayNumber(stock.z_mm)} mm</div>`;
        const stepdown = spec.process_constraints?.axial_stepdown || {};
        const stepdownConflict = ambiguities.includes('conflict:process.axial_stepdown');
        const stepdownHtml = stepdown.mode === 'EXACT'
            ? `<div style="margin-top:5px;">Step-down: EXACT ${_displayNumber(stepdown.value_mm)} mm; hoàn thành lớp trước khi hạ Z</div>`
            : stepdown.mode === 'AUTO'
                ? '<div style="margin-top:5px;">Step-down: AUTO theo ResolvedProcessContract</div>'
                : '<div style="margin-top:5px;color:var(--status-alarm)">Step-down: CHƯA CÓ</div>';
        const jobHash = _escapeHtml(payload.job_spec_sha256 || 'CHƯA CÓ');
        const gcodeHash = _escapeHtml(payload.gcode_sha256 || 'CHƯA CÓ');
        const pipeline = payload.pipeline_status || {};
        const pipelineHtml = `<div style="margin-top:5px;font-size:9px">Pipeline: semantic=${_escapeHtml(pipeline.semantic || 'CHƯA CÓ')} · context=${_escapeHtml(pipeline.context || 'CHƯA CÓ')} · validation=${_escapeHtml(pipeline.validation || 'CHƯA CÓ')} · draft=${_escapeHtml(pipeline.draft || 'CHƯA CÓ')}</div>`;
        const controls = evaluation.confirmable && token
            ? `<div data-intent-controls style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">
                <button onclick="aiConfirmIntentContract('${token}')" style="font-size:9px;padding:4px 9px;border:1px solid var(--status-active);background:transparent;color:var(--status-active);border-radius:3px;cursor:pointer">✓ XÁC NHẬN ĐÚNG CÁCH HIỂU</button>
                <button onclick="aiRejectIntentContract('${token}')" style="font-size:9px;padding:4px 9px;border:1px solid var(--status-warning);background:transparent;color:var(--status-warning);border-radius:3px;cursor:pointer">↺ YÊU CẦU SỬA</button>
            </div>` : '';
        const customerStatus = _customerStatus(payload, evaluation);
        const customerFeatures = _customerFeatureCards(spec.features, ambiguities);
        const systemOwnedKeys = new Set(['tool.id', 'tool.diameter', 'safe_z', 'stock.material']);
        const unresolved = [...new Set([
            ...ambiguities.filter(item => !systemOwnedKeys.has(String(item))).map(_customerIssueText),
            ...errors.map(_customerProcessError),
        ])].filter(Boolean);
        const systemOwned = ambiguities.some(item => systemOwnedKeys.has(String(item)));
        const question = _customerQuestion(payload);
        const unsupportedDrill = errors.some(item => /END_MILL_ONLY/i.test(String(item)));
        const emptyFeatureMessage = unsupportedDrill
            ? 'Đã hiểu bạn muốn tạo lỗ, nhưng chức năng hiện tại chưa hỗ trợ nguyên công khoan.'
            : 'Chưa nhận được hình cần gia công.';
        const customerControls = evaluation.confirmable && token
            ? `<div data-intent-controls style="display:flex;gap:6px;flex-wrap:wrap;margin-top:9px">
                <button onclick="aiConfirmIntentContract('${token}')" style="font-size:10px;padding:5px 10px;border:1px solid var(--status-active);background:transparent;color:var(--status-active);border-radius:5px;cursor:pointer">✓ Đúng, dùng cách hiểu này</button>
                <button onclick="aiRejectIntentContract('${token}')" style="font-size:10px;padding:5px 10px;border:1px solid var(--status-warning);background:transparent;color:var(--status-warning);border-radius:5px;cursor:pointer">↺ Chưa đúng, sửa lại</button>
            </div>` : '';
        const primary = `<div data-customer-primary class="customer-collaboration-card">
            <div class="customer-collaboration-title">AI đang cùng bạn làm rõ sản phẩm</div>
            <div class="customer-understood">
                <div class="${customerStatus.css}">${_escapeHtml(customerStatus.text)}</div>
                <div style="margin-top:5px">Phôi: ${_displayNumber(stock.x_mm)} × ${_displayNumber(stock.y_mm)} × ${_displayNumber(stock.z_mm)} mm${stock.material ? ` · ${_escapeHtml(_customerMaterialLabel(stock.material))}` : ''}</div>
            </div>
            <div class="customer-feature-list">${customerFeatures || `<div class="customer-feature-item">${_escapeHtml(emptyFeatureMessage)}</div>`}</div>
            ${stepdown.mode === 'EXACT' && !stepdownConflict ? `<div class="customer-system-action">Mỗi lớp xuống đúng ${_displayNumber(stepdown.value_mm)} mm theo giá trị bạn đã nhập.</div>` : ''}
            ${systemOwned ? '<div class="customer-system-action">Tôi sẽ tự tra dao, vật liệu chính xác hoặc khoảng nâng dao từ nguồn dự án trước khi yêu cầu bạn nhập.</div>' : ''}
            ${unresolved.length ? `<div class="customer-system-action">Còn cần làm rõ: ${unresolved.map(_escapeHtml).join('; ')}.</div>` : ''}
            ${question ? `<div class="customer-next-question">${_escapeHtml(question)}</div>` : ''}
            ${customerControls}
        </div>`;
        const forceTechnicalOpen = _presentationMode === 'technical' || Boolean(payload?.repair_lineage_id);
        const technical = `<details class="ai-technical-view" ${forceTechnicalOpen ? 'open' : ''}>
            <summary>Chi tiết kỹ thuật</summary>
            <div class="feature-graph-card" style="border:1px solid var(--cyan-portal);padding:7px;border-radius:4px;margin-top:6px;">
                ${rawMessage ? `<pre>${_escapeHtml(rawMessage)}</pre>` : ''}
                <b>UserIntentContract / FeatureGraph</b><div style="margin-top:4px">Status: <b>${status}</b></div>${stockHtml}
                <ul style="margin:5px 0 0 18px;padding:0;">${featureRows}</ul>
                ${stepdownHtml}${pipelineHtml}${stateHtml}${issueHtml}
                ${_renderSemanticClauses(payload)}${_renderProcessContract(payload)}
                <div style="margin-top:6px;font-size:9px;word-break:break-all;">JobSpec SHA-256: ${jobHash}<br>G-code SHA-256: ${gcodeHash}</div>
                ${controls}
            </div>
        </details>`;
        const jobSpecKey = _escapeHtml(evaluation.contractKey || payload?.job_spec_sha256 || token || 'unkeyed');
        return `<div id="${token ? token + '_card' : ''}" data-job-spec-key="${jobSpecKey}">${primary}${technical}</div>`;
    }

    function _typing() {
        const d = _appendMsg('ai', '<span class="typing-dots"><span>●</span><span>●</span><span>●</span></span>', true);
        if (d) d.id = '_typing';
        return d;
    }

    function _rmTyping() { _el('_typing')?.remove(); }

    function _buildGcodeReply(cleanText, gcode, msgBubbleId, { actionsAllowed = true, blockers = [], contractToken = '' } = {}) {
        const gcEnc = encodeURIComponent(gcode || '');
        const safeText = _escapeHtml(cleanText);
        const safeGcode = _escapeHtml(gcode || '');
        const blockerHtml = blockers.length
            ? `<div style="margin-top:6px;color:var(--status-warning)"><b>Action bị khóa:</b> ${blockers.map(_escapeHtml).join('; ')}</div>` : '';
        if (!enableGcodeActions || !actionsAllowed) {
            return `${safeText}<pre>${safeGcode}</pre>${blockerHtml}`;
        }
        return `${safeText}<pre>${safeGcode}</pre>
            <div style="display:flex;gap:5px;margin-top:5px;flex-wrap:wrap;">
                <button onclick="aiCheckGCode(this,'${gcEnc}','${msgBubbleId}','${contractToken}')" style="font-size:9px;padding:2px 8px;border:1px solid var(--status-warning);background:transparent;color:var(--status-warning);border-radius:3px;cursor:pointer;">🔍 Kiểm tra G-code</button>
                <button onclick="aiSaveGCode(this,'${gcEnc}','${contractToken}')" style="font-size:9px;padding:2px 8px;border:1px solid var(--cyan-portal);background:transparent;color:var(--cyan-portal);border-radius:3px;cursor:pointer;">💾 Lưu G-Code</button>
                <button onclick="aiSendToViewer(this,'${gcEnc}','${contractToken}')" style="font-size:9px;padding:2px 8px;border:1px solid var(--status-active);background:transparent;color:var(--status-active);border-radius:3px;cursor:pointer;">👁 Preview</button>
            </div>
            <div id="${msgBubbleId}_checkResult" style="display:none;margin-top:8px;padding:6px 8px;border-radius:4px;font-size:10px;"></div>`;
    }

    function _stageAssistantPayload(payload, text) {
        const cleanText = String(text || '').replace(/```gcode[\s\S]*?```/g, '').trim();
        const evaluation = evaluateIntentContract(payload);
        const contractKey = String(evaluation.contractKey || payload?.job_spec_sha256 || '');
        if (contractKey && document.querySelector(`[data-job-spec-key="${contractKey}"]`)) {
            return { token: '', evaluation, duplicate: true };
        }
        const token = `intent_${Date.now()}_${++_intentCounter}`;
        _pendingIntentContracts.set(token, { payload, cleanText, evaluation, confirmed: false });
        const card = renderFeatureGraph(payload, token, cleanText);
        if (card) _appendMsg('ai', card, true);
        if (payload?.has_gcode && payload?.gcode) {
            const note = evaluation.confirmable
                ? '🔒 G-code đã được tạo ở backend nhưng đang bị khóa trên frontend. Hãy kiểm tra FeatureGraph, clause accounting và process contract rồi xác nhận đúng hash.'
                : '🚫 G-code không được lộ hoặc nạp vào preview vì contract chưa đủ điều kiện xác nhận.';
            _appendMsg('sys', note);
        }
        return { token, evaluation };
    }

    window.aiConfirmIntentContract = async function (token) {
        const entry = _pendingIntentContracts.get(String(token || ''));
        if (!entry) return;
        const current = evaluateIntentContract(entry.payload);
        if (!current.confirmable || current.contractKey !== entry.evaluation.contractKey) {
            _appendMsg('sys', '🚫 Không thể xác nhận: contract hoặc hash đã thay đổi/không còn hợp lệ.');
            return;
        }
        let hashEvidence;
        try {
            hashEvidence = await verifyIntentPayloadHashes(entry.payload);
        } catch (_) {
            _appendMsg('sys', '🚫 Không thể xác nhận: trình duyệt không kiểm được SHA-256 của contract.');
            return;
        }
        if (!hashEvidence.valid) {
            _appendMsg('sys', `🚫 Không thể xác nhận: ${hashEvidence.reasons.join(', ')}.`);
            return;
        }
        entry.confirmed = true;
        entry.evaluation = current;
        const card = _el(`${token}_card`);
        const state = card?.querySelector('[data-intent-state]');
        if (state) {
            state.style.color = 'var(--status-active)';
            state.innerHTML = '<b>✓ ĐÃ XÁC NHẬN ĐÚNG CẶP JOBSPEC/G-CODE HASH</b>';
        }
        const controls = card?.querySelector('[data-intent-controls]');
        if (controls) controls.style.display = 'none';
        const bubbleId = `gcBubble_${Date.now()}_${_intentCounter}`;
        _appendMsg('ai', _buildGcodeReply(
            '',
            entry.payload.gcode,
            bubbleId,
            {
                actionsAllowed: current.actionEligible,
                blockers: current.authorizationBlockers,
                contractToken: token,
            },
        ), true);
        if (current.actionEligible && typeof window.setGCodeFromAI === 'function') {
            window.setGCodeFromAI(entry.payload.gcode, {
                jobSpecSha256: entry.payload.job_spec_sha256,
                gcodeSha256: entry.payload.gcode_sha256,
                interpretationConfirmed: true,
            });
        } else if (!current.actionEligible) {
            _appendMsg('sys', '🔒 Đã xác nhận cách hiểu, nhưng G-code chưa được nạp sang Control vì còn authorization blocker.');
        }
    };

    window.aiRejectIntentContract = function (token) {
        const entry = _pendingIntentContracts.get(String(token || ''));
        if (!entry) return;
        entry.confirmed = false;
        const card = _el(`${token}_card`);
        const state = card?.querySelector('[data-intent-state]');
        if (state) {
            state.style.color = 'var(--status-warning)';
            state.innerHTML = '<b>↺ NGƯỜI DÙNG CHƯA CHẤP NHẬN CÁCH HIỂU — G-CODE VẪN KHÓA</b>';
        }
        const controls = card?.querySelector('[data-intent-controls]');
        if (controls) controls.style.display = 'none';
        const input = _el('aiIn');
        if (input) {
            input.value = `Sửa lại cách hiểu cho JobSpec ${String(entry.payload.job_spec_sha256 || '').slice(0, 12)}: `;
            input.focus();
        }
    };

    async function sendChat() {
        if (_busy) return;
        const inp = _el('aiIn');
        const btn = _el('aiBtn');
        if (!inp) return;
        const msg = inp.value.trim();
        if (!msg) return;

        _busy = true;
        if (btn) btn.disabled = true;
        inp.value = '';
        _appendMsg('user', msg);
        _typing();

        try {
            const body = { message: msg, page_context: context, presentation_mode: _presentationMode };
            if (_currentConvId) body.thread_id = _currentConvId;
            if (_imgId) { body.image_id = _imgId; _imgId = ''; }
            if (_gcodeAttachment) {
                body.gcode = _gcodeAttachment.gcode;
                body.filename = _gcodeAttachment.filename;
                body.gcode_sha256 = _gcodeAttachment.sha256;
            }
            if (_collisionRepairContext) {
                body.action = 'repair_collision';
                Object.assign(body, _collisionRepairContext);
            }
            const r = await api.post('/api/ai/chat', body);
            const id = r?.conversation_id;
            if (!id) throw new Error('Không nhận được ID');
            _setConversationId(r?.thread_id || _currentConvId || id);

            let tries = 0;
            let settled = false;
            let pollInFlight = false;
            const iv = setInterval(async () => {
                if (settled || pollInFlight) return;
                pollInFlight = true;
                tries++;
                try {
                    const d = await api.get(`/api/ai/chat/${id}`);
                    if (d.done || d.failed || tries > maxPollTries) {
                        settled = true;
                        clearInterval(iv);
                        _rmTyping();
                        const last = d.messages?.filter(m => m.role === 'assistant').pop();
                        const txt = last?.message || (d.failed ? '❌ AI thất bại' : '...');
                        if (last?.response_contract) {
                            const actionCard = _renderContextualResponse(last.response_contract);
                            if (actionCard) _appendMsg('ai', actionCard, true);
                            else _appendMsg('ai', txt);
                            if (last?.job_spec) _stageAssistantPayload(last, '');
                            if (last?.repair_lineage_id) {
                                _collisionRepairContext = null;
                                _appendMsg('sys', '🧬 Đã tạo V2/hash mới. Context collision V1 đã đóng; V2 phải xác nhận và CHECK lại.');
                            }
                        } else if (last?.gcode_review) {
                            if (txt) _appendMsg('ai', txt);
                            const card = _renderGcodeReview(last.gcode_review);
                            if (card) _appendMsg('ai', card, true);
                        } else if (last?.job_spec) {
                            _stageAssistantPayload(last, txt);
                            if (last?.repair_lineage_id) {
                                _collisionRepairContext = null;
                                _appendMsg('sys', '🧬 Đã tạo V2/hash mới. Context collision V1 đã đóng; V2 phải xác nhận và CHECK lại.');
                            }
                        } else {
                            _appendMsg('ai', txt);
                        }
                        _busy = false;
                        if (btn) btn.disabled = false;
                        if (typeof onAfterChat === 'function') onAfterChat();
                    }
                } catch (_e) {
                    settled = true;
                    clearInterval(iv); _rmTyping(); _appendMsg('ai', '❌ Lỗi nhận phản hồi');
                    _busy = false; if (btn) btn.disabled = false;
                } finally {
                    pollInFlight = false;
                }
            }, pollIntervalMs);
        } catch (e) {
            _rmTyping(); _appendMsg('ai', `❌ ${e.message}`);
            _busy = false; if (btn) btn.disabled = false;
        }
    }

    window.aiSend = sendChat;
    window.aiKeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); } };
    window.aiRefreshProvider = refreshProviderBadge;
    window.aiWatchConversation = function (conversationId, { maxTries = 1050 } = {}) {
        const id = _setConversationId(conversationId);
        if (!id) return;
        let tries = 0;
        let lastCount = 0;
        let pollInFlight = false;
        const timer = setInterval(async () => {
            if (pollInFlight) return;
            pollInFlight = true;
            tries += 1;
            try {
                const d = await api.get(`/api/ai/chat/${id}`);
                const messages = Array.isArray(d.messages) ? d.messages : [];
                for (const msg of messages.slice(lastCount)) {
                    if (msg.role === 'assistant' && msg.response_contract) {
                        const actionCard = _renderContextualResponse(msg.response_contract);
                        if (actionCard) _appendMsg('ai', actionCard, true);
                    } else if (msg.role === 'assistant' && msg.gcode_review) {
                        if (msg.message) _appendMsg('ai', msg.message);
                        const reviewCard = _renderGcodeReview(msg.gcode_review);
                        if (reviewCard) _appendMsg('ai', reviewCard, true);
                    } else if (msg.role === 'assistant' && msg.job_spec) {
                        _stageAssistantPayload(msg, msg.message || '');
                    }
                    if (msg.role === 'assistant' && msg.event_type === 'check_result') {
                        _appendMsg('ai', msg.message || 'CHECK đã hoàn tất');
                        const contract = msg.check_result || d.check_result || {};
                        if (typeof onAfterChat === 'function') {
                            try { await onAfterChat({ type: 'check_result', contract }); } catch (_) {}
                        }
                        window.dispatchEvent(new CustomEvent('cnc:check-terminal', { detail: contract }));
                    }
                }
                lastCount = Math.max(lastCount, messages.length);
                if (d.done || d.failed || tries >= maxTries) clearInterval(timer);
            } catch (_) {
                if (tries >= maxTries) clearInterval(timer);
            } finally {
                pollInFlight = false;
            }
        }, pollIntervalMs);
    };

    window.aiNewConversation = function () {
        _setConversationId(null);
        _pendingIntentContracts.clear();
        _collisionRepairContext = null;
        const messages = _el('aiMsgs');
        if (messages) {
            messages.innerHTML = '';
            _appendMsg('sys', 'Đã bắt đầu hội thoại mới. Hội thoại cũ vẫn được lưu trong History.');
            _appendMsg('ai', 'Bạn cứ nói tự nhiên. Tôi sẽ lấy đúng ngữ cảnh, trả lời điều bạn hỏi, tự xử lý phần hệ thống an toàn và chỉ hỏi phần thật sự cần bạn quyết định.');
        }
        _el('aiIn')?.focus();
    };

    async function _restoreConversation() {
        if (!_currentConvId) return;
        try {
            const data = await api.get(`/api/ai/chat/thread/${encodeURIComponent(_currentConvId)}`);
            const messages = Array.isArray(data?.messages) ? data.messages : [];
            if (!messages.length) return;
            const container = _el('aiMsgs');
            if (container) container.innerHTML = '';
            _appendMsg('sys', `Đã khôi phục hội thoại liên tục (${messages.length} tin).`);
            for (const msg of messages) {
                if (msg.role === 'assistant' && msg.response_contract) {
                    const actionCard = _renderContextualResponse(msg.response_contract);
                    if (actionCard) _appendMsg('ai', actionCard, true);
                } else if (msg.role === 'assistant' && msg.gcode_review) {
                    if (msg.message) _appendMsg('ai', msg.message);
                    const reviewCard = _renderGcodeReview(msg.gcode_review);
                    if (reviewCard) _appendMsg('ai', reviewCard, true);
                } else if (msg.role === 'assistant' && msg.job_spec) {
                    _stageAssistantPayload(msg, msg.message || '');
                } else {
                    _appendMsg(msg.role === 'user' ? 'user' : 'ai', msg.message || '');
                }
            }
        } catch (_) {
            _setConversationId(null);
        }
    }

    function _sendQuickAction(message) {
        const input = _el('aiIn');
        if (!input || _busy) return;
        input.value = message;
        sendChat();
    }

    function _installConversationControls() {
        const tools = _el('aiIn')?.closest('.ai-input-area')?.querySelector('.ai-tools');
        if (!tools || tools.querySelector('.ai-context-actions')) return;
        const group = document.createElement('div');
        group.className = 'ai-context-actions';
        const actions = [
            ['❓ Giải thích lỗi', 'Nó đang báo tôi sai gì? Hãy giải thích nguyên nhân chính và lỗi hệ quả.'],
            ['🛠 Xử lý phần thiếu', 'Còn thiếu điều kiện gì? Hãy tự sửa phần hệ thống có thể sửa và chỉ hỏi phần tôi phải quyết định.'],
            ['▶ Tiếp tục', 'Tiếp tục công việc đang chờ từ lượt trước.'],
        ];
        for (const [label, message] of actions) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'ai-upload-btn ai-context-action-btn';
            button.textContent = label;
            button.addEventListener('click', () => _sendQuickAction(message));
            group.appendChild(button);
        }
        // Optional text-edit utility retained for users who explicitly request it.
        // It is no longer injected into or required by normal conversation turns.
        const coachButton = document.createElement('button');
        coachButton.type = 'button';
        coachButton.className = 'ai-upload-btn ai-coach-btn';
        coachButton.textContent = '✍️ Sửa văn bản';
        coachButton.title = 'Tùy chọn: chỉ chỉnh câu chữ, không thực hiện công việc CNC';
        coachButton.addEventListener('click', coachDraft);
        group.appendChild(coachButton);
        tools.prepend(group);
    }

    _installConversationControls();
    _applyPresentationMode(_presentationMode);
    void _restoreConversation();

    if (enableUpload) {
        window.aiUpload = async function (ev) {
            const f = ev.target.files[0];
            if (!f) return;
            try {
                _appendMsg('sys', `📎 Đang upload ${f.name}...`);
                const fd = new FormData();
                fd.append('file', f);
                fd.append('description', 'Ảnh phôi HMI');
                const r = await api.upload('/api/ai/upload/image', fd);
                _imgId = r.image_id;
                _appendMsg('sys', `✅ Ảnh ready (${r.size_kb}KB). Nhập câu hỏi để AI phân tích.`);
            } catch (e) {
                _appendMsg('sys', `❌ Upload lỗi: ${e.message}`);
            }
            ev.target.value = '';
        };
    }

    function _confirmedIntentEntry(token, gcode) {
        const entry = _pendingIntentContracts.get(String(token || ''));
        if (!entry || entry.confirmed !== true) return null;
        const current = evaluateIntentContract(entry.payload);
        if (!current.confirmable || current.contractKey !== entry.evaluation.contractKey) return null;
        if (String(entry.payload.gcode || '') !== String(gcode || '')) return null;
        return { entry, current };
    }

    if (enableGcodeActions) {
        window.aiSaveGCode = async function (btn, gcEnc, contractToken) {
            const gc = decodeURIComponent(gcEnc || btn.getAttribute('data-g') || '');
            const confirmed = _confirmedIntentEntry(contractToken, gc);
            if (!gc || !confirmed) {
                if (btn) btn.textContent = '🚫 Chưa xác nhận';
                return;
            }
            try {
                btn.textContent = '⏳...';
                const r = await api.post('/api/gcode/save', {
                    content: gc,
                    source: 'ai_interpretation_confirmed',
                    job_spec_sha256: confirmed.entry.payload.job_spec_sha256,
                    gcode_sha256: confirmed.entry.payload.gcode_sha256,
                    interpretation_confirmed: true,
                });
                btn.textContent = `✅ ${r.gcode_id?.slice(-6)}`;
                btn.style.color = 'var(--status-active)';
                btn.style.borderColor = 'var(--status-active)';
                if (typeof onAfterChat === 'function') onAfterChat();
            } catch (e) { btn.textContent = '❌ Lỗi lưu'; }
        };

        window.aiSendToViewer = function (btn, gcEnc, contractToken) {
            const gc = decodeURIComponent(gcEnc);
            if (!_confirmedIntentEntry(contractToken, gc)) {
                if (btn) btn.textContent = '🚫 Chưa xác nhận';
                return;
            }
            // Gửi lên toolpath viewer qua DigitalTwinViewer
            const twin = new DigitalTwinViewer('toolpathFrame');
            twin.renderToolpath(gc);
            const status = _el('toolpathStatus');
            if (status) status.textContent = 'Đang preview...';
            if (btn) btn.textContent = '✅ Sent';
        };
    }

    // ── Check G-code flow (TASK 1) ───────────────────────────────────────
    window.aiCheckGCode = async function (btn, gcEnc, bubbleId, contractToken) {
        const gc = decodeURIComponent(gcEnc || '');
        const confirmed = _confirmedIntentEntry(contractToken, gc);
        if (!gc || !confirmed) {
            if (btn) btn.textContent = '🚫 Chưa xác nhận';
            return;
        }

        const resultEl = document.getElementById(bubbleId + '_checkResult');
        btn.textContent = '⏳ Đang kiểm tra...';
        btn.disabled = true;

        try {
            const r = await api.post('/api/ai/chat', {
                message: 'Kiểm tra G-code',
                action: 'check_gcode',
                gcode: gc,
                filename: 'check_gcode.nc',
                job_spec_sha256: confirmed.entry.payload.job_spec_sha256,
                job_spec_canonical_json: confirmed.entry.payload.job_spec_canonical_json,
                resolved_process_contract: confirmed.entry.payload.resolved_process_contract,
                gcode_sha256: confirmed.entry.payload.gcode_sha256,
                interpretation_confirmed: true,
                auto_repair: true,
                thread_id: _currentConvId || '',
                page_context: context,
            });
            const id = r?.conversation_id;
            if (!id) throw new Error('Không nhận được ID');
            _setConversationId(r?.thread_id || _currentConvId || id);
            const coachingCard = _renderMessageCoaching(r?.message_coaching || {}, { allowApply: true });
            if (coachingCard) _appendMsg('ai', coachingCard, true);

            let tries = 0;
            const checkMaxPollTries = Math.max(maxPollTries, 1050);
            const iv = setInterval(async () => {
                tries++;
                try {
                    const d = await api.get(`/api/ai/chat/${id}`);
                    if (d.done || d.failed) {
                        clearInterval(iv);
                        btn.textContent = '🔍 Kiểm tra lại';
                        btn.disabled = false;

                        const last = d.messages?.filter(m => m.role === 'assistant').pop();
                        const result = last?.message || '';
                        _appendMsg('ai', result || 'CHECK đã hoàn tất');

                        // Chỉ structured terminal state từ backend mới có quyền thay đổi artifact.
                        const contract = d.check_result || d.workflow_state || d.result_contract || {};
                        const repair = contract.repair || {};
                        if (repair.applied === true) {
                            confirmed.entry.confirmed = false;
                            if (typeof window.invalidateGCodeFromAI === 'function') {
                                window.invalidateGCodeFromAI(
                                    repair.original_gcode_sha256 || confirmed.entry.payload.gcode_sha256,
                                    'Static CHECK đã thay thế artifact bằng bản sửa xác định.',
                                );
                            }
                            const originalPayload = confirmed.entry.payload;
                            const repairedPayload = {
                                ...originalPayload,
                                status: 'VALIDATED_DRAFT',
                                has_gcode: true,
                                gcode: String(repair.repaired_gcode || ''),
                                gcode_sha256: String(repair.repaired_gcode_sha256 || '').toLowerCase(),
                                job_spec: repair.job_spec || originalPayload.job_spec,
                                job_spec_canonical_json: repair.job_spec_canonical_json || originalPayload.job_spec_canonical_json,
                                job_spec_sha256: repair.job_spec_sha256 || originalPayload.job_spec_sha256,
                                resolved_process_contract: repair.resolved_process_contract || originalPayload.resolved_process_contract,
                                errors: [], ambiguities: [],
                                warnings: [
                                    ...(Array.isArray(originalPayload.warnings) ? originalPayload.warnings : []),
                                    'Artifact được tái sinh sau static CHECK; phải xác nhận lại exact hash và CHECK lần hai.',
                                ],
                                pipeline_status: {
                                    semantic: 'BOUND', context: 'FOUND', validation: 'PASSED',
                                    draft: 'GENERATED', authorization: 'BLOCKED',
                                },
                                authorization_blockers: [],
                            };
                            _appendMsg('sys', '🛠️ Static CHECK đã tái sinh artifact mới. Bản cũ đã bị vô hiệu hóa; hãy xác nhận lại exact hash.');
                            _stageAssistantPayload(repairedPayload, 'Bản G-code đã sửa xác định sau static validation.');
                        }

                        if (!resultEl) {
                            window.dispatchEvent(new CustomEvent('cnc:check-terminal', { detail: contract }));
                            return;
                        }
                        resultEl.style.display = 'block';

                        // Free-form AI text/emoji không bao giờ là approval source-of-truth.
                        const approval = String(contract.approval?.state || contract.approval_state || 'UNKNOWN').toUpperCase();
                        const completion = String(contract.completion?.state || contract.terminal_state || 'UNKNOWN').toUpperCase();
                        const safeResult = _escapeHtml(result || 'Không có structured CHECK result');
                        const safeGcodeId = _escapeHtml(contract.gcode_id || '');
                        if (contract.collision_id && contract.failed_check_id) {
                            const repairCtx = _setCollisionRepairContext(contract);
                            if (repairCtx) {
                                _appendMsg('sys', `💥 Collision ${_escapeHtml(contract.collision_id)} đã bind với CHECK/hash. Hãy chat yêu cầu sửa rõ ràng, ví dụ: Giữ nguyên geometry/depth/tool và tăng Safe Z lên 8 mm.`);
                            }
                        }

                        if (approval === 'APPROVED' && completion === 'COMPLETED') {
                            resultEl.style.background = 'rgba(0,180,80,0.1)';
                            resultEl.style.border = '1px solid var(--status-active)';
                            resultEl.innerHTML = `<b style="color:var(--status-active)">✅ CHECK ĐÃ PHÊ DUYỆT</b><br><span>${safeResult}</span>
                                <div style="margin-top:6px;color:var(--text-muted)">
                                    ✅ Artifact ${safeGcodeId ? safeGcodeId.slice(-8) : ''} đã được cập nhật trong G-CODE QUEUE. Mở trang Control để Confirm/RUN.
                                </div>`;
                        } else if (['REJECTED','FAILED','COLLISION'].includes(approval) || ['REJECTED','FAILED','COLLISION'].includes(completion)) {
                            resultEl.style.background = 'rgba(220,50,50,0.1)';
                            resultEl.style.border = '1px solid var(--status-alarm)';
                            resultEl.innerHTML = `<b style="color:var(--status-alarm)">🚫 CHECK TỪ CHỐI</b><br><span>${safeResult}</span>`;
                        } else {
                            resultEl.style.background = 'rgba(200,140,0,0.1)';
                            resultEl.style.border = '1px solid var(--status-warning)';
                            resultEl.innerHTML = `<b style="color:var(--status-warning)">⏳ CHECK CHƯA CÓ TERMINAL APPROVAL</b><br><span>${safeResult}</span>`;
                        }

                        // The CHECK pipeline already saved and updated this exact
                        // artifact. Refresh consumers now; a second "save" would
                        // create a duplicate needs_check row and hide the approved row.
                        if (typeof onAfterChat === 'function') {
                            try { await onAfterChat({ type: 'check_result', contract }); } catch (_) {}
                        }
                        window.dispatchEvent(new CustomEvent('cnc:check-terminal', { detail: contract }));
                    } else if (tries >= checkMaxPollTries) {
                        clearInterval(iv);
                        btn.textContent = '🔍 Theo dõi lại';
                        btn.disabled = false;
                        if (resultEl) {
                            resultEl.style.display = 'block';
                            resultEl.style.background = 'rgba(200,140,0,0.1)';
                            resultEl.style.border = '1px solid var(--status-warning)';
                            resultEl.innerHTML = '<b style="color:var(--status-warning)">⚠️ MẤT THEO DÕI CHECK</b><br><span>Backend chưa trả terminal state trong cửa sổ theo dõi. CHECK không được coi là PASS.</span>';
                        }
                    }
                } catch (_e) {
                    clearInterval(iv);
                    btn.textContent = '🔍 Kiểm tra lại';
                    btn.disabled = false;
                    if (resultEl) {
                        resultEl.style.display = 'block';
                        resultEl.innerHTML = '<span style="color:var(--status-alarm)">❌ Lỗi kiểm tra G-code</span>';
                    }
                }
            }, pollIntervalMs);
        } catch (e) {
            btn.textContent = '🔍 Kiểm tra G-code';
            btn.disabled = false;
            if (resultEl) {
                resultEl.style.display = 'block';
                resultEl.textContent = `❌ ${e.message}`;
                resultEl.style.color = 'var(--status-alarm)';
            }
        }
    };

    // Load provider badge
    refreshProviderBadge();

    return {
        sendChat, coachDraft, attachGCode, clearGCodeAttachment,
        setCollisionRepairContext: _setCollisionRepairContext,
        clearCollisionRepairContext,
        refreshProviderBadge, fetchProviderBadge: refreshProviderBadge,
    };
}

// Export riêng để dùng trong settings