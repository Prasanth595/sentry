from __future__ import annotations

import contextvars
import dataclasses
import threading
from unittest import mock

import pytest

from sentry.types.superuser import SuperuserAccess
from sentry.viewer_context import (
    Actor,
    ActorType,
    ViewerContext,
    get_viewer_context,
    observe_viewer_context_propagation,
    set_viewer_context_organization,
    viewer_context_scope,
)


class TestActorType:
    def test_values_are_strings(self):
        assert ActorType.USER == "user"
        assert ActorType.SYSTEM == "system"
        assert ActorType.INTEGRATION == "integration"
        assert ActorType.UNKNOWN == "unknown"


class TestViewerContext:
    def test_actor_identity_roundtrip(self):
        ctx = ViewerContext(
            organization_id=10,
            actor=Actor(type=ActorType.SERVICE_ACCOUNT, id=42),
        )
        assert ctx.serialize() == {
            "organization_id": 10,
            "actor_type": "service_account",
            "actor": {"type": "service_account", "id": 42},
        }
        assert ViewerContext.deserialize(ctx.serialize()) == ctx
        assert ctx.actor.user_id is None
        assert ctx.actor != Actor(type=ActorType.USER, id=42)

    @pytest.mark.parametrize("actor_type", [ActorType.USER, ActorType.AGENT, ActorType.SYSTEM])
    def test_legacy_human_identity_is_preserved(self, actor_type):
        ctx = ViewerContext.deserialize({"actor_type": actor_type.value, "user_id": 42})
        assert ctx.actor.type == actor_type
        assert ctx.actor.user_id == 42
        assert ViewerContext.deserialize(ctx.serialize()) == ctx

    def test_agent_delegate_is_not_actor_id(self):
        ctx = ViewerContext(actor=Actor(type=ActorType.AGENT, delegated_user_id=42))
        assert ctx.actor.id is None
        assert ctx.actor.delegated_user_id == 42

    def test_user_actor_supports_legacy_readers(self):
        ctx = ViewerContext(actor=Actor(type=ActorType.USER, id=42))
        assert ctx.actor.user_id == 42
        assert ctx.actor.type == ActorType.USER
        assert ctx.serialize()["user_id"] == 42
        assert ctx.actor.id == 42

    @pytest.mark.parametrize(
        "data",
        [
            {"actor": None},
            {"actor": {}},
            {"actor": {"type": "service_account"}},
            {"actor": {"type": "future_actor", "id": 42}},
            {"actor": {"type": "service_account", "id": True}},
            {"actor": {"type": "service_account", "id": "42"}},
            {"actor": {"type": "service_account", "id": 0}},
            {"actor": {"type": "user", "id": 42}, "user_id": 43},
            {"actor": {"type": "service_account", "id": 42}, "actor_type": "user"},
            {"actor": {"type": "service_account", "id": 42}, "actor_type": "future_actor"},
            {"actor": {"type": "service_account", "id": 42}, "user_id": 42},
            {
                "actor": {"type": "service_account", "id": 42, "delegated_user_id": 7},
            },
            {
                "actor": {
                    "type": "service_account",
                    "id": 42,
                    "superuser": {"expires_at": 1234567890},
                },
            },
            {
                "actor": {
                    "type": "user",
                    "id": 42,
                    "superuser": {"expires_at": 1234567890},
                },
                "superuser": {"expires_at": 1234567891},
            },
            {
                "actor": {"type": "service_account", "id": 42},
                "superuser": {"expires_at": 1234567890},
            },
            {"actor_type": "service_account"},
            {"organization_id": None, "actor": {"type": "service_account", "id": 42}},
        ],
    )
    def test_invalid_actor_cannot_fall_back_to_legacy_identity(self, data):
        with pytest.raises(ValueError):
            ViewerContext.deserialize({"organization_id": 10, **data})

    def test_replacing_actor_changes_identity_and_drops_elevation(self):
        ctx = ViewerContext(
            actor=Actor(
                type=ActorType.USER, id=42, superuser=SuperuserAccess(expires_at=1234567890)
            )
        )
        changed = dataclasses.replace(ctx, actor=Actor(type=ActorType.USER, id=43))
        assert changed.actor.user_id == 43
        assert changed.actor.superuser is None
        assert ctx.actor.user_id == 42

    @pytest.mark.parametrize(
        "superuser",
        [
            {"expires_at": True},
            {"expires_at": "123"},
            {},
            "invalid",
        ],
    )
    def test_invalid_superuser_claim(self, superuser):
        with pytest.raises(ValueError):
            ViewerContext.deserialize({"superuser": superuser})

    def test_superuser_access_roundtrip_and_org_change(self):
        ctx = ViewerContext(
            actor=Actor(
                type=ActorType.USER, id=42, superuser=SuperuserAccess(expires_at=1234567890)
            ),
            organization_id=10,
        )
        assert ViewerContext.deserialize(ctx.serialize()) == ctx
        assert "1234567890" not in repr(ctx)
        with viewer_context_scope(ctx):
            set_viewer_context_organization(10)
            assert get_viewer_context() == ctx
            set_viewer_context_organization(11)
            changed = get_viewer_context()
            assert changed is not None
            assert changed.actor.superuser is None

    def test_defaults(self):
        ctx = ViewerContext()
        assert ctx.organization_id is None
        assert ctx.actor.user_id is None
        assert ctx.actor.type is ActorType.UNKNOWN

    def test_frozen(self):
        ctx = ViewerContext(actor=Actor(type=ActorType.USER, id=1))
        with pytest.raises(dataclasses.FrozenInstanceError):
            ctx.actor.id = 2  # type: ignore[misc]

    def test_construction(self):
        ctx = ViewerContext(
            actor=Actor(type=ActorType.SYSTEM, delegated_user_id=42), organization_id=10
        )
        assert ctx.organization_id == 10
        assert ctx.actor.user_id == 42
        assert ctx.actor.type is ActorType.SYSTEM


