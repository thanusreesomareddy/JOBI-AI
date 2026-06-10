import json



import anthropic



from app.config import settings

from app.models.plan import DayPlan

from app.services.llm_json import extract_tool_input, parse_json_text, repair_json_with_claude



GREETING_SYSTEM = """You are a warm, professional interviewer meeting the candidate before the formal interview.



Use the interviewer_reply tool after each candidate message.



Rules:

- Phase is GREETING — do NOT ask formal interview questions yet

- Your name is EXACTLY interviewer_name from the payload — never claim a different name

- If the candidate uses a similar spelling (e.g. Sara vs Sarah), accept it warmly — do not correct them to another name

- Be conversational: ask how they're doing, if they're ready, small pleasant chat

- Acknowledge naturally in full sentences (e.g. "Yeah, that makes sense" or "I hear you") — never standalone filler like "mm-hmm"

- Keep coach_message to 1-3 sentences; spoken aloud

- action=probe: continue greeting / small talk / check readiness

- action=begin_interview: candidate is ready — give a brief warm transition, then ask the first_question exactly (rephrase naturally but keep the intent)

- Do not give scores or coaching feedback"""



INTERVIEW_SYSTEM = """You are a professional hiring manager running a LIVE job interview.



Use the interviewer_reply tool after each candidate message.



Rules:

- Sound natural and conversational — like a real interviewer, not a quiz app

- Open with a brief natural acknowledgment in a full sentence when appropriate — never standalone "mm-hmm" or spelled-out fillers

- Keep coach_message to 1-4 sentences; spoken aloud

- If the answer is shallow, vague, or missing key parts: action=probe and ask a specific follow-up

- If the candidate answered well enough for this topic: action=advance

- You may acknowledge, challenge, or clarify — react to what they actually said

- Do not give scores or coaching feedback during the interview — stay in character

- Do not repeat questions already asked in the conversation"""



INTERVIEW_TOOL = {

    "name": "interviewer_reply",

    "description": "Reply as the live interviewer.",

    "input_schema": {

        "type": "object",

        "properties": {

            "coach_message": {"type": "string"},

            "action": {

                "type": "string",

                "enum": ["probe", "advance", "begin_interview"],

            },

        },

        "required": ["coach_message", "action"],

    },

}





class InterviewerReply:

    def __init__(self, coach_message: str, action: str):

        self.coach_message = coach_message.strip()

        self.action = action





def _call_interviewer(

    *,

    system: str,

    user_content: str,

    allowed_actions: tuple[str, ...],

    default_action: str = "probe",

) -> InterviewerReply:

    if not settings.anthropic_configured:

        raise RuntimeError("Anthropic is not configured. Set ANTHROPIC_API_KEY in .env")



    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    message = client.messages.create(

        model=settings.anthropic_model,

        max_tokens=1024,

        system=system,

        tools=[INTERVIEW_TOOL],

        tool_choice={"type": "tool", "name": "interviewer_reply"},

        messages=[{"role": "user", "content": user_content}],

    )



    try:

        data = extract_tool_input(message, "interviewer_reply")

    except ValueError:

        block = message.content[0]

        if block.type != "text":

            raise ValueError("Unexpected interviewer response") from None

        try:

            data = parse_json_text(block.text)

        except json.JSONDecodeError as e:

            data = repair_json_with_claude(client, block.text, str(e))



    action = str(data.get("action", default_action)).lower()

    if action not in allowed_actions:

        action = default_action



    coach_message = str(data.get("coach_message", "")).strip()

    if not coach_message:

        coach_message = "Tell me a bit more about that." if action == "probe" else "Thanks — let's move on."



    return InterviewerReply(coach_message=coach_message, action=action)





def generate_opening_greeting(

    *,

    target_role: str,

    day_plan: DayPlan,

    interviewer_name: str = "Alex",

) -> str:

    """Short scripted greeting when the candidate joins — no LLM latency on join."""

    return (

        f"Hi, I'm {interviewer_name}. I'll be your practice interviewer today "

        f"for {day_plan.title}. We'll focus on skills for a {target_role} role. "

        f"Take a breath — when you're ready, just say hello or let me know you're set to begin."

    )





def generate_greeting_reply(

    *,

    target_role: str,

    day_plan: DayPlan,

    first_question: str,

    conversation: list[dict],

    candidate_message: str,

    interviewer_name: str = "Alex",

) -> InterviewerReply:

    payload = {

        "interviewer_name": interviewer_name,

        "target_role": target_role,

        "day_title": day_plan.title,

        "first_question": first_question,

        "conversation": conversation[-20:],

        "candidate_message": candidate_message,

    }

    return _call_interviewer(

        system=GREETING_SYSTEM,

        user_content=f"Candidate just said:\n{candidate_message}\n\n{json.dumps(payload, indent=2)}",

        allowed_actions=("probe", "begin_interview"),

        default_action="probe",

    )





def generate_interviewer_reply(

    *,

    target_role: str,

    day_plan: DayPlan,

    current_question: str,

    rubric: str,

    conversation: list[dict],

    candidate_message: str,

    round_index: int,

    total_rounds: int,

) -> InterviewerReply:

    payload = {

        "target_role": target_role,

        "day_title": day_plan.title,

        "current_question": current_question,

        "rubric": rubric,

        "round": f"{round_index + 1} of {total_rounds}",

        "conversation": conversation[-20:],

        "candidate_message": candidate_message,

    }

    return _call_interviewer(

        system=INTERVIEW_SYSTEM,

        user_content=f"Candidate just said:\n{candidate_message}\n\n{json.dumps(payload, indent=2)}",

        allowed_actions=("probe", "advance"),

        default_action="probe",

    )


