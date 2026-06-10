import re
from datetime import datetime, timezone
from uuid import UUID

from app.config import settings
from app.models.plan import DayPlan, TrainingPlan
from app.models.session import EvaluationResult, SessionStatus, SessionSummary, SessionTurn
from app.services import focus_areas, interviewer, plan_adaptor, plan_store, question_generator, session_summary
from app.services import evaluator
from app.services.supabase_client import get_supabase


class SessionNotFoundError(LookupError):
    pass


class PlanNotFoundError(LookupError):
    pass


class DayNotFoundError(LookupError):
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_day_plan(plan_json: dict, day: int) -> DayPlan:
    plan = TrainingPlan.model_validate(plan_json)
    for entry in plan.schedule:
        if entry.day == day:
            return entry
    raise DayNotFoundError(f"Day {day} not found in plan (has {plan.days} days)")


def _parse_turns(raw: list | None) -> list[SessionTurn]:
    if not raw:
        return []
    return [SessionTurn.model_validate(t) for t in raw]


def _session_current_prompt(session: dict, day_plan: DayPlan) -> str:
    if session.get("current_prompt"):
        return session["current_prompt"]
    return day_plan.voice_session.prompts[0]


def start_session(candidate_id: UUID, day: int, *, adapt_plan: bool = True) -> dict:
    plan_row = plan_store.get_plan_for_candidate(candidate_id)
    if not plan_row:
        raise PlanNotFoundError(f"No plan found for candidate {candidate_id}")

    day_plan = _get_day_plan(plan_row["plan_json"], day)
    if not day_plan.voice_session.prompts:
        raise DayNotFoundError(f"Day {day} has no voice session prompts")

    target_role = plan_row["target_role"]
    try:
        opening = question_generator.generate_opening_question(
            target_role=target_role,
            day_plan=day_plan,
        )
        first_prompt = opening.question
    except Exception:
        first_prompt = day_plan.voice_session.prompts[0]

    max_turns = settings.session_max_turns

    sb = get_supabase()
    row = (
        sb.table("sessions")
        .insert(
            {
                "candidate_id": str(candidate_id),
                "plan_id": plan_row["id"],
                "day": day,
                "prompt_index": 0,
                "turn_count": 0,
                "max_turns": max_turns,
                "current_prompt": first_prompt,
                "status": SessionStatus.in_progress.value,
                "turns": [],
                "adapt_plan": adapt_plan,
                "session_mode": "interview",
                "interview_phase": "lobby",
                "interview_log": [],
            }
        )
        .execute()
    )
    session = row.data[0]
    session["adapt_plan"] = adapt_plan
    session["session_mode"] = "interview"
    session["interview_phase"] = "lobby"
    session["interview_log"] = []
    session["day_plan"] = day_plan.model_dump(mode="json")
    session["target_role"] = plan_row["target_role"]
    session["current_prompt"] = first_prompt
    session["total_prompts"] = max_turns
    return session


def get_session(session_id: UUID) -> dict:
    sb = get_supabase()
    row = sb.table("sessions").select("*").eq("id", str(session_id)).single().execute()
    if not row.data:
        raise SessionNotFoundError(f"Session {session_id} not found")
    return row.data


def _completed_sessions_for_plan(plan_id: str, exclude_session_id: str | None = None) -> list[dict]:
    sb = get_supabase()
    rows = (
        sb.table("sessions")
        .select("id, day, session_summary, turns, status")
        .eq("plan_id", plan_id)
        .eq("status", SessionStatus.completed.value)
        .order("day")
        .execute()
    )
    sessions = rows.data or []
    if exclude_session_id:
        sessions = [s for s in sessions if s.get("id") != exclude_session_id]
    return sessions


def _adapt_plan_after_completion(
    *,
    plan_id: str,
    completed_day: int,
    day_title: str,
    summary: SessionSummary,
    turns: list[SessionTurn],
    session_id: str,
) -> dict | None:
    plan_row = plan_store.get_plan_by_id(UUID(plan_id))
    if not plan_row:
        return None

    plan = TrainingPlan.model_validate(plan_row["plan_json"])
    prior = _completed_sessions_for_plan(plan_id, exclude_session_id=session_id)

    result = plan_adaptor.adapt_upcoming_days(
        plan=plan,
        completed_day=completed_day,
        completed_day_title=day_title,
        session_summary=summary,
        turns=turns,
        prior_sessions=prior,
    )
    if not result.adapted or not result.plan:
        return None

    log_entry = plan_adaptor.adaptation_log_entry(
        source_day=completed_day,
        reason=result.reason,
        updated_days=result.updated_days,
    )
    plan_store.update_plan_after_adaptation(UUID(plan_id), result.plan, log_entry)
    return {
        "adapted": True,
        "reason": result.reason,
        "updated_days": result.updated_days,
    }


