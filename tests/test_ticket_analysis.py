from collections.abc import Sequence
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient, Response

from support_prompt_lab.api.dependencies import get_support_workflow
from support_prompt_lab.api.schemas import AnalyzeTicketResponse
from support_prompt_lab.application.draft import (
    ResponseDraftPromptBuilder,
    ResponseDraftStage,
)
from support_prompt_lab.application.escalation import EscalationDecider
from support_prompt_lab.application.policy import PolicyDecisionStage, PolicyPromptBuilder
from support_prompt_lab.application.ports import (
    LLMClient,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from support_prompt_lab.application.review import (
    ResponseReviewPromptBuilder,
    ResponseReviewStage,
)
from support_prompt_lab.application.triage import TriagePromptBuilder, TriageStage
from support_prompt_lab.application.workflow import SupportWorkflow
from support_prompt_lab.config import Settings, get_settings
from support_prompt_lab.infrastructure import LLMProviderError
from support_prompt_lab.main import app
from support_prompt_lab.prompts import PromptRegistry, PromptStrategy
from tests.fakes import FakeLLMClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPT_ROOT = PROJECT_ROOT / "prompts"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def model_response(text: str) -> ModelResponse:
    return ModelResponse(
        text=text,
        model="gpt-test-resolved",
        usage=ModelUsage(input_tokens=100, output_tokens=20),
    )


def successful_responses(*, review: str) -> list[ModelResponse]:
    return [
        model_response(
            '{"intent":"refund","urgency":"low","sentiment":"neutral",'
            '"rationale":"The customer requests a refund."}'
        ),
        model_response(
            '{"decision":"allow","applicable_policy_ids":["returns-30-day"],'
            '"missing_information":[],"rationale":"The return is allowed."}'
        ),
        model_response(
            '{"message":"We can process your return within the 30-day window.",'
            '"applied_policy_ids":["returns-30-day"]}'
        ),
        model_response(review),
    ]


def request_document() -> dict[str, object]:
    return {
        "ticket": {
            "ticket_id": "ticket-5001",
            "subject": "Refund request",
            "message": "Please refund my order.",
            "order_id": "order-9001",
        },
        "policies": [
            {
                "policy_id": "returns-30-day",
                "title": "Standard returns",
                "text": "Returns are allowed within 30 days.",
            }
        ],
    }


def support_workflow(client: LLMClient) -> SupportWorkflow:
    registry = PromptRegistry(PROMPT_ROOT)
    model = "gpt-test"
    return SupportWorkflow(
        triage_stage=TriageStage(TriagePromptBuilder(registry), client, model),
        policy_stage=PolicyDecisionStage(PolicyPromptBuilder(registry), client, model),
        escalation_decider=EscalationDecider(),
        draft_stage=ResponseDraftStage(ResponseDraftPromptBuilder(registry), client, model),
        review_stage=ResponseReviewStage(ResponseReviewPromptBuilder(registry), client, model),
    )


async def post_analysis(
    llm_client: LLMClient,
    *,
    document: dict[str, object] | None = None,
) -> Response:
    def override_workflow() -> SupportWorkflow:
        return support_workflow(llm_client)

    app.dependency_overrides[get_support_workflow] = override_workflow
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/v1/tickets/analyze",
                json=document if document is not None else request_document(),
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_analyze_endpoint_returns_approved_workflow() -> None:
    fake = FakeLLMClient(
        successful_responses(
            review=(
                '{"verdict":"approved","final_message":"We can process your return '
                'within the 30-day window.","issues":[],'
                '"applied_policy_ids":["returns-30-day"],'
                '"rationale":"The response is compliant and clear."}'
            )
        )
    )

    response = await post_analysis(fake)

    assert response.status_code == 200
    result = AnalyzeTicketResponse.model_validate(response.json())
    assert result.ticket_id == "ticket-5001"
    assert result.requires_escalation is False
    assert result.final_message == "We can process your return within the 30-day window."
    assert result.triage.metadata.prompt_version == "1.5.0"
    assert result.policy.metadata.prompt_version == "1.1.0"
    assert result.draft is not None
    assert result.draft.metadata.usage.input_tokens == 100
    assert result.review is not None
    assert result.review.outcome.verdict.value == "approved"
    assert len(fake.requests) == 4


@pytest.mark.parametrize(
    ("selection", "expected_strategy", "expected_version"),
    [
        ({"strategy": "zero_shot"}, PromptStrategy.ZERO_SHOT, "1.3.0"),
        ({"strategy": "few_shot"}, PromptStrategy.FEW_SHOT, "1.4.0"),
        ({"version": "1.2.0"}, PromptStrategy.MANY_SHOT, "1.2.0"),
    ],
)
@pytest.mark.anyio
async def test_analyze_endpoint_selects_requested_triage_prompt(
    selection: dict[str, str],
    expected_strategy: PromptStrategy,
    expected_version: str,
) -> None:
    fake = FakeLLMClient(
        successful_responses(
            review=(
                '{"verdict":"approved","final_message":"We can process your return '
                'within the 30-day window.","issues":[],'
                '"applied_policy_ids":["returns-30-day"],'
                '"rationale":"The response is compliant and clear."}'
            )
        )
    )
    document = request_document()
    document["triage_prompt"] = selection

    response = await post_analysis(fake, document=document)

    assert response.status_code == 200
    result = AnalyzeTicketResponse.model_validate(response.json())
    assert result.triage.metadata.strategy is expected_strategy
    assert result.triage.metadata.prompt_version == expected_version


@pytest.mark.parametrize(
    "selection",
    [
        {},
        {"strategy": "zero_shot", "version": "1.0.0"},
        {"strategy": "unknown"},
        {"version": "1.0"},
    ],
    ids=["empty", "both-fields", "unknown-strategy", "invalid-version"],
)
@pytest.mark.anyio
async def test_analyze_endpoint_rejects_invalid_triage_selection(
    selection: dict[str, str],
) -> None:
    fake = FakeLLMClient([])
    document = request_document()
    document["triage_prompt"] = selection

    response = await post_analysis(fake, document=document)

    assert response.status_code == 422
    assert fake.requests == []


@pytest.mark.anyio
async def test_analyze_endpoint_rejects_unavailable_triage_version() -> None:
    fake = FakeLLMClient([])
    document = request_document()
    document["triage_prompt"] = {"version": "99.0.0"}

    response = await post_analysis(fake, document=document)

    assert response.status_code == 422
    assert response.json() == {"detail": "requested prompt selection is unavailable"}
    assert fake.requests == []


@pytest.mark.anyio
async def test_analyze_endpoint_returns_reviewer_revision() -> None:
    fake = FakeLLMClient(
        successful_responses(
            review=(
                '{"verdict":"revised","final_message":"We are happy to help with '
                'your eligible return.","issues":["tone_issue"],'
                '"applied_policy_ids":["returns-30-day"],'
                '"rationale":"The response needed a warmer tone."}'
            )
        )
    )

    response = await post_analysis(fake)

    assert response.status_code == 200
    result = AnalyzeTicketResponse.model_validate(response.json())
    assert result.final_message == "We are happy to help with your eligible return."
    assert result.review is not None
    assert result.review.outcome.verdict.value == "revised"


@pytest.mark.anyio
async def test_analyze_endpoint_short_circuits_escalated_workflow() -> None:
    fake = FakeLLMClient(
        [
            model_response(
                '{"intent":"refund","urgency":"low","sentiment":"neutral",'
                '"rationale":"The customer requests a refund."}'
            ),
            model_response(
                '{"decision":"escalate","applicable_policy_ids":[],'
                '"missing_information":["purchase date"],'
                '"rationale":"Eligibility cannot be established."}'
            ),
        ]
    )

    response = await post_analysis(fake)

    assert response.status_code == 200
    result = AnalyzeTicketResponse.model_validate(response.json())
    assert result.requires_escalation is True
    assert result.final_message is None
    assert result.draft is None
    assert result.review is None
    assert result.escalation.required is True
    assert len(fake.requests) == 2


@pytest.mark.anyio
async def test_analyze_endpoint_sanitizes_invalid_model_output() -> None:
    raw_output = "not json and must not be returned"

    response = await post_analysis(FakeLLMClient([model_response(raw_output)]))

    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "message": "support workflow failed",
            "code": "triage_output_invalid",
        }
    }
    assert raw_output not in response.text


