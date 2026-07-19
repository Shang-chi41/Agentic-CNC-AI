"""
cloud_backend/routes/ai_routes.py
AI Chat: tạo job, poll kết quả, lịch sử, provider status.

Flow (theo log.md):
  HMI → POST /api/ai/chat       → tạo Chat_Job (pending) trong MongoDB
  Edge AIWorker poll Chat_Jobs  → xử lý → lưu Chat_Messages (assistant)
  HMI → GET  /api/ai/chat/{id} → poll kết quả (done=True khi xong)

Endpoints:
    POST /api/ai/chat                   → tạo job AI
    GET  /api/ai/chat/{conv_id}         → poll tin nhắn + trạng thái job
    GET  /api/ai/history                → lịch sử chat (History page)
    GET  /api/ai/provider/status        → tier hiện tại cloud/local/emergency
    POST /api/ai/provider/switch        → chuyển provider (Settings page)
    POST /api/ai/upload/image           → upload ảnh phôi kèm chat
    GET  /api/ai/images                 → danh sách ảnh đã upload
"""

from __future__ import annotations

import base64
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from cloud_backend.middleware.auth import CurrentUser, OperatorUser
from cloud_backend.services.mongo_service import doc_to_dict, docs_to_list, get_col
from edge_backend.ai.attachment_contract import validated_gcode_attachment
from edge_backend.ai.image_attachment import validated_image_attachment
from edge_backend.ai.conversation_coach import analyze_user_message
from edge_backend.ai.continuous_chat_contract import ContinuousChatError, poll_scope, prepare_turn

router = APIRouter()
_VN_TZ = timezone(timedelta(hours=7))

_COL_MESSAGES = "Chat_Messages"
_COL_JOBS     = "Chat_Jobs"
_COL_IMAGES   = "Uploaded_Images"
_COL_SETTINGS = "HMI_Settings"


def _now_str() -> str:
    return datetime.now(_VN_TZ).isoformat()


# ══════════════════════════════════════════════════════════════════════════
#  CHAT
# ══════════════════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message:      str
    image_id:     str = ""
    action:       str = "chat"      # "chat" | "check_gcode"
    gcode:        str = ""          # G-code content (khi action=check_gcode)
    filename:     str = ""          # tên file G-code
    gcode_sha256: str = ""          # exact attachment identity
    job_spec_sha256: str = ""
    job_spec_canonical_json: str = ""
    resolved_process_contract: dict[str, Any] | None = None
    interpretation_confirmed: bool = False
    auto_repair: bool = True
    # Collision-bound repair context.  These fields are only hints from the
    # frontend; Edge re-reads Mongo and verifies every value fail-closed.
    base_gcode_id: str = ""
    base_gcode_sha256: str = ""
    base_version: int = 0
    failed_check_id: str = ""
    collision_id: str = ""
    thread_id: str = ""
    page_context: str = ""
    contextual_action_enabled: bool = True






class ChatCoachRequest(BaseModel):
    message: str
    has_gcode: bool = False
    collision_context: dict[str, Any] | None = None
    page_context: str = ""


@router.post("/chat/coach", summary="Sửa câu chat và chỉ ra thông tin còn thiếu")
def coach_chat_message(body: ChatCoachRequest, user: CurrentUser) -> dict:
    return analyze_user_message(
        body.message,
        has_gcode=body.has_gcode,
        collision_context=body.collision_context or {},
        page_context=body.page_context,
    )

def _validated_gcode_attachment(gcode: str, filename: str, declared_sha256: str = "") -> dict[str, str]:
    """Compatibility wrapper kept in the route for focused contract tests."""
    return validated_gcode_attachment(gcode, filename, declared_sha256)