def _load_day_context(session: dict) -> tuple[DayPlan, str]:
    sb = get_supabase()
    plan_row = sb.table("plans").select("target_role, plan_json").eq("id", session["plan_id"]).single().execute()
    day_plan = _get_day_plan(plan_row.data["plan_json"], session["day"])
    return day_plan, plan_row.data["target_role"]


def get_turn_context(session_id: UUID) -> dict:
    session = get_session(session_id)
    if session["status"] == SessionStatus.completed.value:
        raise ValueError("Session is already completed")

    day_plan, target_role = _load_day_context(session)
    turn_count = session.get("turn_count") or 0
    max_turns = session.get("max_turns") or settings.session_max_turns

    if turn_count >= max_turns:
        raise ValueError("No more prompts in this session")

    current_prompt = _session_current_prompt(session, day_plan)

    return {
        "day_plan": day_plan,
        "target_role": target_role,
        "current_prompt": current_prompt,
        "rubric": day_plan.voice_session.rubric,
        "prompt_index": turn_count,
        "total_prompts": max_turns,
        "turns": _parse_turns(session.get("turns")),
    }


def submit_answer(session_id: UUID, answer: str, evaluation: EvaluationResult) -> dict:
    session = get_session(session_id)
    if session["status"] == SessionStatus.completed.value:
        raise ValueError("Session is already completed")

    day_plan, target_role = _load_day_context(session)
    turn_count = session.get("turn_count") or 0
    max_turns = session.get("max_turns") or settings.session_max_turns
    current_prompt = _session_current_prompt(session, day_plan)
    turns = _parse_turns(session.get("turns"))

    prompt_source = "context" if turn_count == 0 else "adaptive"
    turn = SessionTurn(
        prompt_index=turn_count,
        prompt=current_prompt,
        answer=answer,
        evaluation=evaluation,
        prompt_source=prompt_source,
    )
    turns.append(turn)
    new_turn_count = turn_count + 1

    next_prompt: str | None = None
    next_focus: str | None = None
    summary: SessionSummary | None = None
    completed = False

    if new_turn_count >= max_turns:
        completed = True
    else:
        next_q = question_generator.generate_next_question(
            target_role=target_role,
            day_plan=day_plan,
            turns=turns,
            last_evaluation=evaluation,
            turns_completed=new_turn_count,
            max_turns=max_turns,
        )
        if next_q.should_continue and next_q.next_question.strip():
            next_prompt = next_q.next_question.strip()
            next_focus = next_q.focus
        else:
            completed = True

    new_status = SessionStatus.completed if completed else SessionStatus.in_progress
    update_payload: dict = {
        "turn_count": new_turn_count,
        "prompt_index": new_turn_count,
        "status": new_status.value,
        "turns": [t.model_dump(mode="json") for t in turns],
        "updated_at": _utc_now_iso(),
    }

    if completed:
        summary = session_summary.build_session_summary(
            target_role=target_role,
            day_title=day_plan.title,
            turns=turns,
        )
        update_payload["session_summary"] = summary.model_dump(mode="json")
        update_payload["current_prompt"] = None
    else:
        update_payload["current_prompt"] = next_prompt

    sb = get_supabase()
    sb.table("sessions").update(update_payload).eq("id", str(session_id)).execute()

    plan_adaptation = None
    adapt_plan = session.get("adapt_plan", True)
    if completed and summary and adapt_plan:
        try:
            plan_adaptation = _adapt_plan_after_completion(
                plan_id=session["plan_id"],
                completed_day=session["day"],
                day_title=day_plan.title,
                summary=summary,
                turns=turns,
                session_id=str(session_id),
            )
        except Exception:
            plan_adaptation = None

    return {
        "session_id": str(session_id),
        "session_status": new_status,
        "prompt_index": new_turn_count,
        "evaluation": evaluation,
        "next_prompt": next_prompt,
        "total_prompts": max_turns,
        "next_focus": next_focus,
        "session_summary": summary,
        "plan_adaptation": plan_adaptation,
    }


