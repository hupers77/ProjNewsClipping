"""v1 업무 흐름: 이메일 만들기 · 발송 처리 · 초안 되돌리기 · 오래된 기사 삭제.

화면(HTML)과 분리된 순수 로직이라 테스트하기 쉽다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from newsclip.emailer import (
    CATEGORY_ORDER,
    Draft,
    build_draft,
    draft_from_dict,
    draft_to_dict,
)
from newsclip.review import review
from newsclip.store import APPROVED, REJECTED
from newsclip_v1.config import Settings
from newsclip_v1.store import ACTIVE, CLEARED, DRAFTED, SENT, Store2

DRAFT_KEY = "email_draft"
MEMBERS_KEY = "draft_members"  # {대표 기사 id: [묶음에 속한 모든 기사 id]}
LAST_SENT_KEY = "last_sent"


class NothingApproved(ValueError):
    """승인한 기사가 없어 이메일을 만들 수 없다."""


def load_draft(store: Store2) -> Draft | None:
    data = store.get_kv(DRAFT_KEY)
    return draft_from_dict(data) if isinstance(data, dict) else None


def save_draft(store: Store2, draft: Draft) -> None:
    store.set_kv(DRAFT_KEY, draft_to_dict(draft))


def _category_rank(category: str) -> int:
    return CATEGORY_ORDER.index(category) if category in CATEGORY_ORDER else 99


def make_email(settings: Settings, store: Store2, *, clear_undecided: bool = True) -> Draft:
    """승인한 기사를 이메일 초안으로 옮기고 후보 리스트를 초기화한다.

    - 승인 → drafted (초안에 담김)
    - 거절 → cleared (이후 수집에서 제외)
    - 미검토·제외어 걸린 기사 → clear_undecided 이면 cleared, 아니면 그대로 둔다
    이미 보내지 않은 초안이 있으면 그 항목(편집 내용 포함)을 유지하고 새 항목을 더한다.
    """
    result = review(settings, store)
    approved = [c for c in result.candidates if c.decision == APPROVED]
    if not approved:
        raise NothingApproved("승인한 기사가 없습니다")

    fresh = build_draft(approved, settings.email, None)
    existing = load_draft(store)
    if existing:
        known = {i.article_id for i in existing.items}
        items = existing.items + [i for i in fresh.items if i.article_id not in known]
        items.sort(key=lambda i: _category_rank(i.category))  # 안정 정렬
        draft = Draft(
            existing.subject,
            existing.recipients,
            existing.intro,
            existing.outro,
            existing.sender or settings.email.sender,
            items,
        )
    else:
        draft = fresh
    save_draft(store, draft)

    members = store.get_kv(MEMBERS_KEY)
    members = members if isinstance(members, dict) else {}
    for c in approved:
        members[str(c.rep.id)] = c.ids
        store.set_phase(c.ids, DRAFTED)
    store.set_kv(MEMBERS_KEY, members)

    for c in result.candidates:
        if c.decision == REJECTED or (clear_undecided and c.decision != APPROVED):
            store.set_phase(c.ids, CLEARED)
    if clear_undecided:
        store.set_phase([a.id for a, _ in result.excluded], CLEARED)
    return draft


def mark_sent(store: Store2) -> int:
    """사용자가 직접 '발송 처리'했을 때: 초안의 기사를 sent 로 바꾸고 초안을 비운다.

    메일에 포함하지 않기로 한 항목은 발송한 것이 아니므로 sent 대신 cleared 로 둔다.
    """
    draft = load_draft(store)
    members = store.get_kv(MEMBERS_KEY)
    members = members if isinstance(members, dict) else {}
    sent_ids: list[int] = []
    skipped_ids: list[int] = []
    if draft:
        for item in draft.items:
            ids = members.get(str(item.article_id), [item.article_id])
            (sent_ids if item.include else skipped_ids).extend(ids)
    store.set_phase(skipped_ids, CLEARED)
    store.set_phase(sent_ids, SENT)
    # 초안과 연결이 끊긴 drafted 기사가 남아 있으면 함께 발송 처리한다
    store.set_phase(store.ids_in_phase(DRAFTED), SENT)
    store.set_kv(DRAFT_KEY, None)
    store.set_kv(MEMBERS_KEY, None)
    store.set_kv(LAST_SENT_KEY, datetime.now(UTC).isoformat())
    return len(sent_ids)


def revert_draft(store: Store2) -> int:
    """초안을 폐기하고 담겨 있던 기사를 승인 상태로 후보 리스트에 되돌린다."""
    ids = store.ids_in_phase(DRAFTED)
    store.set_phase(ids, ACTIVE)
    store.set_kv(DRAFT_KEY, None)
    store.set_kv(MEMBERS_KEY, None)
    return len(ids)


def purge_expired(settings: Settings, store: Store2, now: datetime | None = None) -> int:
    """보관 기간(retention_days)이 지난 기사를 모두 삭제한다. 삭제 건수를 돌려준다."""
    now = now or datetime.now(UTC)
    return store.purge_all_older_than(now - timedelta(days=settings.collect.retention_days))