@router.post("/chat", summary="Gửi tin nhắn tới AI")
def send_chat(body: ChatRequest, user: CurrentUser) -> dict:
    """Tạo Chat_Job để Edge AIWorker xử lý.

    Flow:
      1. Lưu tin nhắn user vào Chat_Messages
      2. Tạo job pending trong Chat_Jobs
      3. Trả về conversation_id để HMI poll

    Edge AIWorker sẽ poll Chat_Jobs, gọi AI, lưu kết quả vào
    Chat_Messages với role=assistant, đánh dấu job done.
    """
    msg = body.message.strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Tin nhắn không được trống")

    try:
        attachment = _validated_gcode_attachment(body.gcode, body.filename, body.gcode_sha256)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Continuous chat: one stable thread_id, one unique turn_id per request.
    # The returned conversation_id remains the poll identifier for backward compatibility.
    try:
        thread_id, turn_id = prepare_turn(
            requested_thread_id=body.thread_id,
            username=user["username"],
            messages_collection=get_col(_COL_MESSAGES),
            id_factory=lambda: str(ObjectId()),
        )
    except ContinuousChatError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    now = _now_str()

    # Normal chat is contextual/action-oriented.  Sentence coaching remains an
    # optional legacy endpoint and is not injected into every user turn.
    coaching: dict[str, Any] = {}

    # Lấy base64 ảnh nếu có image_id
    image_b64    = None
    image_format = "png"
    image_sha256 = ""
    if body.image_id:
        try:
            img_doc = get_col(_COL_IMAGES).find_one({"_id": ObjectId(body.image_id)})
            if img_doc:
                image_b64    = img_doc.get("file_base64")
                image_format = img_doc.get("file_extension", "png")
                image_sha256 = str(img_doc.get("sha256") or "")
                # Đánh dấu ảnh đã dùng
                get_col(_COL_IMAGES).update_one(
                    {"_id": ObjectId(body.image_id)},
                    {"$set": {"used": True}},
                )
        except Exception:
            pass

    # Lưu tin nhắn user
    get_col(_COL_MESSAGES).insert_one({
        "conversation_id": thread_id,
        "thread_id":       thread_id,
        "turn_id":         turn_id,
        "role":            "user",
        "message":         msg,
        "image_id":        body.image_id or None,
        "username":        user["username"],
        "timestamp":       now,
        "created_at":      now,
    })

    # Tạo job cho Edge AIWorker
    get_col(_COL_JOBS).insert_one({
        "conversation_id": thread_id,
        "thread_id":       thread_id,
        "turn_id":         turn_id,
        "question":        msg,
        "message_coaching": coaching,
        "contextual_action_enabled": body.contextual_action_enabled is True,
        "page_context": body.page_context,
        "action":          body.action,     # "chat" | "check_gcode"
        "gcode":           attachment["gcode"],
        "filename":        attachment["filename"],
        "gcode_sha256":    attachment["sha256"],
        "job_spec_sha256": body.job_spec_sha256,
        "job_spec_canonical_json": body.job_spec_canonical_json,
        "resolved_process_contract": body.resolved_process_contract,
        "interpretation_confirmed": body.interpretation_confirmed,
        "auto_repair": body.auto_repair,
        "base_gcode_id": body.base_gcode_id,
        "base_gcode_sha256": body.base_gcode_sha256.lower(),
        "base_version": int(body.base_version or 0),
        "failed_check_id": body.failed_check_id,
        "collision_id": body.collision_id,
        "image_base64":    image_b64,
        "image_format":    image_format,
        "image_sha256":    image_sha256,
        "status":          "pending",
        "created_by":      user["username"],
        "created_at":      now,
    })

    return {
        "status":          "ok",
        "conversation_id": turn_id,
        "thread_id":       thread_id,
        "message_coaching": coaching,
        "message":         "AI đang xử lý...",
    }


@router.get("/chat/thread/{thread_id}", summary="Khôi phục toàn bộ hội thoại liên tục")
def get_chat_thread(thread_id: str, user: CurrentUser) -> dict:
    owner_message = get_col(_COL_MESSAGES).find_one({
        "conversation_id": thread_id, "role": "user"
    })
    if owner_message and owner_message.get("username") != user["username"]:
        raise HTTPException(status_code=403, detail="Không có quyền truy cập hội thoại này")
    docs = list(
        get_col(_COL_MESSAGES).find({"conversation_id": thread_id}).sort("created_at", 1)
    )
    messages = []
    for m in docs:
        role = "assistant" if m.get("role") in ("ai", "assistant") else m.get("role", "user")
        entry = {
            "role": role,
            "message": m.get("message", ""),
            "time": m.get("timestamp", m.get("created_at", "")),
            "turn_id": m.get("turn_id", ""),
        }
        for key in (
            "event_type", "gcode_id", "check_result", "status", "job_spec",
            "job_spec_sha256", "job_spec_canonical_json", "semantic_clause_accounting",
            "resolved_process_contract", "pipeline_status", "ambiguities", "errors",
            "warnings", "setup_requirements", "authorization_blockers", "decision_record",
            "gcode_sha256", "selected_candidate_id", "selected_strategy",
            "candidate_summaries", "machine_authorized", "check_status", "run_permission",
            "gcode_review", "collision_repair", "collision_id", "failed_check_id",
            "artifact_version", "parent_gcode_id", "repair_lineage_id",
            "requires_interpretation_reconfirmation", "has_gcode", "gcode",
            "repair_changes", "message_coaching", "response_contract",
            "conversation_state", "conversation_plan", "reasoning_record",
            "reasoning_execution", "agent_skill_trace", "contextual_action",
            "interpretation_confirmed", "base_gcode_sha256", "base_version",
        ):
            if key in m:
                entry[key] = m.get(key)
        messages.append(entry)
    return {"thread_id": thread_id, "messages": messages, "count": len(messages)}