def _parse_interview_log(raw: list | None) -> list[dict]:
    if not raw:
        return []
    return [e for e in raw if isinstance(e, dict) and e.get("role") in ("coach", "candidate")]


def _candidate_text_current_round(log: list[dict]) -> str:
    parts: list[str] = []
    for entry in log:
        if entry.get("role") == "marker" and entry.get("event") == "round_end":
            parts = []
            continue
        if entry.get("role") == "candidate" and entry.get("text"):
            parts.append(entry["text"])
    return "\n\n".join(parts)


def _interviewer_name_from_session(session: dict) -> str:
    stored = (session.get("interviewer_name") or "").strip()
    if stored:
        return stored
    for entry in session.get("interview_log") or []:
        if entry.get("role") != "coach":
            continue
        text = entry.get("text") or ""
        match = re.search(r"Hi, I'm ([A-Za-z]+)", text)
        if match:
            return match.group(1)
    return "Alex"


def _append_interview_log(log: list[dict], role: str, text: str) -> list[dict]:
    updated = list(log)
    updated.append({"role": role, "text": text.strip()})
    return updated


def _complete_session_from_turns(
    session: dict,
    *,
    day_plan: DayPlan,
    target_role: str,
    turns: list[SessionTurn],
    session_id: UUID,
    interview_log: list[dict] | None = None,
) -> dict:
    summary = session_summary.build_session_summary(
        target_role=target_role,
        day_title=day_plan.title,
        turns=turns,
    )
    update_payload = {
        "turn_count": len(turns),
        "prompt_index": len(turns),
        "status": SessionStatus.completed.value,
        "turns": [t.model_dump(mode="json") for t in turns],
        "session_summary": summary.model_dump(mode="json"),
        "current_prompt": None,
        "updated_at": _utc_now_iso(),
    }
    if interview_log is not None:
        update_payload["interview_log"] = interview_log
    sb = get_supabase()
    sb.table("sessions").update(update_payload).eq("id", str(session_id)).execute()

    plan_adaptation = None
    if session.get("adapt_plan", True):
        try:
            plan_adaptation = _adapt_plan_after_completion(
                plan_id=session["plan_id"],
                completed_day=session["day"],
                day_title=day_plan.title,
                summary=summary,
                turns=turns,
                session_id=str(session_id),
            )
        except Exception:
            plan_adaptation = None

    return {
        "session_status": SessionStatus.completed,
        "prompt_index": len(turns),
        "evaluation": turns[-1].evaluation if turns else None,
        "session_summary": summary,
        "plan_adaptation": plan_adaptation,
    }


def _handle_greeting_turn(
    session: dict,
    *,
    session_id: UUID,
    day_plan: DayPlan,
    target_role: str,
    current_prompt: str,
    interview_log: list[dict],
    message: str,
    max_turns: int,
    interviewer_name: str = "Alex",
) -> dict:
    reply = interviewer.generate_greeting_reply(
        target_role=target_role,
        day_plan=day_plan,
        first_question=current_prompt,
        conversation=interview_log,
        candidate_message=message,
        interviewer_name=interviewer_name,
    )

    interview_log = _append_interview_log(interview_log, "coach", reply.coach_message)
    coach_messages = [reply.coach_message]
    new_phase = "greeting"
    action = reply.action

    if reply.action == "begin_interview":
        new_phase = "interview"
        action = "begin_interview"

    sb = get_supabase()
    sb.table("sessions").update(
        {
            "interview_phase": new_phase,
            "interview_log": interview_log,
            "updated_at": _utc_now_iso(),
        }
    ).eq("id", str(session_id)).execute()

    return {
        "session_id": str(session_id),
        "session_status": SessionStatus.in_progress,
        "interview_phase": new_phase,
        "coach_messages": coach_messages,
        "action": action,
        "conversation": _parse_interview_log(interview_log),
        "round_index": 0,
        "total_rounds": max_turns,
        "evaluation": None,
        "session_summary": None,
        "plan_adaptation": None,
    }


