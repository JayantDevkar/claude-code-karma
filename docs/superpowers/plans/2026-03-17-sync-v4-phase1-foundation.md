# Sync v4 Phase 1: Foundation — Domain Models + Schema + Repositories

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **TDD SKILL:** Use `oh-my-claudecode:tdd` or `superpowers:test-driven-development` for every task.

**Goal:** Build the pure domain model layer, v19 schema migration, and repository persistence layer.

**Architecture:** Frozen Pydantic models with state machine methods → SQLite repositories. Models have zero DB coupling. Repos are thin CRUD.

**Tech Stack:** Python 3.9+, Pydantic 2.x, SQLite, pytest

**Spec:** `docs/superpowers/specs/2026-03-17-sync-v4-domain-models-design.md`

**Parent Plan:** `docs/superpowers/plans/2026-03-17-sync-v4-master.md`

---

## Task Dependency Graph

```
Tasks 1-5 (Domain Models) ─── ALL PARALLEL ───→ Task 6 (Schema) → Task 7 (Repos) → Task 8 (Integration)
                                                                    ↑
                                                              5 repos can be
                                                              parallel within
                                                              Task 7
```

---

### Task 1: Team Domain Model

**Files:**
- Create: `api/domain/__init__.py`
- Create: `api/domain/team.py`
- Test: `api/tests/test_domain_team.py`

**CAN PARALLEL with Tasks 2-5**

- [ ] **Step 1: Create domain package + write failing tests**

```python
# api/domain/__init__.py
"""Sync v4 domain models — pure Pydantic, no DB coupling."""

# api/tests/test_domain_team.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from domain.team import Team, TeamStatus, AuthorizationError


class TestTeamCreation:
    def test_create_team_defaults_to_active(self):
        team = Team(
            name="karma-team",
            leader_device_id="DEVICE-ABC",
            leader_member_tag="jayant.macbook",
        )
        assert team.status == TeamStatus.ACTIVE
        assert team.name == "karma-team"
        assert team.leader_device_id == "DEVICE-ABC"
        assert team.leader_member_tag == "jayant.macbook"
        assert team.created_at is not None

    def test_team_is_frozen(self):
        team = Team(
            name="t", leader_device_id="D", leader_member_tag="j.m",
        )
        with pytest.raises(Exception):  # ValidationError for frozen
            team.name = "other"


class TestTeamIsLeader:
    def test_is_leader_true(self):
        team = Team(name="t", leader_device_id="LEADER", leader_member_tag="j.m")
        assert team.is_leader("LEADER") is True

    def test_is_leader_false(self):
        team = Team(name="t", leader_device_id="LEADER", leader_member_tag="j.m")
        assert team.is_leader("OTHER") is False


class TestTeamDissolve:
    def test_dissolve_by_leader(self):
        team = Team(name="t", leader_device_id="LEADER", leader_member_tag="j.m")
        dissolved = team.dissolve(by_device="LEADER")
        assert dissolved.status == TeamStatus.DISSOLVED
        assert dissolved.name == team.name  # same identity

    def test_dissolve_by_non_leader_raises(self):
        team = Team(name="t", leader_device_id="LEADER", leader_member_tag="j.m")
        with pytest.raises(AuthorizationError, match="Only leader"):
            team.dissolve(by_device="OTHER")

    def test_dissolve_already_dissolved_raises(self):
        team = Team(name="t", leader_device_id="L", leader_member_tag="j.m",
                    status=TeamStatus.DISSOLVED)
        with pytest.raises(ValueError, match="already dissolved"):
            team.dissolve(by_device="L")


class TestTeamAddMember:
    def test_add_member_by_leader(self):
        from domain.member import Member, MemberStatus
        team = Team(name="t", leader_device_id="LEADER", leader_member_tag="j.m")
        member = Member(
            member_tag="ayush.laptop", team_name="t",
            device_id="DEV-2", user_id="ayush", machine_tag="laptop",
        )
        result = team.add_member(member, by_device="LEADER")
        assert result.status == MemberStatus.ADDED
        assert result.member_tag == "ayush.laptop"

    def test_add_member_by_non_leader_raises(self):
        from domain.member import Member
        team = Team(name="t", leader_device_id="LEADER", leader_member_tag="j.m")
        member = Member(
            member_tag="ayush.laptop", team_name="t",
            device_id="DEV-2", user_id="ayush", machine_tag="laptop",
        )
        with pytest.raises(AuthorizationError):
            team.add_member(member, by_device="OTHER")


class TestTeamRemoveMember:
    def test_remove_active_member_by_leader(self):
        from domain.member import Member, MemberStatus
        team = Team(name="t", leader_device_id="LEADER", leader_member_tag="j.m")
        member = Member(
            member_tag="ayush.laptop", team_name="t",
            device_id="DEV-2", user_id="ayush", machine_tag="laptop",
            status=MemberStatus.ACTIVE,
        )
        result = team.remove_member(member, by_device="LEADER")
        assert result.status == MemberStatus.REMOVED

    def test_remove_added_member_by_leader(self):
        from domain.member import Member, MemberStatus
        team = Team(name="t", leader_device_id="LEADER", leader_member_tag="j.m")
        member = Member(
            member_tag="ayush.laptop", team_name="t",
            device_id="DEV-2", user_id="ayush", machine_tag="laptop",
            status=MemberStatus.ADDED,
        )
        result = team.remove_member(member, by_device="LEADER")
        assert result.status == MemberStatus.REMOVED

    def test_remove_member_by_non_leader_raises(self):
        from domain.member import Member, MemberStatus
        team = Team(name="t", leader_device_id="LEADER", leader_member_tag="j.m")
        member = Member(
            member_tag="a.l", team_name="t", device_id="D",
            user_id="a", machine_tag="l", status=MemberStatus.ACTIVE,
        )
        with pytest.raises(AuthorizationError):
            team.remove_member(member, by_device="OTHER")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/test_domain_team.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'domain'`

- [ ] **Step 3: Implement Team model**