@router.get("/chat/{conv_id}", summary="Poll kết quả chat")
def poll_chat(conv_id: str, user: CurrentUser) -> dict:
    """Lấy tin nhắn của một conversation và trạng thái job.

    HMI poll endpoint này mỗi 1-2 giây cho đến khi done=True.

    Returns:
        messages: list tin nhắn (user + assistant)
        done:     True khi job đã hoàn thành (có thể dừng poll)
        failed:   True nếu job thất bại
    """
    job, message_query = poll_scope(conv_id, get_col(_COL_JOBS))
    if job and job.get("created_by") and job.get("created_by") != user["username"]:
        raise HTTPException(status_code=403, detail="Không có quyền truy cập lượt hội thoại này")
    msgs = list(
        get_col(_COL_MESSAGES).find(message_query).sort("created_at", 1)
    )

    result_msgs = []
    for m in msgs:
        role = "assistant" if m.get("role") in ("ai", "assistant") else m.get("role", "user")
        entry = {
            "role":    role,
            "message": m.get("message", ""),
            "time":    m.get("timestamp", m.get("created_at", "")),
        }
        for key in (
            "event_type", "gcode_id", "check_result", "status", "job_spec",
            "job_spec_sha256", "job_spec_canonical_json", "semantic_clause_accounting",
            "resolved_process_contract", "pipeline_status",
            "ambiguities", "errors", "warnings", "setup_requirements",
            "authorization_blockers", "decision_record", "gcode_sha256",
            "selected_candidate_id", "selected_strategy",
            "candidate_summaries", "machine_authorized", "check_status",
            "run_permission", "gcode_review", "collision_repair",
            "collision_id", "failed_check_id", "artifact_version",
            "parent_gcode_id", "repair_lineage_id",
            "requires_interpretation_reconfirmation", "has_gcode", "gcode",
            "repair_changes", "message_coaching", "response_contract",
            "conversation_state", "conversation_plan", "reasoning_record",
            "reasoning_execution", "agent_skill_trace", "contextual_action",
            "interpretation_confirmed", "base_gcode_sha256", "base_version",
        ):
            if key in m:
                entry[key] = m.get(key)
        # Trích G-code block nếu có
        if role == "assistant":
            gm = re.search(r"```gcode\n(.*?)\n```", m.get("message", ""), re.DOTALL)
            if gm:
                entry["has_gcode"] = True
                entry["gcode"]     = gm.group(1)
        result_msgs.append(entry)

    job_status = job.get("status", "pending") if job else "unknown"

    check_result = None
    for entry in reversed(result_msgs):
        if entry.get("event_type") == "check_result":
            check_result = entry.get("check_result")
            break
    if check_result is None and job:
        check_result = job.get("result")
    return {
        "messages": result_msgs,
        "done":     job_status == "done",
        "failed":   job_status == "failed",
        "status":   job_status,
        "check_result": check_result,
    }


# ══════════════════════════════════════════════════════════════════════════
#  HISTORY (HMI History page → Chat tab)
# ══════════════════════════════════════════════════════════════════════════

@router.get("/history", summary="Lịch sử chat AI")
def chat_history(
    user:   CurrentUser,
    limit:  int = Query(50, ge=1, le=500),
    search: str = Query("", description="Tìm kiếm theo nội dung"),
) -> list[dict]:
    """Lấy lịch sử chat — HMI History page → Chat tab.

    Chỉ lấy tin nhắn role=user (1 record/lượt chat) để hiển thị dạng table.
    Có thể tìm kiếm theo nội dung message.
    """
    col   = get_col(_COL_MESSAGES)
    query: dict = {"role": "user"}
    if search:
        query["message"] = {"$regex": search, "$options": "i"}

    docs = list(col.find(query).sort("created_at", -1).limit(limit))
    return docs_to_list(docs)