def end_interview_session(session_id: UUID) -> dict:
    session = get_session(session_id)
    if session["status"] == SessionStatus.completed.value:
        raise ValueError("Session is already completed")

    day_plan, target_role = _load_day_context(session)
    turn_count = session.get("turn_count") or 0
    max_turns = session.get("max_turns") or settings.session_max_turns
    turns = _parse_turns(session.get("turns"))
    interview_log = list(session.get("interview_log") or [])
    phase = session.get("interview_phase") or "lobby"
    current_prompt = _session_current_prompt(session, day_plan)
    answer_feedback = None
    feedback_label = ""
    feedback_skipped = False

    if phase == "interview" and len(turns) == turn_count:
        round_answer = _candidate_text_current_round(interview_log)
        if round_answer.strip():
            evaluation = evaluator.evaluate_answer(
                target_role=target_role,
                day_title=day_plan.title,
                prompt=current_prompt,
                rubric=day_plan.voice_session.rubric,
                answer=round_answer,
            )
            answer_feedback, feedback_label, feedback_skipped = evaluator.answer_feedback_for_client(
                evaluation, label=f"Topic {turn_count + 1} complete"
            )
            prompt_source = "context" if turn_count == 0 else "adaptive"
            turns.append(
                SessionTurn(
                    prompt_index=turn_count,
                    prompt=current_prompt,
                    answer=round_answer,
                    evaluation=evaluation,
                    prompt_source=prompt_source,
                )
            )
            interview_log.append({"role": "marker", "event": "round_end"})

    closing = (
        "Alright, we'll wrap up here. Thanks for your time — here is how you did today."
        if turns
        else "Thanks for joining today. We wrapped up before the formal questions — try again when you have more time."
    )
    interview_log = _append_interview_log(interview_log, "coach", closing)

    done = _complete_session_from_turns(
        session,
        day_plan=day_plan,
        target_role=target_role,
        turns=turns,
        session_id=session_id,
        interview_log=interview_log,
    )

    sb = get_supabase()
    sb.table("sessions").update(
        {"interview_phase": "interview", "updated_at": _utc_now_iso()}
    ).eq("id", str(session_id)).execute()

    return {
        "session_id": str(session_id),
        "session_status": SessionStatus.completed,
        "interview_phase": "interview",
        "coach_messages": [closing],
        "action": "advance",
        "conversation": _parse_interview_log(interview_log),
        "round_index": len(turns),
        "total_rounds": max_turns,
        "evaluation": done["evaluation"],
        "answer_feedback": answer_feedback,
        "feedback_label": feedback_label,
        "feedback_skipped": feedback_skipped,
        "session_summary": done["session_summary"],
        "plan_adaptation": done.get("plan_adaptation"),
        "turns": turns,
    }


def begin_interview(session_id: UUID, *, interviewer_name: str = "Alex") -> dict:
    session = get_session(session_id)
    if session["status"] == SessionStatus.completed.value:
        raise ValueError("Session is already completed")

    phase = session.get("interview_phase") or "lobby"
    if phase not in ("lobby", "greeting"):
        raise ValueError("Interview has already started")

    day_plan, target_role = _load_day_context(session)
    current_prompt = _session_current_prompt(session, day_plan)
    max_turns = session.get("max_turns") or settings.session_max_turns

    greeting = interviewer.generate_opening_greeting(
        target_role=target_role,
        day_plan=day_plan,
        interviewer_name=interviewer_name,
    )
    interview_log = _append_interview_log([], "coach", greeting)

    sb = get_supabase()
    sb.table("sessions").update(
        {
            "interview_phase": "greeting",
            "interviewer_name": interviewer_name,
            "interview_log": interview_log,
            "updated_at": _utc_now_iso(),
        }
    ).eq("id", str(session_id)).execute()

    return {
        "session_id": str(session_id),
        "session_status": SessionStatus.in_progress,
        "interview_phase": "greeting",
        "coach_messages": [greeting],
        "conversation": _parse_interview_log(interview_log),
        "topic_preview": current_prompt,
        "total_rounds": max_turns,
    }