class TestViewerContextScope:
    def test_get_returns_none_outside_scope(self):
        assert get_viewer_context() is None

    def test_scope_sets_and_resets(self):
        ctx = ViewerContext(actor=Actor(type=ActorType.USER, id=1))
        assert get_viewer_context() is None

        with viewer_context_scope(ctx):
            assert get_viewer_context() is ctx

        assert get_viewer_context() is None

    def test_nested_scopes(self):
        outer = ViewerContext(actor=Actor(type=ActorType.USER, id=1))
        inner = ViewerContext(actor=Actor(type=ActorType.USER, id=2))

        with viewer_context_scope(outer):
            assert get_viewer_context() is outer

            with viewer_context_scope(inner):
                assert get_viewer_context() is inner

            assert get_viewer_context() is outer

        assert get_viewer_context() is None

    def test_cleanup_on_exception(self):
        ctx = ViewerContext(actor=Actor(type=ActorType.USER, id=1))

        with pytest.raises(RuntimeError):
            with viewer_context_scope(ctx):
                assert get_viewer_context() is ctx
                raise RuntimeError("boom")

        assert get_viewer_context() is None

    def test_copy_context_propagates_to_thread(self):
        ctx = ViewerContext(actor=Actor(type=ActorType.USER, id=1), organization_id=10)
        result: list[ViewerContext | None] = [None]

        with viewer_context_scope(ctx):
            copied = contextvars.copy_context()

            def _worker():
                result[0] = copied.run(get_viewer_context)

            t = threading.Thread(target=_worker)
            t.start()
            t.join()

        assert result[0] is ctx

    def test_context_propagating_thread_pool_executor(self):
        from sentry.utils.concurrent import ContextPropagatingThreadPoolExecutor

        ctx = ViewerContext(
            actor=Actor(type=ActorType.INTEGRATION, delegated_user_id=7), organization_id=99
        )

        with viewer_context_scope(ctx):
            with ContextPropagatingThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(get_viewer_context).result()

        assert result is ctx

    def test_context_propagating_executor_does_not_leak_across_submissions(self):
        from sentry.utils.concurrent import ContextPropagatingThreadPoolExecutor

        ctx = ViewerContext(actor=Actor(type=ActorType.USER, id=1))

        with ContextPropagatingThreadPoolExecutor(max_workers=1) as pool:
            # Submit inside a scope — worker should see ctx
            with viewer_context_scope(ctx):
                inside = pool.submit(get_viewer_context).result()

            # Submit outside any scope — worker should see None
            outside = pool.submit(get_viewer_context).result()

        assert inside is ctx
        assert outside is None

    def test_set_organization_updates_current_context(self):
        ctx = ViewerContext(actor=Actor(type=ActorType.USER, id=1))

        with viewer_context_scope(ctx):
            set_viewer_context_organization(42)
            updated = get_viewer_context()

            assert updated is not None
            assert updated.organization_id == 42
            assert updated.actor.user_id == ctx.actor.user_id
            assert updated.actor.type is ctx.actor.type

        assert get_viewer_context() is None

    def test_set_organization_is_noop_without_context(self):
        set_viewer_context_organization(42)

        assert get_viewer_context() is None