class FailingLLMClient:
    async def complete(self, request: ModelRequest) -> ModelResponse:
        raise LLMProviderError("sensitive upstream error")


@pytest.mark.anyio
async def test_analyze_endpoint_sanitizes_provider_failure() -> None:
    response = await post_analysis(FailingLLMClient())

    assert response.status_code == 502
    assert response.json() == {
        "detail": {
            "message": "support workflow failed",
            "code": "model_provider_failed",
        }
    }
    assert "sensitive" not in response.text


@pytest.mark.anyio
async def test_analyze_endpoint_reports_unconfigured_provider() -> None:
    def override_settings() -> Settings:
        return Settings(openai_api_key=None, openai_model="gpt-test")

    app.dependency_overrides[get_settings] = override_settings
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(
                "/v1/tickets/analyze",
                json=request_document(),
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "language model provider is not configured"}


@pytest.mark.parametrize(
    "policies",
    [
        [],
        [
            {
                "policy_id": "returns-30-day",
                "title": "Standard returns",
                "text": "Returns are allowed within 30 days.",
            },
            {
                "policy_id": "returns-30-day",
                "title": "Duplicate returns",
                "text": "This identifier is duplicated.",
            },
        ],
    ],
    ids=["missing-policies", "duplicate-policy-identifiers"],
)
@pytest.mark.anyio
async def test_analyze_endpoint_rejects_invalid_requests(
    policies: Sequence[dict[str, str]],
) -> None:
    fake = FakeLLMClient([])
    document = request_document()
    document["policies"] = policies

    response = await post_analysis(fake, document=document)

    assert response.status_code == 422
    assert fake.requests == []
