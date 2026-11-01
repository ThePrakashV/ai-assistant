import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.llm import ChatSession
from app.memory.long_term import FORGET_RE, RECALL_RE, REMEMBER_RE
from app.nlu.classifier import IntentClassifier
from app.nlu.entities import extract_entities
from app.nlu.intents import INTENT_SLOTS
from app.skills.context import SkillContext
from app.skills.registry import GUARDS, SKILLS

# Indha skills ku LLM entity extraction thevai illa (skill thaane text paathukkum). ~1 sec save.
SKIP_EXTRACTION = {"time_date", "assistant_settings", "play_music", "smart_home"}

# Keyword override: user explicit ah indha words sonna, embedding enna sonnaalum idha nambu.
# (Order mukkiyam: modhal match aanadhu win. "remind" modhalil, appuram "timer".)
_DURATION = r"\d+\s*(?:seconds?|secs?|minutes?|mins?|hours?|hrs?)"
FORCED_INTENTS = {
    "set_reminder": re.compile(r"\b(remind me|remind|reminder|alarm|wake me up)\b", re.IGNORECASE),
    # "timer" word illaamalum: "set alert on 30 sec", "start 5 minutes" -> timer
    "set_timer": re.compile(
        r"\b(timer|countdown)\b|\b(?:set|start)\b.*\b" + _DURATION + r"\b", re.IGNORECASE
    ),
    "web_search": re.compile(r"\b(search for|search the web|search online|google|look ?up|wikipedia)\b", re.IGNORECASE),
}


def forced_intent(text: str) -> str | None:
    for intent, pattern in FORCED_INTENTS.items():
        if pattern.search(text):
            return intent
    return None


class AgentState(TypedDict):
    """Flowchart la box to box poga pora 'form'. Ovvoru node idha update pannum."""

    text: str
    intent: str
    confidence: float
    entities: dict
    route: str            # "skill" illa "chat"
    reply: str | None
    skill: str | None     # edha skill answer pannichu (illa None)
    trace: list[str]      # enna nadandhuchu nu step by step (Phase 9 monitoring ku)
    timings: dict


@dataclass
class AgentResult:
    text: str
    reply: str
    intent: str
    confidence: float
    route: str
    entities: dict
    trace: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)


class NovaAgent:
    """Receptionist + flowchart. handle(text) -> AgentResult."""

    def __init__(self, session_id: str = "agent", ctx: SkillContext | None = None) -> None:
        self.ctx = ctx or SkillContext()
        self.session = ChatSession(session_id=session_id)  # short-term + long-term memory
        self.classifier = IntentClassifier()
        self.graph = self._build_graph()

    # ---------- Flowchart definition ----------
    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("understand", self._understand)
        builder.add_node("run_skill", self._run_skill)
        builder.add_node("chat", self._chat)

        builder.add_edge(START, "understand")
        builder.add_conditional_edges(
            "understand",
            lambda state: state["route"],
            {"skill": "run_skill", "chat": "chat"},
        )
        builder.add_conditional_edges(
            "run_skill",
            lambda state: "chat" if state["reply"] is None else "done",
            {"chat": "chat", "done": END},
        )
        builder.add_edge("chat", END)
        return builder.compile()

    # ---------- Node 1: understand ----------
    async def _understand(self, state: AgentState) -> dict:
        text = state["text"]
        started = time.perf_counter()
        trace = list(state["trace"])

        def done(intent: str, confidence: float, entities: dict, route: str) -> dict:
            timings = {**state["timings"], "understand_ms": round((time.perf_counter() - started) * 1000)}
            return {
                "intent": intent,
                "confidence": confidence,
                "entities": entities,
                "route": route,
                "trace": trace,
                "timings": timings,
            }

        # "Remember that..." maadhiri memory commands skill ku pogakoodaadhu (reminder nu thappa aagidum)
        clean = text.strip()
        if REMEMBER_RE.match(clean) or FORGET_RE.match(clean) or RECALL_RE.match(clean):
            trace.append("memory command -> chat")
            return done("memory_command", 1.0, {}, "chat")

        # Explicit keyword irundha embedding ah nambaama direct intent
        forced = forced_intent(text)
        if forced:
            intent, confidence = forced, 1.0
            trace.append(f"keyword -> intent={intent}")
        else:
            intent, confidence, _ = await asyncio.to_thread(self.classifier.classify, text)
            trace.append(f"intent={intent} ({confidence})")

        if intent not in SKILLS:
            trace.append("no skill for this intent -> chat")
            return done(intent, confidence, {}, "chat")

        guard = GUARDS.get(intent)
        if guard and not guard.search(text):
            trace.append("guard blocked (keyword illa) -> chat")
            return done(intent, confidence, {}, "chat")

        entities: dict = {}
        if intent in INTENT_SLOTS and intent not in SKIP_EXTRACTION:
            entities = await extract_entities(intent, text)
            trace.append(f"entities={entities}")

        return done(intent, confidence, entities, "skill")

    # ---------- Node 2: run_skill ----------
    async def _run_skill(self, state: AgentState) -> dict:
        intent = state["intent"]
        started = time.perf_counter()
        trace = list(state["trace"])
        reply: str | None = None

        try:
            reply = await SKILLS[intent](state["text"], state["entities"], self.ctx)
        except Exception as exc:  # skill crash aanaalum assistant crash aagaadhu
            trace.append(f"skill error: {exc}")

        timings = {**state["timings"], "skill_ms": round((time.perf_counter() - started) * 1000)}

        if reply is None:
            trace.append("skill could not handle -> chat")
            return {"reply": None, "trace": trace, "timings": timings}

        # Skill reply kooda conversation history la save pannanum (apparam "adhu enna?" nu kettaa Nova ku theriyum)
        self.session.short.append("user", state["text"])
        self.session.short.append("assistant", reply)
        trace.append(f"skill:{intent} answered")
        return {"reply": reply, "skill": intent, "trace": trace, "timings": timings}

    # ---------- Node 3: chat (LLM + memory) ----------
    async def _chat(self, state: AgentState) -> dict:
        started = time.perf_counter()
        trace = list(state["trace"])
        reply = ""

        try:
            async for token in self.session.stream_reply(state["text"]):
                reply += token
        except Exception as exc:
            trace.append(f"chat error: {exc}")
            reply = "Sorry, I could not reach my language model."

        timings = {**state["timings"], "chat_ms": round((time.perf_counter() - started) * 1000)}
        trace.append("chat answered")
        return {"reply": reply.strip(), "skill": None, "trace": trace, "timings": timings}

    # ---------- Public API ----------
    async def handle(self, text: str) -> AgentResult:
        initial: AgentState = {
            "text": text,
            "intent": "",
            "confidence": 0.0,
            "entities": {},
            "route": "chat",
            "reply": None,
            "skill": None,
            "trace": [],
            "timings": {},
        }
        final: dict[str, Any] = await self.graph.ainvoke(initial)

        route = f"skill:{final['skill']}" if final.get("skill") else "chat"
        return AgentResult(
            text=text,
            reply=final["reply"] or "",
            intent=final["intent"],
            confidence=final["confidence"],
            route=route,
            entities=final["entities"],
            trace=final["trace"],
            timings=final["timings"],
        )