class TestObserve:
    @pytest.fixture(autouse=True)
    def patch_metrics(self):
        with mock.patch("sentry.viewer_context.sentry_sdk.metrics.count") as m:
            yield m

    def _tags(self, m):
        assert m.call_count == 1
        args, kwargs = m.call_args
        assert args == ("viewer_context.observation", 1)
        return kwargs["attributes"]

    def test_no_context_tags_actor_none(self, patch_metrics):
        observe_viewer_context_propagation("seer_rpc_out")
        tags = self._tags(patch_metrics)
        assert tags == {
            "point": "seer_rpc_out",
            "actor_type": "none",
            "has_user_id": "false",
            "has_org_id": "false",
            "expected": "true",
            "sentry.client_sample_rate": 0.001,
        }

    def test_with_context_tags_actor_and_presence_flags(self, patch_metrics):
        ctx = ViewerContext(actor=Actor(type=ActorType.USER, id=42), organization_id=7)
        with viewer_context_scope(ctx):
            observe_viewer_context_propagation("seer_rpc_out")
        tags = self._tags(patch_metrics)
        assert tags["actor_type"] == "user"
        assert tags["has_user_id"] == "true"
        assert tags["has_org_id"] == "true"

    def test_partial_context_tags_individual_flags(self, patch_metrics):
        # User without org (e.g. cross-org admin lookup before org is resolved)
        ctx = ViewerContext(actor=Actor(type=ActorType.USER, id=42))
        with viewer_context_scope(ctx):
            observe_viewer_context_propagation("rpc_inbound")
        tags = self._tags(patch_metrics)
        assert tags["has_user_id"] == "true"
        assert tags["has_org_id"] == "false"

    def test_explicit_ctx_overrides_contextvar(self, patch_metrics):
        # Caller passes a resolved value that's distinct from the contextvar
        with viewer_context_scope(ViewerContext(actor=Actor(type=ActorType.SYSTEM))):
            observe_viewer_context_propagation(
                "seer_rpc_out", ctx=ViewerContext(actor=Actor(type=ActorType.INTEGRATION))
            )
        tags = self._tags(patch_metrics)
        assert tags["actor_type"] == "integration"

    def test_explicit_ctx_none_treated_as_missing(self, patch_metrics):
        # Distinguishes "ctx wasn't passed" (sentinel) from "ctx is explicitly None"
        with viewer_context_scope(ViewerContext(actor=Actor(type=ActorType.USER))):
            observe_viewer_context_propagation("seer_rpc_out", ctx=None)
        tags = self._tags(patch_metrics)
        assert tags["actor_type"] == "none"

    def test_expected_false_does_not_log_when_missing(self, patch_metrics, caplog):
        observe_viewer_context_propagation("optional_point", expected=False)
        tags = self._tags(patch_metrics)
        assert tags["expected"] == "false"
        # No warning log for expected=False misses
        assert all(r.levelname != "WARNING" for r in caplog.records)

    def test_expected_true_logs_when_missing(self, patch_metrics, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="sentry.viewer_context"):
            observe_viewer_context_propagation("rpc_inbound")
        assert any(r.message == "viewer_context.missing" for r in caplog.records)

    def test_expected_true_does_not_log_when_present(self, patch_metrics, caplog):
        ctx = ViewerContext(actor=Actor(type=ActorType.USER, id=1))
        with viewer_context_scope(ctx):
            observe_viewer_context_propagation("rpc_inbound")
        assert all(r.message != "viewer_context.missing" for r in caplog.records)

    def test_extra_attributes_merged_into_metric_tags(self, patch_metrics):
        observe_viewer_context_propagation(
            "seer_rpc_in", extra_attributes={"method": "get_organization_slug"}
        )
        tags = self._tags(patch_metrics)
        assert tags["point"] == "seer_rpc_in"
        assert tags["method"] == "get_organization_slug"

    def test_extra_attributes_cannot_override_fixed_tags(self, patch_metrics):
        # Fixed tags must take precedence so callers can't accidentally swap
        # `point` or `actor_type` and corrupt the metric's cardinality story.
        ctx = ViewerContext(actor=Actor(type=ActorType.USER, id=1))
        with viewer_context_scope(ctx):
            observe_viewer_context_propagation(
                "seer_rpc_in",
                extra_attributes={"point": "hijacked", "method": "real_method"},
            )
        tags = self._tags(patch_metrics)
        assert tags["point"] == "seer_rpc_in"
        assert tags["method"] == "real_method"

    def test_extra_attributes_propagate_to_missing_log(self, patch_metrics, caplog):
        import logging

        with caplog.at_level(logging.WARNING, logger="sentry.viewer_context"):
            observe_viewer_context_propagation(
                "seer_rpc_in", extra_attributes={"method": "ghost_method"}
            )
        missing_records = [r for r in caplog.records if r.message == "viewer_context.missing"]
        assert len(missing_records) == 1
        assert missing_records[0].method == "ghost_method"
        assert missing_records[0].point == "seer_rpc_in"
