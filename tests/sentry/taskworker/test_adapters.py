import contextlib

import orjson
import pytest
from django.test.utils import override_settings
from taskbroker_client.metrics import NoOpMetricsBackend
from taskbroker_client.registry import TaskRegistry

from sentry.conf.types.kafka_definition import Topic
from sentry.silo.base import SiloMode
from sentry.taskworker.adapters import (
    SentryRouter,
    ViewerContextHook,
    make_producer,
)
from sentry.viewer_context import (
    Actor,
    ActorType,
    ViewerContext,
    get_viewer_context,
    viewer_context_scope,
)


@pytest.mark.django_db
def test_registry_create_namespace_route_setting() -> None:
    with override_settings(
        TASKWORKER_ROUTES='{"profiling":"profiles", "private":"private-taskworker-topic"}'
    ):
        registry = TaskRegistry(
            application="sentry",
            producer_factory=make_producer,
            router=SentryRouter(),
            metrics=NoOpMetricsBackend(),
        )

        # namespaces without routes resolve to the default topic.
        tests = registry.create_namespace(name="tests")
        assert tests.topic == Topic.TASKWORKER.value

        profiling = registry.create_namespace(name="profiling")
        assert profiling.topic == "profiles"

        private = registry.create_namespace(name="private")
        assert private.topic == "private-taskworker-topic"


@pytest.mark.django_db
def test_default_router_topic() -> None:
    router = SentryRouter()
    topic = router.route_namespace("test.tasks.test_router.default")
    assert topic == Topic.TASKWORKER.value


@pytest.mark.django_db
def test_default_router_topic_region_silo() -> None:
    with override_settings(SILO_MODE=SiloMode.CELL):
        router = SentryRouter()
        topic = router.route_namespace("test.tasks.test_router.region")
        assert topic == Topic.TASKWORKER.value


@pytest.mark.django_db(databases=["default", "control"])
def test_default_router_topic_control_silo() -> None:
    with override_settings(SILO_MODE=SiloMode.CONTROL):
        router = SentryRouter()
        topic = router.route_namespace("test.tasks.test_router.control")
        assert topic == Topic.TASKWORKER_CONTROL.value


@pytest.mark.django_db
def test_default_router_topic_override() -> None:
    with override_settings(
        SILO_MODE=SiloMode.CELL,
        TASKWORKER_DEFAULT_TOPIC="taskworker-push",
    ):
        router = SentryRouter()
        topic = router.route_namespace("test.tasks.test_router.unrouted")
        assert topic == "taskworker-push"


@pytest.mark.django_db(databases=["default", "control"])
def test_default_router_topic_override_ignored_in_control_silo() -> None:
    # The region default-topic override must never redirect control-silo tasks.
    with override_settings(
        SILO_MODE=SiloMode.CONTROL,
        TASKWORKER_DEFAULT_TOPIC="taskworker-push",
    ):
        router = SentryRouter()
        topic = router.route_namespace("test.tasks.test_router.control")
        assert topic == Topic.TASKWORKER_CONTROL.value


class TestViewerContextHook:
    def test_on_dispatch_with_context(self) -> None:
        hook = ViewerContextHook()
        headers: dict[str, str] = {}
        ctx = ViewerContext(actor=Actor(type=ActorType.USER, id=7), organization_id=42)
        with viewer_context_scope(ctx):
            hook.on_dispatch(headers)

        payload = orjson.loads(headers["sentry-viewer-context"])
        assert payload["organization_id"] == 42
        assert payload["user_id"] == 7
        assert payload["actor_type"] == "user"

    def test_on_dispatch_without_context(self) -> None:
        hook = ViewerContextHook()
        headers: dict[str, str] = {}
        hook.on_dispatch(headers)

        assert "sentry-viewer-context" not in headers

    def test_on_dispatch_partial_context(self) -> None:
        hook = ViewerContextHook()
        headers: dict[str, str] = {}
        ctx = ViewerContext(actor=Actor(type=ActorType.SYSTEM), organization_id=42)
        with viewer_context_scope(ctx):
            hook.on_dispatch(headers)

        payload = orjson.loads(headers["sentry-viewer-context"])
        assert payload["organization_id"] == 42
        assert "user_id" not in payload
        assert payload["actor_type"] == "system"

    def test_on_execute_restores_context(self) -> None:
        hook = ViewerContextHook()
        headers = {
            "sentry-viewer-context": orjson.dumps(
                {"organization_id": 42, "user_id": 7, "actor_type": "user"}
            ).decode(),
        }
        with hook.on_execute(headers):
            ctx = get_viewer_context()
            assert ctx is not None
            assert ctx.organization_id == 42
            assert ctx.actor.user_id == 7
            assert ctx.actor.type == ActorType.USER

        assert get_viewer_context() is None

    def test_on_execute_no_headers(self) -> None:
        hook = ViewerContextHook()
        cm = hook.on_execute({})
        assert isinstance(cm, contextlib.nullcontext)

    def test_on_execute_partial_headers(self) -> None:
        hook = ViewerContextHook()
        headers = {
            "sentry-viewer-context": orjson.dumps(
                {"organization_id": 99, "actor_type": "integration"}
            ).decode(),
        }
        with hook.on_execute(headers):
            ctx = get_viewer_context()
            assert ctx is not None
            assert ctx.organization_id == 99
            assert ctx.actor.user_id is None
            assert ctx.actor.type == ActorType.INTEGRATION

    @pytest.mark.parametrize(
        "original",
        [
            ViewerContext(actor=Actor(type=ActorType.USER, id=456), organization_id=123),
            ViewerContext(organization_id=123, actor=Actor(type=ActorType.SERVICE_ACCOUNT, id=456)),
        ],
    )
    def test_roundtrip(self, original: ViewerContext) -> None:
        """Dispatch then execute produces the same ViewerContext."""
        hook = ViewerContextHook()
        headers: dict[str, str] = {}

        with viewer_context_scope(original):
            hook.on_dispatch(headers)

        with hook.on_execute(headers):
            restored = get_viewer_context()
            assert restored is not None
            assert restored.organization_id == original.organization_id
            assert restored.actor.user_id == original.actor.user_id
            assert restored.actor.type == original.actor.type
            assert restored.actor == original.actor

    def test_on_execute_malformed_json(self) -> None:
        hook = ViewerContextHook()
        headers = {"sentry-viewer-context": "not-valid-json{"}
        cm = hook.on_execute(headers)
        assert isinstance(cm, contextlib.nullcontext)

    def test_invalid_actor_prevents_execution_without_identity(self) -> None:
        hook = ViewerContextHook()
        headers = {
            "sentry-viewer-context": orjson.dumps(
                {"organization_id": 42, "actor": {"type": "service_account"}}
            ).decode(),
        }
        with pytest.raises(ValueError):
            hook.on_execute(headers)

    def test_on_execute_non_dict_json(self) -> None:
        hook = ViewerContextHook()
        headers = {"sentry-viewer-context": "[1, 2, 3]"}
        cm = hook.on_execute(headers)
        assert isinstance(cm, contextlib.nullcontext)
