from datetime import datetime, timezone
from uuid import UUID

from app.models.plan import TrainingPlan
from app.models.resume import ParsedResume
from app.services.supabase_client import get_supabase


def create_candidate() -> UUID:
    sb = get_supabase()
    row = sb.table("candidates").insert({}).execute()
    return UUID(row.data[0]["id"])


def save_resume(
    candidate_id: UUID,
    *,
    raw_text: str,
    file_path: str | None,
    parsed: ParsedResume | None = None,
) -> UUID:
    sb = get_supabase()
    payload: dict = {
        "candidate_id": str(candidate_id),
        "raw_text": raw_text,
        "file_path": file_path,
    }
    if parsed is not None:
        payload["parsed_json"] = parsed.model_dump(mode="json")
    row = sb.table("resumes").insert(payload).execute()
    return UUID(row.data[0]["id"])


def update_resume_parsed(resume_id: UUID, parsed: ParsedResume) -> None:
    sb = get_supabase()
    sb.table("resumes").update({"parsed_json": parsed.model_dump(mode="json")}).eq("id", str(resume_id)).execute()


def get_resume(resume_id: UUID) -> dict:
    sb = get_supabase()
    row = sb.table("resumes").select("*").eq("id", str(resume_id)).single().execute()
    return row.data


def save_plan(candidate_id: UUID, plan: TrainingPlan) -> UUID:
    sb = get_supabase()
    row = (
        sb.table("plans")
        .insert(
            {
                "candidate_id": str(candidate_id),
                "target_role": plan.target_role,
                "days": plan.days,
                "plan_json": plan.model_dump(mode="json"),
            }
        )
        .execute()
    )
    return UUID(row.data[0]["id"])


def get_plan_for_candidate(candidate_id: UUID) -> dict | None:
    sb = get_supabase()
    rows = (
        sb.table("plans")
        .select("*")
        .eq("candidate_id", str(candidate_id))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not rows.data:
        return None
    return rows.data[0]


def get_plan_by_id(plan_id: UUID) -> dict | None:
    sb = get_supabase()
    row = sb.table("plans").select("*").eq("id", str(plan_id)).single().execute()
    return row.data


def update_plan_after_adaptation(
    plan_id: UUID,
    plan: TrainingPlan,
    log_entry: dict,
) -> None:
    sb = get_supabase()
    current = get_plan_by_id(plan_id)
    if not current:
        raise ValueError(f"Plan {plan_id} not found")

    log = list(current.get("adaptation_log") or [])
    log.append(log_entry)

    sb.table("plans").update(
        {
            "plan_json": plan.model_dump(mode="json"),
            "adaptation_log": log,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", str(plan_id)).execute()