def submit_interview_turn(
    session_id: UUID, candidate_message: str, *, interviewer_name: str | None = None
) -> dict:
    session = get_session(session_id)
    if interviewer_name and interviewer_name.strip():
        session["interviewer_name"] = interviewer_name.strip()
    if session["status"] == SessionStatus.completed.value:
        raise ValueError("Session is already completed")

    message = candidate_message.strip()
    if not message:
        raise ValueError("Empty message")

    phase = session.get("interview_phase") or "lobby"
    if phase == "lobby":
        raise ValueError("Tap the mic to join the interview first")

    day_plan, target_role = _load_day_context(session)
    turn_count = session.get("turn_count") or 0
    max_turns = session.get("max_turns") or settings.session_max_turns
    current_prompt = _session_current_prompt(session, day_plan)
    turns = _parse_turns(session.get("turns"))
    interview_log = list(session.get("interview_log") or [])

    interview_log = _append_interview_log(interview_log, "candidate", message)

    if phase == "greeting":
        return _handle_greeting_turn(
            session,
            session_id=session_id,
            day_plan=day_plan,
            target_role=target_role,
            current_prompt=current_prompt,
            interview_log=interview_log,
            message=message,
            max_turns=max_turns,
            interviewer_name=_interviewer_name_from_session(session),
        )

    reply = interviewer.generate_interviewer_reply(
        target_role=target_role,
        day_plan=day_plan,
        current_question=current_prompt,
        rubric=day_plan.voice_session.rubric,
        conversation=interview_log,
        candidate_message=message,
        round_index=turn_count,
        total_rounds=max_turns,
    )

    interview_log = _append_interview_log(interview_log, "coach", reply.coach_message)

    evaluation = None
    answer_feedback = None
    feedback_label = ""
    feedback_skipped = False
    session_status = SessionStatus.in_progress
    session_summary_obj: SessionSummary | None = None
    plan_adaptation = None
    coach_messages = [reply.coach_message]
    topic_num = turn_count + 1

    if reply.action == "advance":
        round_answer = _candidate_text_current_round(interview_log)
        evaluation = evaluator.evaluate_answer(
            target_role=target_role,
            day_title=day_plan.title,
            prompt=current_prompt,
            rubric=day_plan.voice_session.rubric,
            answer=round_answer,
        )
        answer_feedback, feedback_label, feedback_skipped = evaluator.answer_feedback_for_client(
            evaluation, label=f"Topic {topic_num} complete"
        )
        prompt_source = "context" if turn_count == 0 else "adaptive"
        turns.append(
            SessionTurn(
                prompt_index=turn_count,
                prompt=current_prompt,
                answer=round_answer,
                evaluation=evaluation,
                prompt_source=prompt_source,
            )
        )
        interview_log.append({"role": "marker", "event": "round_end"})
        new_turn_count = turn_count + 1

        if new_turn_count >= max_turns:
            done = _complete_session_from_turns(
                session,
                day_plan=day_plan,
                target_role=target_role,
                turns=turns,
                session_id=session_id,
                interview_log=interview_log,
            )
            session_status = done["session_status"]
            session_summary_obj = done["session_summary"]
            plan_adaptation = done.get("plan_adaptation")
            evaluation = done["evaluation"]
            answer_feedback, feedback_label, feedback_skipped = evaluator.answer_feedback_for_client(
                evaluation, label=f"Topic {topic_num} complete"
            )
        else:
            next_q = question_generator.generate_next_question(
                target_role=target_role,
                day_plan=day_plan,
                turns=turns,
                last_evaluation=evaluation,
                turns_completed=new_turn_count,
                max_turns=max_turns,
            )
            if next_q.should_continue and next_q.next_question.strip():
                next_prompt = next_q.next_question.strip()
                interview_log = _append_interview_log(interview_log, "coach", next_prompt)
                coach_messages.append(next_prompt)
                sb = get_supabase()
                sb.table("sessions").update(
                    {
                        "turn_count": new_turn_count,
                        "prompt_index": new_turn_count,
                        "turns": [t.model_dump(mode="json") for t in turns],
                        "current_prompt": next_prompt,
                        "interview_log": interview_log,
                        "updated_at": _utc_now_iso(),
                    }
                ).eq("id", str(session_id)).execute()
            else:
                done = _complete_session_from_turns(
                    session,
                    day_plan=day_plan,
                    target_role=target_role,
                    turns=turns,
                    session_id=session_id,
                    interview_log=interview_log,
                )
                session_status = done["session_status"]
                session_summary_obj = done["session_summary"]
                plan_adaptation = done.get("plan_adaptation")
                evaluation = done["evaluation"]
                answer_feedback, feedback_label, feedback_skipped = evaluator.answer_feedback_for_client(
                    evaluation, label=f"Topic {topic_num} complete"
                )
    else:
        quick_eval = evaluator.evaluate_answer_quick(
            target_role=target_role,
            day_title=day_plan.title,
            prompt=current_prompt,
            rubric=day_plan.voice_session.rubric,
            answer=message,
        )
        answer_feedback, feedback_label, feedback_skipped = evaluator.answer_feedback_for_client(
            quick_eval, label=f"Topic {topic_num} · your reply"
        )
        sb = get_supabase()
        sb.table("sessions").update(
            {"interview_log": interview_log, "updated_at": _utc_now_iso()}
        ).eq("id", str(session_id)).execute()

    return {
        "session_id": str(session_id),
        "session_status": session_status,
        "interview_phase": "interview",
        "coach_messages": coach_messages,
        "action": reply.action,
        "conversation": _parse_interview_log(interview_log),
        "round_index": turn_count + (1 if reply.action == "advance" else 0),
        "total_rounds": max_turns,
        "evaluation": evaluation,
        "answer_feedback": answer_feedback,
        "feedback_label": feedback_label,
        "feedback_skipped": feedback_skipped,
        "session_summary": session_summary_obj,
        "plan_adaptation": plan_adaptation,
        "turns": turns if session_status == SessionStatus.completed else None,
    }