# ══════════════════════════════════════════════════════════════════════════
#  AI PROVIDER STATUS  (Settings page → AI Provider group)
# ══════════════════════════════════════════════════════════════════════════

@router.get("/provider/status", summary="Trạng thái AI provider hiện tại")
def provider_status(user: CurrentUser) -> dict:
    """Trạng thái tier của AI provider.

    Edge AIWorker cập nhật field này vào HMI_Settings sau mỗi lần switch.
    Cloud Backend đọc lại và trả về cho HMI.

    Returns:
        tier: cloud | local | emergency
        provider: tên provider đang dùng (gemini, claude, ollama, rule_based)
        last_switch: thời điểm switch gần nhất
    """
    col = get_col(_COL_SETTINGS)
    doc = col.find_one({"_id": "provider_status"})
    if doc:
        del doc["_id"]
        return doc

    # Fallback: lấy từ ai_provider config
    cfg = col.find_one({"_id": "ai_provider"}) or {}
    return {
        "tier":        "unknown",
        "provider":    cfg.get("primary_provider", "gemini"),
        "last_switch": None,
    }


class SwitchProviderRequest(BaseModel):
    provider: str   # "claude" | "gemini" | "openrouter" | "ollama"


@router.post("/provider/switch", summary="Chuyển AI provider thủ công")
def switch_provider(body: SwitchProviderRequest, user: OperatorUser) -> dict:
    """Operator chuyển cloud provider từ HMI Settings.

    Ghi vào HMI_Settings → Edge AIWorker poll và apply khi nhận được.
    Đây là cơ chế gián tiếp: Cloud ghi lệnh, Edge thực thi.
    """
    _VALID = {"claude", "gemini", "openrouter", "ollama", "rule_based"}
    if body.provider not in _VALID:
        raise HTTPException(
            status_code=400,
            detail=f"Provider không hợp lệ. Hợp lệ: {', '.join(sorted(_VALID))}",
        )

    col = get_col(_COL_SETTINGS)
    col.update_one(
        {"_id": "provider_switch_request"},
        {"$set": {
            "provider":    body.provider,
            "requested_by": user["username"],
            "requested_at": _now_str(),
            "applied":     False,
        }},
        upsert=True,
    )
    return {
        "status":   "ok",
        "message":  f"Yêu cầu chuyển sang '{body.provider}' đã được ghi. Edge sẽ áp dụng.",
        "provider": body.provider,
    }


# ══════════════════════════════════════════════════════════════════════════
#  IMAGE UPLOAD (kèm chat)
# ══════════════════════════════════════════════════════════════════════════

@router.post("/upload/image", summary="Upload ảnh phôi để gửi AI")
async def upload_image(
    user:        CurrentUser,
    file:        UploadFile = File(...),
    description: str        = Form(""),
) -> dict:
    """Upload ảnh phôi/dao/bề mặt — lưu base64 vào MongoDB Uploaded_Images.

    Trả về image_id để dùng trong POST /api/ai/chat body.image_id.
    """
    MAX_SIZE = 10 * 1024 * 1024  # 10 MB
    content  = await file.read()

    if len(content) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File quá lớn (tối đa 10MB)")

    try:
        attachment = validated_image_attachment(
            content, file.content_type or "", file.filename or "image"
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ext = str(attachment["extension"])
    b64 = str(attachment["base64"])
    now = _now_str()

    result = get_col(_COL_IMAGES).insert_one({
        "filename":       file.filename,
        "file_extension": ext,
        "file_size":      len(content),
        "file_base64":    b64,
        "mime_type":      attachment["mime_type"],
        "sha256":         attachment["sha256"],
        "uploaded_by":    user["username"],
        "uploaded_at":    now,
        "created_at":     now,
        "description":    description,
        "used":           False,
    })

    return {
        "status":   "ok",
        "image_id": str(result.inserted_id),
        "filename": file.filename,
        "size_kb":  round(len(content) / 1024, 1),
        "sha256": attachment["sha256"],
        "mime_type": attachment["mime_type"],
    }


@router.get("/images", summary="Danh sách ảnh đã upload")
def list_images(
    user:  CurrentUser,
    limit: int = Query(20, ge=1, le=200),
) -> list[dict]:
    """Lấy danh sách ảnh đã upload (không kèm base64 để tránh payload lớn)."""
    col  = get_col(_COL_IMAGES)
    docs = list(
        col.find({}, {"file_base64": 0})
           .sort("created_at", -1)
           .limit(limit)
    )
    return docs_to_list(docs)