```python
# api/domain/team.py
"""Team domain model — the authority boundary for sync operations."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from domain.member import Member


class AuthorizationError(Exception):
    """Raised when a non-leader attempts a leader-only action."""


class InvalidTransitionError(ValueError):
    """Raised when a state transition is not allowed."""


class TeamStatus(str, Enum):
    ACTIVE = "active"
    DISSOLVED = "dissolved"


class Team(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    leader_device_id: str
    leader_member_tag: str
    status: TeamStatus = TeamStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_leader(self, device_id: str) -> bool:
        return self.leader_device_id == device_id

    def _assert_leader(self, by_device: str) -> None:
        if not self.is_leader(by_device):
            raise AuthorizationError(
                f"Only leader ({self.leader_device_id}) can perform this action, "
                f"got device {by_device}"
            )

    def _assert_active(self) -> None:
        if self.status == TeamStatus.DISSOLVED:
            raise InvalidTransitionError(
                f"Team '{self.name}' is already dissolved"
            )

    def dissolve(self, *, by_device: str) -> Team:
        self._assert_leader(by_device)
        self._assert_active()
        return self.model_copy(update={"status": TeamStatus.DISSOLVED})

    def add_member(self, member: Member, *, by_device: str) -> Member:
        self._assert_leader(by_device)
        self._assert_active()
        return member  # member is already created with ADDED status

    def remove_member(self, member: Member, *, by_device: str) -> Member:
        self._assert_leader(by_device)
        self._assert_active()
        return member.remove()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && pytest tests/test_domain_team.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add api/domain/__init__.py api/domain/team.py api/tests/test_domain_team.py
git commit -m "feat(sync-v4): add Team domain model with state machine"
```

---

### Task 2: Member Domain Model

**Files:**
- Create: `api/domain/member.py`
- Test: `api/tests/test_domain_member.py`

**CAN PARALLEL with Tasks 1, 3-5**

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_domain_member.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from domain.member import Member, MemberStatus
from domain.team import InvalidTransitionError


class TestMemberCreation:
    def test_create_member_defaults_to_added(self):
        m = Member(
            member_tag="ayush.laptop", team_name="t",
            device_id="DEV-1", user_id="ayush", machine_tag="laptop",
        )
        assert m.status == MemberStatus.ADDED
        assert m.member_tag == "ayush.laptop"
        assert m.user_id == "ayush"
        assert m.machine_tag == "laptop"

    def test_member_is_frozen(self):
        m = Member(
            member_tag="a.l", team_name="t",
            device_id="D", user_id="a", machine_tag="l",
        )
        with pytest.raises(Exception):
            m.status = MemberStatus.ACTIVE

    def test_parse_member_tag(self):
        m = Member.from_member_tag(
            member_tag="jayant.macbook-pro",
            team_name="t", device_id="D",
        )
        assert m.user_id == "jayant"
        assert m.machine_tag == "macbook-pro"

    def test_invalid_member_tag_no_dot(self):
        with pytest.raises(ValueError, match="must contain"):
            Member.from_member_tag(
                member_tag="nodot", team_name="t", device_id="D",
            )


class TestMemberActivate:
    def test_activate_from_added(self):
        m = Member(
            member_tag="a.l", team_name="t",
            device_id="D", user_id="a", machine_tag="l",
            status=MemberStatus.ADDED,
        )
        activated = m.activate()
        assert activated.status == MemberStatus.ACTIVE

    def test_activate_from_active_raises(self):
        m = Member(
            member_tag="a.l", team_name="t",
            device_id="D", user_id="a", machine_tag="l",
            status=MemberStatus.ACTIVE,
        )
        with pytest.raises(InvalidTransitionError):
            m.activate()

    def test_activate_from_removed_raises(self):
        m = Member(
            member_tag="a.l", team_name="t",
            device_id="D", user_id="a", machine_tag="l",
            status=MemberStatus.REMOVED,
        )
        with pytest.raises(InvalidTransitionError):
            m.activate()


class TestMemberRemove:
    def test_remove_from_active(self):
        m = Member(
            member_tag="a.l", team_name="t",
            device_id="D", user_id="a", machine_tag="l",
            status=MemberStatus.ACTIVE,
        )
        removed = m.remove()
        assert removed.status == MemberStatus.REMOVED

    def test_remove_from_added(self):
        m = Member(
            member_tag="a.l", team_name="t",
            device_id="D", user_id="a", machine_tag="l",
            status=MemberStatus.ADDED,
        )
        removed = m.remove()
        assert removed.status == MemberStatus.REMOVED

    def test_remove_from_removed_raises(self):
        m = Member(
            member_tag="a.l", team_name="t",
            device_id="D", user_id="a", machine_tag="l",
            status=MemberStatus.REMOVED,
        )
        with pytest.raises(InvalidTransitionError):
            m.remove()


class TestMemberProperties:
    def test_is_active_true(self):
        m = Member(
            member_tag="a.l", team_name="t",
            device_id="D", user_id="a", machine_tag="l",
            status=MemberStatus.ACTIVE,
        )
        assert m.is_active is True

    def test_is_active_false_when_added(self):
        m = Member(
            member_tag="a.l", team_name="t",
            device_id="D", user_id="a", machine_tag="l",
            status=MemberStatus.ADDED,
        )
        assert m.is_active is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/test_domain_member.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Member model**

```python
# api/domain/member.py
"""Member domain model — a person + machine in a team."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from domain.team import InvalidTransitionError


class MemberStatus(str, Enum):
    ADDED = "added"
    ACTIVE = "active"
    REMOVED = "removed"


class Member(BaseModel):
    model_config = ConfigDict(frozen=True)

    member_tag: str
    team_name: str
    device_id: str
    user_id: str
    machine_tag: str
    status: MemberStatus = MemberStatus.ADDED
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_member_tag(
        cls, *, member_tag: str, team_name: str, device_id: str, **kwargs
    ) -> Member:
        if "." not in member_tag:
            raise ValueError(
                f"member_tag '{member_tag}' must contain a dot separating user_id and machine_tag"
            )
        user_id, machine_tag = member_tag.split(".", 1)
        return cls(
            member_tag=member_tag,
            team_name=team_name,
            device_id=device_id,
            user_id=user_id,
            machine_tag=machine_tag,
            **kwargs,
        )

    def activate(self) -> Member:
        if self.status != MemberStatus.ADDED:
            raise InvalidTransitionError(
                f"Cannot activate member in '{self.status.value}' state (must be 'added')"
            )
        return self.model_copy(
            update={"status": MemberStatus.ACTIVE, "updated_at": datetime.now(timezone.utc)}
        )

    def remove(self) -> Member:
        if self.status == MemberStatus.REMOVED:
            raise InvalidTransitionError(
                f"Member '{self.member_tag}' is already removed"
            )
        return self.model_copy(
            update={"status": MemberStatus.REMOVED, "updated_at": datetime.now(timezone.utc)}
        )

    @property
    def is_active(self) -> bool:
        return self.status == MemberStatus.ACTIVE
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && pytest tests/test_domain_member.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add api/domain/member.py api/tests/test_domain_member.py
git commit -m "feat(sync-v4): add Member domain model with state machine"
```