def get_session_detail(session_id: UUID) -> dict:
    session = get_session(session_id)
    day_plan, target_role = _load_day_context(session)
    turn_count = session.get("turn_count") or 0
    max_turns = session.get("max_turns") or settings.session_max_turns
    current_prompt = None
    if session["status"] == SessionStatus.in_progress.value and turn_count < max_turns:
        current_prompt = _session_current_prompt(session, day_plan)

    return {
        "session_id": str(session_id),
        "candidate_id": session["candidate_id"],
        "plan_id": session["plan_id"],
        "day": session["day"],
        "title": day_plan.title,
        "reading": day_plan.reading.model_dump(mode="json"),
        "status": session["status"],
        "prompt_index": turn_count,
        "total_prompts": max_turns,
        "current_prompt": current_prompt,
        "turns": session.get("turns") or [],
        "target_role": target_role,
        "session_summary": session.get("session_summary"),
        "session_mode": session.get("session_mode", "interview"),
        "interview_log": _parse_interview_log(session.get("interview_log")),
    }


def get_candidate_progress(candidate_id: UUID) -> dict:
    plan_row = plan_store.get_plan_for_candidate(candidate_id)
    if not plan_row:
        raise PlanNotFoundError(f"No plan found for candidate {candidate_id}")

    plan = TrainingPlan.model_validate(plan_row["plan_json"])
    sb = get_supabase()
    rows = (
        sb.table("sessions")
        .select("day, status, turn_count, max_turns, session_summary, updated_at, turns")
        .eq("candidate_id", str(candidate_id))
        .order("updated_at", desc=True)
        .execute()
    )
    all_sessions = rows.data or []

    by_day: dict[int, list[dict]] = {}
    for row in all_sessions:
        by_day.setdefault(row["day"], []).append(row)

    days = []
    for entry in plan.schedule:
        day_sessions = by_day.get(entry.day, [])
        attempts = len(day_sessions)
        completed_sessions = [s for s in day_sessions if s["status"] == SessionStatus.completed.value]
        latest = day_sessions[0] if day_sessions else None

        best_score = None
        for sess in completed_sessions:
            sm = sess.get("session_summary") or {}
            avg = sm.get("average_score")
            if avg is not None:
                best_score = avg if best_score is None else max(best_score, avg)

        if not latest:
            status = "not_started"
            avg = None
        elif latest["status"] == SessionStatus.in_progress.value:
            status = "in_progress"
            avg = None
        else:
            status = "completed"
            sm = latest.get("session_summary") or {}
            avg = sm.get("average_score")

        days.append(
            {
                "day": entry.day,
                "title": entry.title,
                "status": status,
                "average_score": avg,
                "best_score": best_score,
                "attempts": attempts,
                "can_retry": status == "completed",
                "personalized": entry.personalized,
                "adapted_from_day": entry.adapted_from_day,
            }
        )

    return {
        "candidate_id": str(candidate_id),
        "target_role": plan_row["target_role"],
        "total_days": plan.days,
        "days": days,
        "focus_areas": focus_areas.compute_focus_areas(all_sessions),
    }
