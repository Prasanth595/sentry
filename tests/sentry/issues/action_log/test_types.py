from datetime import UTC, datetime
from typing import Any

import pytest

from sentry.issues.action_log.types import FirstSeenAction, GroupAction, GroupActionType
from sentry.testutils.cases import TestCase


class GroupActionRegistrationTest(TestCase):
    def test_all_types_are_registered(self) -> None:
        missing = [member for member in GroupActionType if GroupAction.by_type(member) is None]
        assert missing == [], (
            f"GroupActionType members without a registered GroupAction subclass: "
            f"{[m.name for m in missing]}"
        )


class GroupActionJsonDictTest(TestCase):
    def test_datetime_round_trips_through_json_dict(self) -> None:
        first_seen = datetime(2026, 10, 8, 19, 13, 56, 56000, tzinfo=UTC)
        data = FirstSeenAction(first_seen=first_seen).json_dict()

        assert data == {"first_seen": first_seen.isoformat()}
        assert FirstSeenAction(**data).first_seen == first_seen


@pytest.mark.parametrize(
    "action_type",
    [
        GroupActionType.COMMENT_CREATED,
        GroupActionType.COMMENT_EDITED,
        GroupActionType.COMMENT_DELETED,
    ],
)
def test_comment_audit_contract(action_type: GroupActionType) -> None:
    action_class = GroupAction.by_type(action_type)
    assert action_class is not None
    occurred_at = datetime(2024, 1, 1, tzinfo=UTC)
    action = action_class(comment_id=42, occurred_at=occurred_at)
    assert action.json_dict() == {"comment_id": 42, "occurred_at": occurred_at.isoformat()}
    assert action_class(**action.json_dict()) == action
    assert action_type not in GroupAction.get_user_visible_types()


@pytest.mark.parametrize(
    "action_type,payload",
    [
        (GroupActionType.COMMENT, {"comment_id": 42, "text": "original", "mentions": []}),
        (GroupActionType.COMMENT_EDIT, {"comment_id": 73, "text": "edited", "mentions": []}),
        (GroupActionType.COMMENT_DELETE, {"comment_id": 73}),
    ],
)
def test_historical_comment_payload(action_type: GroupActionType, payload: dict[str, Any]) -> None:
    action_class = GroupAction.by_type(action_type)
    assert action_class is not None
    assert action_class(**payload).json_dict() == payload