---

### Task 3: SharedProject Domain Model

**Files:**
- Create: `api/domain/project.py`
- Test: `api/tests/test_domain_project.py`

**CAN PARALLEL with Tasks 1-2, 4-5**

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_domain_project.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from domain.project import SharedProject, SharedProjectStatus, derive_folder_suffix
from domain.team import InvalidTransitionError


class TestSharedProjectCreation:
    def test_create_project(self):
        p = SharedProject(
            team_name="t",
            git_identity="jayantdevkar/claude-karma",
            folder_suffix="jayantdevkar-claude-karma",
        )
        assert p.status == SharedProjectStatus.SHARED
        assert p.git_identity == "jayantdevkar/claude-karma"
        assert p.encoded_name is None

    def test_create_project_with_encoded_name(self):
        p = SharedProject(
            team_name="t",
            git_identity="jayantdevkar/claude-karma",
            encoded_name="-Users-jayant-GitHub-claude-karma",
            folder_suffix="jayantdevkar-claude-karma",
        )
        assert p.encoded_name == "-Users-jayant-GitHub-claude-karma"

    def test_project_is_frozen(self):
        p = SharedProject(
            team_name="t", git_identity="o/r", folder_suffix="o-r",
        )
        with pytest.raises(Exception):
            p.git_identity = "other"


class TestSharedProjectRemove:
    def test_remove_shared_project(self):
        p = SharedProject(
            team_name="t", git_identity="o/r", folder_suffix="o-r",
        )
        removed = p.remove()
        assert removed.status == SharedProjectStatus.REMOVED

    def test_remove_already_removed_raises(self):
        p = SharedProject(
            team_name="t", git_identity="o/r", folder_suffix="o-r",
            status=SharedProjectStatus.REMOVED,
        )
        with pytest.raises(InvalidTransitionError):
            p.remove()


class TestDeriveFolderSuffix:
    def test_simple_identity(self):
        assert derive_folder_suffix("jayantdevkar/claude-karma") == "jayantdevkar-claude-karma"

    def test_nested_identity(self):
        assert derive_folder_suffix("org/sub/repo") == "org-sub-repo"

    def test_strips_dotgit(self):
        assert derive_folder_suffix("jayantdevkar/claude-karma.git") == "jayantdevkar-claude-karma"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/test_domain_project.py -v`
Expected: FAIL

- [ ] **Step 3: Implement SharedProject model**

```python
# api/domain/project.py
"""SharedProject domain model — a git project shared with a team."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from domain.team import InvalidTransitionError


class SharedProjectStatus(str, Enum):
    SHARED = "shared"
    REMOVED = "removed"


def derive_folder_suffix(git_identity: str) -> str:
    """Derive Syncthing folder suffix from git identity.

    'jayantdevkar/claude-karma' → 'jayantdevkar-claude-karma'
    'jayantdevkar/claude-karma.git' → 'jayantdevkar-claude-karma'
    """
    suffix = git_identity.replace("/", "-")
    if suffix.endswith(".git"):
        suffix = suffix[:-4]
    return suffix


class SharedProject(BaseModel):
    model_config = ConfigDict(frozen=True)

    team_name: str
    git_identity: str
    encoded_name: str | None = None
    folder_suffix: str
    status: SharedProjectStatus = SharedProjectStatus.SHARED
    shared_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def remove(self) -> SharedProject:
        if self.status == SharedProjectStatus.REMOVED:
            raise InvalidTransitionError(
                f"Project '{self.git_identity}' is already removed"
            )
        return self.model_copy(update={"status": SharedProjectStatus.REMOVED})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && pytest tests/test_domain_project.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add api/domain/project.py api/tests/test_domain_project.py
git commit -m "feat(sync-v4): add SharedProject domain model"
```

---

### Task 4: Subscription Domain Model

**Files:**
- Create: `api/domain/subscription.py`
- Test: `api/tests/test_domain_subscription.py`

**CAN PARALLEL with Tasks 1-3, 5**

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_domain_subscription.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from domain.team import InvalidTransitionError


class TestSubscriptionCreation:
    def test_defaults(self):
        s = Subscription(
            member_tag="a.l", team_name="t",
            project_git_identity="o/r",
        )
        assert s.status == SubscriptionStatus.OFFERED
        assert s.direction == SyncDirection.BOTH

    def test_frozen(self):
        s = Subscription(member_tag="a.l", team_name="t", project_git_identity="o/r")
        with pytest.raises(Exception):
            s.status = SubscriptionStatus.ACCEPTED


class TestSubscriptionAccept:
    def test_accept_with_direction(self):
        s = Subscription(member_tag="a.l", team_name="t", project_git_identity="o/r")
        accepted = s.accept(SyncDirection.RECEIVE)
        assert accepted.status == SubscriptionStatus.ACCEPTED
        assert accepted.direction == SyncDirection.RECEIVE

    def test_accept_defaults_to_both(self):
        s = Subscription(member_tag="a.l", team_name="t", project_git_identity="o/r")
        accepted = s.accept()
        assert accepted.direction == SyncDirection.BOTH

    def test_accept_from_non_offered_raises(self):
        s = Subscription(
            member_tag="a.l", team_name="t", project_git_identity="o/r",
            status=SubscriptionStatus.ACCEPTED,
        )
        with pytest.raises(InvalidTransitionError):
            s.accept()


class TestSubscriptionPause:
    def test_pause_from_accepted(self):
        s = Subscription(
            member_tag="a.l", team_name="t", project_git_identity="o/r",
            status=SubscriptionStatus.ACCEPTED,
        )
        paused = s.pause()
        assert paused.status == SubscriptionStatus.PAUSED

    def test_pause_from_offered_raises(self):
        s = Subscription(member_tag="a.l", team_name="t", project_git_identity="o/r")
        with pytest.raises(InvalidTransitionError):
            s.pause()


class TestSubscriptionResume:
    def test_resume_from_paused(self):
        s = Subscription(
            member_tag="a.l", team_name="t", project_git_identity="o/r",
            status=SubscriptionStatus.PAUSED, direction=SyncDirection.SEND,
        )
        resumed = s.resume()
        assert resumed.status == SubscriptionStatus.ACCEPTED
        assert resumed.direction == SyncDirection.SEND  # preserves direction

    def test_resume_from_accepted_raises(self):
        s = Subscription(
            member_tag="a.l", team_name="t", project_git_identity="o/r",
            status=SubscriptionStatus.ACCEPTED,
        )
        with pytest.raises(InvalidTransitionError):
            s.resume()


class TestSubscriptionDecline:
    def test_decline_from_offered(self):
        s = Subscription(member_tag="a.l", team_name="t", project_git_identity="o/r")
        declined = s.decline()
        assert declined.status == SubscriptionStatus.DECLINED

    def test_decline_from_accepted(self):
        s = Subscription(
            member_tag="a.l", team_name="t", project_git_identity="o/r",
            status=SubscriptionStatus.ACCEPTED,
        )
        declined = s.decline()
        assert declined.status == SubscriptionStatus.DECLINED

    def test_decline_from_paused(self):
        s = Subscription(
            member_tag="a.l", team_name="t", project_git_identity="o/r",
            status=SubscriptionStatus.PAUSED,
        )
        declined = s.decline()
        assert declined.status == SubscriptionStatus.DECLINED

    def test_decline_from_declined_raises(self):
        s = Subscription(
            member_tag="a.l", team_name="t", project_git_identity="o/r",
            status=SubscriptionStatus.DECLINED,
        )
        with pytest.raises(InvalidTransitionError):
            s.decline()


class TestSubscriptionChangeDirection:
    def test_change_direction(self):
        s = Subscription(
            member_tag="a.l", team_name="t", project_git_identity="o/r",
            status=SubscriptionStatus.ACCEPTED, direction=SyncDirection.BOTH,
        )
        changed = s.change_direction(SyncDirection.RECEIVE)
        assert changed.direction == SyncDirection.RECEIVE
        assert changed.status == SubscriptionStatus.ACCEPTED

    def test_change_direction_when_not_accepted_raises(self):
        s = Subscription(member_tag="a.l", team_name="t", project_git_identity="o/r")
        with pytest.raises(InvalidTransitionError):
            s.change_direction(SyncDirection.SEND)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/test_domain_subscription.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Subscription model**

```python
# api/domain/subscription.py
"""Subscription domain model — member-project relationship with sync direction."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from domain.team import InvalidTransitionError


