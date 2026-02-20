from typing import Dict, Any, List, AsyncGenerator, Optional
import json
import logging
from app.domain.models.plan import Plan, Step
from app.domain.models.message import Message
from app.domain.services.agents.base import BaseAgent
from app.domain.models.memory import Memory
from app.domain.external.llm import LLM
from app.domain.services.prompts.system import SYSTEM_PROMPT
from app.domain.services.prompts.planner import (
    CREATE_PLAN_PROMPT, 
    UPDATE_PLAN_PROMPT,
    PLANNER_SYSTEM_PROMPT
)
from app.domain.models.event import (
    BaseEvent,
    PlanEvent,
    PlanStatus,
    ErrorEvent,
    MessageEvent,
    DoneEvent,
)
from app.domain.external.sandbox import Sandbox
from app.domain.services.tools.base import BaseTool
from app.domain.services.tools.file import FileTool
from app.domain.services.tools.shell import ShellTool
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.utils.json_parser import JsonParser

logger = logging.getLogger(__name__)

class PlannerAgent(BaseAgent):
    """
    Planner agent class, defining the basic behavior of planning
    """

    name: str = "planner"
    system_prompt: str = SYSTEM_PROMPT + PLANNER_SYSTEM_PROMPT
    format: Optional[str] = "json_object"
    tool_choice: Optional[str] = "none"

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        llm: LLM,
        tools: List[BaseTool],
        json_parser: JsonParser,
    ):
        super().__init__(
            agent_id=agent_id,
            agent_repository=agent_repository,
            llm=llm,
            json_parser=json_parser,
            tools=tools,
        )


    async def create_plan(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        message = CREATE_PLAN_PROMPT.format(
            message=message.message,
            attachments="\n".join(message.attachments)
        )
        async for event in self.execute(message):
            if isinstance(event, MessageEvent):
                logger.info(event.message)
                try:
                    parsed_response = await self.json_parser.parse(event.message)
                    if isinstance(parsed_response, str):
                        parsed_response = {"message": parsed_response, "goal": "", "title": "", "steps": []}
                    plan = Plan.model_validate(parsed_response)
                except Exception as e:
                    logger.error(f"Failed to parse plan response: {e}")
                    plan = Plan(
                        title="Task Plan",
                        goal=event.message[:200] if event.message else "Process user request",
                        message=event.message[:500] if event.message else "I'll work on your request.",
                        steps=[Step(id="1", description="Process the user's request")]
                    )
                yield PlanEvent(status=PlanStatus.CREATED, plan=plan)
            else:
                yield event

    async def update_plan(self, plan: Plan, step: Step) -> AsyncGenerator[BaseEvent, None]:
        message = UPDATE_PLAN_PROMPT.format(plan=plan.dump_json(), step=step.model_dump_json())
        async for event in self.execute(message):
            if isinstance(event, MessageEvent):
                logger.debug(f"Planner agent update plan: {event.message}")
                try:
                    parsed_response = await self.json_parser.parse(event.message)
                    updated_plan = Plan.model_validate(parsed_response)
                    new_steps = [Step.model_validate(s) for s in updated_plan.steps]
                except Exception as e:
                    logger.error(f"Failed to parse plan update: {e}")
                    new_steps = []
                
                first_pending_index = None
                for i, s in enumerate(plan.steps):
                    if not s.is_done():
                        first_pending_index = i
                        break
                
                if first_pending_index is not None:
                    updated_steps = plan.steps[:first_pending_index]
                    updated_steps.extend(new_steps)
                    plan.steps = updated_steps
                
                yield PlanEvent(status=PlanStatus.UPDATED, plan=plan)
            else:
                yield event