class SubscriptionStatus(str, Enum):
    OFFERED = "offered"
    ACCEPTED = "accepted"
    PAUSED = "paused"
    DECLINED = "declined"


class SyncDirection(str, Enum):
    RECEIVE = "receive"
    SEND = "send"
    BOTH = "both"


class Subscription(BaseModel):
    model_config = ConfigDict(frozen=True)

    member_tag: str
    team_name: str
    project_git_identity: str
    status: SubscriptionStatus = SubscriptionStatus.OFFERED
    direction: SyncDirection = SyncDirection.BOTH
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def accept(self, direction: SyncDirection = SyncDirection.BOTH) -> Subscription:
        if self.status != SubscriptionStatus.OFFERED:
            raise InvalidTransitionError(
                f"Can only accept from 'offered' state, currently '{self.status.value}'"
            )
        return self.model_copy(update={
            "status": SubscriptionStatus.ACCEPTED,
            "direction": direction,
            "updated_at": datetime.now(timezone.utc),
        })

    def pause(self) -> Subscription:
        if self.status != SubscriptionStatus.ACCEPTED:
            raise InvalidTransitionError(
                f"Can only pause from 'accepted' state, currently '{self.status.value}'"
            )
        return self.model_copy(update={
            "status": SubscriptionStatus.PAUSED,
            "updated_at": datetime.now(timezone.utc),
        })

    def resume(self) -> Subscription:
        if self.status != SubscriptionStatus.PAUSED:
            raise InvalidTransitionError(
                f"Can only resume from 'paused' state, currently '{self.status.value}'"
            )
        return self.model_copy(update={
            "status": SubscriptionStatus.ACCEPTED,
            "updated_at": datetime.now(timezone.utc),
        })

    def decline(self) -> Subscription:
        if self.status == SubscriptionStatus.DECLINED:
            raise InvalidTransitionError("Already declined")
        return self.model_copy(update={
            "status": SubscriptionStatus.DECLINED,
            "updated_at": datetime.now(timezone.utc),
        })

    def change_direction(self, direction: SyncDirection) -> Subscription:
        if self.status != SubscriptionStatus.ACCEPTED:
            raise InvalidTransitionError(
                f"Can only change direction in 'accepted' state, currently '{self.status.value}'"
            )
        return self.model_copy(update={
            "direction": direction,
            "updated_at": datetime.now(timezone.utc),
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && pytest tests/test_domain_subscription.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add api/domain/subscription.py api/tests/test_domain_subscription.py
git commit -m "feat(sync-v4): add Subscription domain model with state machine"
```

---

### Task 5: SyncEvent Domain Model

**Files:**
- Create: `api/domain/events.py`
- Test: `api/tests/test_domain_events.py`

**CAN PARALLEL with Tasks 1-4**

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_domain_events.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from domain.events import SyncEvent, SyncEventType


class TestSyncEventCreation:
    def test_create_team_created_event(self):
        event = SyncEvent(
            event_type=SyncEventType.TEAM_CREATED,
            team_name="karma-team",
        )
        assert event.event_type == SyncEventType.TEAM_CREATED
        assert event.team_name == "karma-team"
        assert event.member_tag is None
        assert event.created_at is not None

    def test_create_member_added_event_with_detail(self):
        event = SyncEvent(
            event_type=SyncEventType.MEMBER_ADDED,
            team_name="karma-team",
            member_tag="ayush.laptop",
            detail={"device_id": "DEV-1", "added_by": "jayant.macbook"},
        )
        assert event.detail["device_id"] == "DEV-1"
        assert event.detail["added_by"] == "jayant.macbook"

    def test_create_session_packaged_event(self):
        event = SyncEvent(
            event_type=SyncEventType.SESSION_PACKAGED,
            team_name="t",
            member_tag="j.m",
            project_git_identity="o/r",
            session_uuid="abc-123",
            detail={"branches": ["main", "feature-x"]},
        )
        assert event.session_uuid == "abc-123"
        assert event.project_git_identity == "o/r"

    def test_event_is_frozen(self):
        event = SyncEvent(event_type=SyncEventType.TEAM_CREATED, team_name="t")
        with pytest.raises(Exception):
            event.team_name = "other"


class TestSyncEventTypes:
    def test_all_event_types_exist(self):
        expected = {
            "team_created", "team_dissolved",
            "member_added", "member_activated", "member_removed", "member_auto_left",
            "project_shared", "project_removed",
            "subscription_offered", "subscription_accepted",
            "subscription_paused", "subscription_resumed", "subscription_declined",
            "direction_changed",
            "session_packaged", "session_received",
            "device_paired", "device_unpaired",
        }
        actual = {e.value for e in SyncEventType}
        assert actual == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/test_domain_events.py -v`
Expected: FAIL

- [ ] **Step 3: Implement SyncEvent model**

```python
# api/domain/events.py
"""Sync event types for the audit trail."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class SyncEventType(str, Enum):
    TEAM_CREATED = "team_created"
    TEAM_DISSOLVED = "team_dissolved"
    MEMBER_ADDED = "member_added"
    MEMBER_ACTIVATED = "member_activated"
    MEMBER_REMOVED = "member_removed"
    MEMBER_AUTO_LEFT = "member_auto_left"
    PROJECT_SHARED = "project_shared"
    PROJECT_REMOVED = "project_removed"
    SUBSCRIPTION_OFFERED = "subscription_offered"
    SUBSCRIPTION_ACCEPTED = "subscription_accepted"
    SUBSCRIPTION_PAUSED = "subscription_paused"
    SUBSCRIPTION_RESUMED = "subscription_resumed"
    SUBSCRIPTION_DECLINED = "subscription_declined"
    DIRECTION_CHANGED = "direction_changed"
    SESSION_PACKAGED = "session_packaged"
    SESSION_RECEIVED = "session_received"
    DEVICE_PAIRED = "device_paired"
    DEVICE_UNPAIRED = "device_unpaired"


class SyncEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_type: SyncEventType
    team_name: str | None = None
    member_tag: str | None = None
    project_git_identity: str | None = None
    session_uuid: str | None = None
    detail: dict | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && pytest tests/test_domain_events.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add api/domain/events.py api/tests/test_domain_events.py
git commit -m "feat(sync-v4): add SyncEvent domain model with typed event types"
```

---

### Task 6: Schema v19 Migration

**Files:**
- Modify: `api/db/schema.py` (add v19 migration)
- Test: `api/tests/test_schema_v19.py`

**SEQUENTIAL — after Tasks 1-5 (needs domain model understanding)**

- [ ] **Step 1: Write failing tests**

```python
# api/tests/test_schema_v19.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pytest
from db.schema import ensure_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


class TestV19Tables:
    def test_sync_teams_exists(self, conn):
        conn.execute("INSERT INTO sync_teams (name, leader_device_id, leader_member_tag) VALUES ('t', 'D', 'j.m')")
        row = conn.execute("SELECT * FROM sync_teams WHERE name='t'").fetchone()
        assert row["status"] == "active"

    def test_sync_members_exists(self, conn):
        conn.execute("INSERT INTO sync_teams (name, leader_device_id, leader_member_tag) VALUES ('t', 'D', 'j.m')")
        conn.execute(
            "INSERT INTO sync_members (team_name, member_tag, device_id, user_id, machine_tag) "
            "VALUES ('t', 'j.m', 'D', 'j', 'm')"
        )
        row = conn.execute("SELECT * FROM sync_members WHERE member_tag='j.m'").fetchone()
        assert row["status"] == "added"
        assert row["updated_at"] is not None

    def test_sync_projects_pk_is_git_identity(self, conn):
        conn.execute("INSERT INTO sync_teams (name, leader_device_id, leader_member_tag) VALUES ('t', 'D', 'j.m')")
        conn.execute(
            "INSERT INTO sync_projects (team_name, git_identity, folder_suffix) "
            "VALUES ('t', 'owner/repo', 'owner-repo')"
        )
        row = conn.execute("SELECT * FROM sync_projects WHERE git_identity='owner/repo'").fetchone()
        assert row["encoded_name"] is None  # nullable
        assert row["status"] == "shared"

    def test_sync_subscriptions_exists(self, conn):
        conn.execute("INSERT INTO sync_teams (name, leader_device_id, leader_member_tag) VALUES ('t', 'D', 'j.m')")
        conn.execute(
            "INSERT INTO sync_members (team_name, member_tag, device_id, user_id, machine_tag) "
            "VALUES ('t', 'a.l', 'D2', 'a', 'l')"
        )
        conn.execute(
            "INSERT INTO sync_projects (team_name, git_identity, folder_suffix) "
            "VALUES ('t', 'o/r', 'o-r')"
        )
        conn.execute(
            "INSERT INTO sync_subscriptions (member_tag, team_name, project_git_identity) "
            "VALUES ('a.l', 't', 'o/r')"
        )
        row = conn.execute("SELECT * FROM sync_subscriptions").fetchone()
        assert row["status"] == "offered"
        assert row["direction"] == "both"

    def test_sync_events_uses_git_identity_column(self, conn):
        conn.execute(
            "INSERT INTO sync_events (event_type, team_name, project_git_identity) "
            "VALUES ('team_created', 't', 'o/r')"
        )
        row = conn.execute("SELECT * FROM sync_events").fetchone()
        assert row["project_git_identity"] == "o/r"


class TestV19Cascades:
    def test_delete_team_cascades_members(self, conn):
        conn.execute("INSERT INTO sync_teams (name, leader_device_id, leader_member_tag) VALUES ('t', 'D', 'j.m')")
        conn.execute(
            "INSERT INTO sync_members (team_name, member_tag, device_id, user_id, machine_tag) "
            "VALUES ('t', 'a.l', 'D2', 'a', 'l')"
        )
        conn.execute("DELETE FROM sync_teams WHERE name='t'")
        assert conn.execute("SELECT COUNT(*) FROM sync_members").fetchone()[0] == 0

    def test_delete_team_cascades_subscriptions(self, conn):
        conn.execute("INSERT INTO sync_teams (name, leader_device_id, leader_member_tag) VALUES ('t', 'D', 'j.m')")
        conn.execute(
            "INSERT INTO sync_members (team_name, member_tag, device_id, user_id, machine_tag) "
            "VALUES ('t', 'a.l', 'D2', 'a', 'l')"
        )
        conn.execute(
            "INSERT INTO sync_projects (team_name, git_identity, folder_suffix) VALUES ('t', 'o/r', 'o-r')"
        )
        conn.execute(
            "INSERT INTO sync_subscriptions (member_tag, team_name, project_git_identity) "
            "VALUES ('a.l', 't', 'o/r')"
        )
        conn.execute("DELETE FROM sync_teams WHERE name='t'")
        assert conn.execute("SELECT COUNT(*) FROM sync_subscriptions").fetchone()[0] == 0


class TestV19Constraints:
    def test_team_status_check(self, conn):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sync_teams (name, leader_device_id, leader_member_tag, status) "
                "VALUES ('t', 'D', 'j.m', 'invalid')"
            )

    def test_member_status_check(self, conn):
        conn.execute("INSERT INTO sync_teams (name, leader_device_id, leader_member_tag) VALUES ('t', 'D', 'j.m')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sync_members (team_name, member_tag, device_id, user_id, machine_tag, status) "
                "VALUES ('t', 'a.l', 'D2', 'a', 'l', 'invalid')"
            )

    def test_subscription_direction_check(self, conn):
        conn.execute("INSERT INTO sync_teams (name, leader_device_id, leader_member_tag) VALUES ('t', 'D', 'j.m')")
        conn.execute(
            "INSERT INTO sync_members (team_name, member_tag, device_id, user_id, machine_tag) "
            "VALUES ('t', 'a.l', 'D2', 'a', 'l')"
        )
        conn.execute(
            "INSERT INTO sync_projects (team_name, git_identity, folder_suffix) VALUES ('t', 'o/r', 'o-r')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO sync_subscriptions (member_tag, team_name, project_git_identity, direction) "
                "VALUES ('a.l', 't', 'o/r', 'invalid')"
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/test_schema_v19.py -v`
Expected: FAIL — v19 tables don't exist yet

- [ ] **Step 3: Add v19 migration to schema.py**

Add the following migration block to `api/db/schema.py` inside the `ensure_schema()` function, after the v18 migration block. Read the file first to find the exact insertion point.

```python
# v19: Sync v4 — domain model rewrite. Clean slate for sync tables.
if version < 19:
    # Drop all v3 sync tables
    cur.execute("DROP TABLE IF EXISTS sync_subscriptions")
    cur.execute("DROP TABLE IF EXISTS sync_rejected_folders")
    cur.execute("DROP TABLE IF EXISTS sync_settings")
    cur.execute("DROP TABLE IF EXISTS sync_removed_members")
    cur.execute("DROP TABLE IF EXISTS sync_events")
    cur.execute("DROP TABLE IF EXISTS sync_team_projects")
    cur.execute("DROP TABLE IF EXISTS sync_members")
    cur.execute("DROP TABLE IF EXISTS sync_teams")

    # Recreate with v4 schema
    cur.execute("""
        CREATE TABLE sync_teams (
            name             TEXT PRIMARY KEY,
            leader_device_id TEXT NOT NULL,
            leader_member_tag TEXT NOT NULL,
            status           TEXT NOT NULL DEFAULT 'active'
                             CHECK(status IN ('active', 'dissolved')),
            created_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("""
        CREATE TABLE sync_members (
            team_name        TEXT NOT NULL REFERENCES sync_teams(name) ON DELETE CASCADE,
            member_tag       TEXT NOT NULL,
            device_id        TEXT NOT NULL,
            user_id          TEXT NOT NULL,
            machine_tag      TEXT NOT NULL,
            status           TEXT NOT NULL DEFAULT 'added'
                             CHECK(status IN ('added', 'active', 'removed')),
            added_at         TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (team_name, member_tag)
        )
    """)
    cur.execute("""
        CREATE TABLE sync_projects (
            team_name        TEXT NOT NULL REFERENCES sync_teams(name) ON DELETE CASCADE,
            git_identity     TEXT NOT NULL,
            encoded_name     TEXT,
            folder_suffix    TEXT NOT NULL,
            status           TEXT NOT NULL DEFAULT 'shared'
                             CHECK(status IN ('shared', 'removed')),
            shared_at        TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (team_name, git_identity)
        )
    """)
    cur.execute("""
        CREATE TABLE sync_subscriptions (
            member_tag       TEXT NOT NULL,
            team_name        TEXT NOT NULL,
            project_git_identity TEXT NOT NULL,
            status           TEXT NOT NULL DEFAULT 'offered'
                             CHECK(status IN ('offered', 'accepted', 'paused', 'declined')),
            direction        TEXT NOT NULL DEFAULT 'both'
                             CHECK(direction IN ('receive', 'send', 'both')),
            updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (member_tag, team_name, project_git_identity),
            FOREIGN KEY (team_name, member_tag)
                REFERENCES sync_members(team_name, member_tag) ON DELETE CASCADE,
            FOREIGN KEY (team_name, project_git_identity)
                REFERENCES sync_projects(team_name, git_identity) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE sync_events (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type       TEXT NOT NULL,
            team_name        TEXT,
            member_tag       TEXT,
            project_git_identity TEXT,
            session_uuid     TEXT,
            detail           TEXT,
            created_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("""
        CREATE TABLE sync_removed_members (
            team_name        TEXT NOT NULL REFERENCES sync_teams(name) ON DELETE CASCADE,
            device_id        TEXT NOT NULL,
            member_tag       TEXT,
            removed_at       TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (team_name, device_id)
        )
    """)
    # Indexes
    cur.execute("CREATE INDEX idx_members_device ON sync_members(device_id)")
    cur.execute("CREATE INDEX idx_members_status ON sync_members(team_name, status)")
    cur.execute("CREATE INDEX idx_projects_suffix ON sync_projects(folder_suffix)")
    cur.execute("CREATE INDEX idx_projects_git ON sync_projects(git_identity)")
    cur.execute("CREATE INDEX idx_subs_member ON sync_subscriptions(member_tag)")
    cur.execute("CREATE INDEX idx_subs_status ON sync_subscriptions(status)")
    cur.execute("CREATE INDEX idx_subs_project ON sync_subscriptions(project_git_identity)")
    cur.execute("CREATE INDEX idx_events_type ON sync_events(event_type)")
    cur.execute("CREATE INDEX idx_events_team ON sync_events(team_name)")
    cur.execute("CREATE INDEX idx_events_time ON sync_events(created_at)")

    cur.execute("PRAGMA user_version = 19")
```

Also update the `CURRENT_VERSION` constant at the top of schema.py to `19`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && pytest tests/test_schema_v19.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run existing tests to verify no regressions**

Run: `cd api && pytest tests/test_db.py -v`
Expected: ALL PASS (existing tests should still work)

- [ ] **Step 6: Commit**

```bash
git add api/db/schema.py api/tests/test_schema_v19.py
git commit -m "feat(sync-v4): add v19 schema migration — clean slate sync tables"
```

---

### Task 7: Repositories

**Files:**
- Create: `api/repositories/__init__.py`
- Create: `api/repositories/team_repo.py`
- Create: `api/repositories/member_repo.py`
- Create: `api/repositories/project_repo.py`
- Create: `api/repositories/subscription_repo.py`
- Create: `api/repositories/event_repo.py`
- Test: `api/tests/test_repo_team.py`
- Test: `api/tests/test_repo_member.py`
- Test: `api/tests/test_repo_project.py`
- Test: `api/tests/test_repo_subscription.py`
- Test: `api/tests/test_repo_event.py`

**SEQUENTIAL — after Task 6 (needs schema). But 5 repos can be written in parallel.**

Each repo follows the same pattern. I'll show TeamRepo in full; others follow the same structure.

- [ ] **Step 1: Create repo package + write TeamRepo failing tests**

```python
# api/repositories/__init__.py
"""Sync v4 repositories — thin SQLite persistence layer."""

# api/tests/test_repo_team.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pytest
from db.schema import ensure_schema
from domain.team import Team, TeamStatus
from repositories.team_repo import TeamRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


@pytest.fixture
def repo():
    return TeamRepository()


class TestTeamRepoSave:
    def test_save_new_team(self, conn, repo):
        team = Team(name="t", leader_device_id="D", leader_member_tag="j.m")
        repo.save(conn, team)
        result = repo.get(conn, "t")
        assert result is not None
        assert result.name == "t"
        assert result.status == TeamStatus.ACTIVE

    def test_save_updates_existing(self, conn, repo):
        team = Team(name="t", leader_device_id="D", leader_member_tag="j.m")
        repo.save(conn, team)
        dissolved = team.dissolve(by_device="D")
        repo.save(conn, dissolved)
        result = repo.get(conn, "t")
        assert result.status == TeamStatus.DISSOLVED


class TestTeamRepoGet:
    def test_get_nonexistent_returns_none(self, conn, repo):
        assert repo.get(conn, "nope") is None


class TestTeamRepoList:
    def test_list_all(self, conn, repo):
        repo.save(conn, Team(name="a", leader_device_id="D1", leader_member_tag="j.m1"))
        repo.save(conn, Team(name="b", leader_device_id="D2", leader_member_tag="j.m2"))
        teams = repo.list_all(conn)
        assert len(teams) == 2
        names = {t.name for t in teams}
        assert names == {"a", "b"}


class TestTeamRepoDelete:
    def test_delete_team(self, conn, repo):
        repo.save(conn, Team(name="t", leader_device_id="D", leader_member_tag="j.m"))
        repo.delete(conn, "t")
        assert repo.get(conn, "t") is None


class TestTeamRepoGetByLeader:
    def test_get_by_leader(self, conn, repo):
        repo.save(conn, Team(name="t1", leader_device_id="D", leader_member_tag="j.m"))
        repo.save(conn, Team(name="t2", leader_device_id="D", leader_member_tag="j.m"))
        repo.save(conn, Team(name="t3", leader_device_id="OTHER", leader_member_tag="a.l"))
        teams = repo.get_by_leader(conn, "D")
        assert len(teams) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/test_repo_team.py -v`
Expected: FAIL

- [ ] **Step 3: Implement TeamRepository**

```python
# api/repositories/team_repo.py
"""Team repository — SQLite persistence for Team domain model."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from domain.team import Team, TeamStatus


class TeamRepository:
    def get(self, conn: sqlite3.Connection, name: str) -> Team | None:
        row = conn.execute(
            "SELECT * FROM sync_teams WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_team(row)

    def get_by_leader(self, conn: sqlite3.Connection, device_id: str) -> list[Team]:
        rows = conn.execute(
            "SELECT * FROM sync_teams WHERE leader_device_id = ?", (device_id,)
        ).fetchall()
        return [self._row_to_team(r) for r in rows]

    def save(self, conn: sqlite3.Connection, team: Team) -> None:
        conn.execute(
            """INSERT INTO sync_teams (name, leader_device_id, leader_member_tag, status, created_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   leader_device_id = excluded.leader_device_id,
                   leader_member_tag = excluded.leader_member_tag,
                   status = excluded.status""",
            (team.name, team.leader_device_id, team.leader_member_tag,
             team.status.value, team.created_at.isoformat()),
        )
        conn.commit()

    def delete(self, conn: sqlite3.Connection, name: str) -> None:
        conn.execute("DELETE FROM sync_teams WHERE name = ?", (name,))
        conn.commit()

    def list_all(self, conn: sqlite3.Connection) -> list[Team]:
        rows = conn.execute("SELECT * FROM sync_teams").fetchall()
        return [self._row_to_team(r) for r in rows]

    @staticmethod
    def _row_to_team(row: sqlite3.Row) -> Team:
        return Team(
            name=row["name"],
            leader_device_id=row["leader_device_id"],
            leader_member_tag=row["leader_member_tag"],
            status=TeamStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd api && pytest tests/test_repo_team.py -v`
Expected: ALL PASS

- [ ] **Step 5: Write and implement remaining 4 repos (parallel)**

Each repo follows the same pattern as TeamRepository. Key method signatures:

**MemberRepository** (`api/repositories/member_repo.py`):
```python
class MemberRepository:
    def get(self, conn, team_name: str, member_tag: str) -> Member | None
    def get_by_device(self, conn, device_id: str) -> list[Member]
    def save(self, conn, member: Member) -> None  # UPSERT on (team_name, member_tag)
    def list_for_team(self, conn, team_name: str) -> list[Member]
    def was_removed(self, conn, team_name: str, device_id: str) -> bool
    def record_removal(self, conn, team_name: str, device_id: str, member_tag: str = None) -> None
```

**ProjectRepository** (`api/repositories/project_repo.py`):
```python
class ProjectRepository:
    def get(self, conn, team_name: str, git_identity: str) -> SharedProject | None
    def save(self, conn, project: SharedProject) -> None  # UPSERT on (team_name, git_identity)
    def list_for_team(self, conn, team_name: str) -> list[SharedProject]
    def find_by_suffix(self, conn, suffix: str) -> list[SharedProject]
    def find_by_git_identity(self, conn, git_identity: str) -> list[SharedProject]
```

**SubscriptionRepository** (`api/repositories/subscription_repo.py`):
```python
class SubscriptionRepository:
    def get(self, conn, member_tag: str, team_name: str, git_identity: str) -> Subscription | None
    def save(self, conn, sub: Subscription) -> None  # UPSERT on (member_tag, team_name, project_git_identity)
    def list_for_member(self, conn, member_tag: str) -> list[Subscription]
    def list_for_project(self, conn, team_name: str, git_identity: str) -> list[Subscription]
    def list_accepted_for_suffix(self, conn, suffix: str) -> list[Subscription]
```

**EventRepository** (`api/repositories/event_repo.py`):
```python
class EventRepository:
    def log(self, conn, event: SyncEvent) -> int  # returns event id
    def query(self, conn, *, team: str = None, event_type: str = None, limit: int = 50) -> list[SyncEvent]
```

Write test files: `test_repo_member.py`, `test_repo_project.py`, `test_repo_subscription.py`, `test_repo_event.py`. Follow the same test patterns as `test_repo_team.py`: fixture creates in-memory SQLite + `ensure_schema()`, tests cover save/get/list/edge cases.

- [ ] **Step 6: Run all repo tests**

Run: `cd api && pytest tests/test_repo_*.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add api/repositories/ api/tests/test_repo_*.py
git commit -m "feat(sync-v4): add repositories for all domain models"
```

---

### Task 8: Phase 1 Integration Test

**Files:**
- Test: `api/tests/test_sync_v4_foundation.py`

**SEQUENTIAL — after Task 7. Verifies the full domain→repo stack works together.**

- [ ] **Step 1: Write integration test**

```python
# api/tests/test_sync_v4_foundation.py
"""Integration test: domain models + repositories working together."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pytest
from db.schema import ensure_schema
from domain.team import Team, AuthorizationError
from domain.member import Member, MemberStatus
from domain.project import SharedProject, derive_folder_suffix
from domain.subscription import Subscription, SubscriptionStatus, SyncDirection
from domain.events import SyncEvent, SyncEventType
from repositories.team_repo import TeamRepository
from repositories.member_repo import MemberRepository
from repositories.project_repo import ProjectRepository
from repositories.subscription_repo import SubscriptionRepository
from repositories.event_repo import EventRepository


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


class TestFullWorkflow:
    """Simulates: create team → add member → share project → accept subscription."""

    def test_leader_creates_team_and_adds_member(self, conn):
        teams = TeamRepository()
        members = MemberRepository()
        projects = ProjectRepository()
        subs = SubscriptionRepository()
        events = EventRepository()

        # 1. Leader creates team
        team = Team(name="karma", leader_device_id="DEV-L", leader_member_tag="jayant.macbook")
        teams.save(conn, team)
        leader = Member(
            member_tag="jayant.macbook", team_name="karma",
            device_id="DEV-L", user_id="jayant", machine_tag="macbook",
            status=MemberStatus.ACTIVE,
        )
        members.save(conn, leader)

        # 2. Leader adds member
        new_member = Member.from_member_tag(
            member_tag="ayush.laptop", team_name="karma", device_id="DEV-A",
        )
        added = team.add_member(new_member, by_device="DEV-L")
        members.save(conn, added)

        # Verify member persisted
        loaded = members.get(conn, "karma", "ayush.laptop")
        assert loaded is not None
        assert loaded.status == MemberStatus.ADDED

        # 3. Leader shares project
        project = SharedProject(
            team_name="karma",
            git_identity="jayantdevkar/claude-karma",
            folder_suffix=derive_folder_suffix("jayantdevkar/claude-karma"),
        )
        projects.save(conn, project)

        # 4. Create subscription for new member
        sub = Subscription(
            member_tag="ayush.laptop", team_name="karma",
            project_git_identity="jayantdevkar/claude-karma",
        )
        subs.save(conn, sub)

        # 5. Member activates (device acknowledged)
        loaded_member = members.get(conn, "karma", "ayush.laptop")
        activated = loaded_member.activate()
        members.save(conn, activated)
        assert members.get(conn, "karma", "ayush.laptop").status == MemberStatus.ACTIVE

        # 6. Member accepts subscription
        loaded_sub = subs.get(conn, "ayush.laptop", "karma", "jayantdevkar/claude-karma")
        accepted = loaded_sub.accept(SyncDirection.BOTH)
        subs.save(conn, accepted)
        final_sub = subs.get(conn, "ayush.laptop", "karma", "jayantdevkar/claude-karma")
        assert final_sub.status == SubscriptionStatus.ACCEPTED
        assert final_sub.direction == SyncDirection.BOTH

        # 7. Log events
        events.log(conn, SyncEvent(
            event_type=SyncEventType.TEAM_CREATED, team_name="karma",
        ))
        events.log(conn, SyncEvent(
            event_type=SyncEventType.MEMBER_ADDED, team_name="karma",
            member_tag="ayush.laptop",
            detail={"device_id": "DEV-A", "added_by": "jayant.macbook"},
        ))
        logged = events.query(conn, team="karma")
        assert len(logged) == 2

    def test_non_leader_cannot_remove_member(self, conn):
        teams = TeamRepository()
        team = Team(name="t", leader_device_id="DEV-L", leader_member_tag="j.m")
        teams.save(conn, team)

        member = Member(
            member_tag="a.l", team_name="t", device_id="DEV-A",
            user_id="a", machine_tag="l", status=MemberStatus.ACTIVE,
        )
        with pytest.raises(AuthorizationError):
            team.remove_member(member, by_device="DEV-A")  # member tries to remove self

    def test_cascade_on_team_delete(self, conn):
        teams = TeamRepository()
        members = MemberRepository()
        projects = ProjectRepository()
        subs = SubscriptionRepository()

        team = Team(name="t", leader_device_id="D", leader_member_tag="j.m")
        teams.save(conn, team)
        members.save(conn, Member(
            member_tag="a.l", team_name="t", device_id="D2",
            user_id="a", machine_tag="l",
        ))
        projects.save(conn, SharedProject(
            team_name="t", git_identity="o/r", folder_suffix="o-r",
        ))
        subs.save(conn, Subscription(
            member_tag="a.l", team_name="t", project_git_identity="o/r",
        ))

        teams.delete(conn, "t")

        assert members.list_for_team(conn, "t") == []
        assert projects.list_for_team(conn, "t") == []
        assert subs.list_for_member(conn, "a.l") == []
```

- [ ] **Step 2: Run integration test**

Run: `cd api && pytest tests/test_sync_v4_foundation.py -v`
Expected: ALL PASS

- [ ] **Step 3: Run full Phase 1 test suite**

Run: `cd api && pytest tests/test_domain_*.py tests/test_schema_v19.py tests/test_repo_*.py tests/test_sync_v4_foundation.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add api/tests/test_sync_v4_foundation.py
git commit -m "test(sync-v4): add Phase 1 integration test — full domain+repo workflow"
```

---

## Phase 1 Completion Checklist

- [ ] All 5 domain models implemented with state machines
- [ ] v19 schema migration applied
- [ ] All 5 repositories implemented
- [ ] Integration test passes
- [ ] No regressions in existing test suite: `cd api && pytest -v`
- [ ] All Phase 1 code committed
