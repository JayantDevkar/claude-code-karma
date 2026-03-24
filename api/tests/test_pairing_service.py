"""
Tests for PairingService — permanent, deterministic pairing codes using base64url.
Backwards-compatible with legacy base32 codes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services.sync.pairing_service import PairingInfo, PairingService


@pytest.fixture
def service():
    return PairingService()


MEMBER_TAG = "alice.laptop"
DEVICE_ID = "AAAAAAA-BBBBBBB-CCCCCCC-DDDDDDD-EEEEEEE-FFFFFFF-GGGGGGG-HHHHHHH"


class TestGenerateCode:
    def test_returns_string(self, service):
        code = service.generate_code(MEMBER_TAG, DEVICE_ID)
        assert isinstance(code, str)

    def test_code_contains_dashes(self, service):
        code = service.generate_code(MEMBER_TAG, DEVICE_ID)
        assert "-" in code

    def test_code_is_base64url_chars(self, service):
        code = service.generate_code(MEMBER_TAG, DEVICE_ID)
        # All non-dash chars should be base64url-safe
        for part in code.split("-"):
            assert all(c.isalnum() or c in ("_", "-") for c in part)

    def test_code_blocks_are_1_to_6_chars(self, service):
        code = service.generate_code(MEMBER_TAG, DEVICE_ID)
        for part in code.split("-"):
            assert 1 <= len(part) <= 6

    def test_deterministic_same_input(self, service):
        code1 = service.generate_code(MEMBER_TAG, DEVICE_ID)
        code2 = service.generate_code(MEMBER_TAG, DEVICE_ID)
        assert code1 == code2

    def test_different_member_tag_different_code(self, service):
        code1 = service.generate_code("alice.laptop", DEVICE_ID)
        code2 = service.generate_code("bob.desktop", DEVICE_ID)
        assert code1 != code2

    def test_different_device_id_different_code(self, service):
        device2 = "ZZZZZZZ-YYYYYYY-XXXXXXX-WWWWWWW-VVVVVVV-UUUUUUU-TTTTTTT-SSSSSSS"
        code1 = service.generate_code(MEMBER_TAG, DEVICE_ID)
        code2 = service.generate_code(MEMBER_TAG, device2)
        assert code1 != code2

    def test_code_matches_expected_format(self, service):
        """Code should look like amF5LW-1hY2Jv (groups of up to 6 separated by dashes)."""
        code = service.generate_code(MEMBER_TAG, DEVICE_ID)
        parts = code.split("-")
        assert len(parts) >= 2  # At least 2 groups
        for part in parts:
            assert 1 <= len(part) <= 6
            assert all(c.isalnum() or c in ("_",) for c in part)


class TestValidateCode:
    def test_roundtrip_member_tag(self, service):
        code = service.generate_code(MEMBER_TAG, DEVICE_ID)
        info = service.validate_code(code)
        assert info.member_tag == MEMBER_TAG

    def test_roundtrip_device_id(self, service):
        code = service.generate_code(MEMBER_TAG, DEVICE_ID)
        info = service.validate_code(code)
        assert info.device_id == DEVICE_ID

    def test_returns_pairing_info_model(self, service):
        code = service.generate_code(MEMBER_TAG, DEVICE_ID)
        info = service.validate_code(code)
        assert isinstance(info, PairingInfo)

    def test_invalid_code_raises_value_error(self, service):
        with pytest.raises(ValueError):
            service.validate_code("INVALID-CODE-HERE")

    def test_empty_code_raises_value_error(self, service):
        with pytest.raises(ValueError):
            service.validate_code("")

    def test_whitespace_tolerant_validation(self, service):
        """Codes should decode successfully with extra spaces."""
        code = service.generate_code(MEMBER_TAG, DEVICE_ID)
        info = service.validate_code(f"  {code}  ")
        assert info.member_tag == MEMBER_TAG
        assert info.device_id == DEVICE_ID

    def test_legacy_base32_code_still_works(self, service):
        """Old base32 codes (all uppercase) should still decode."""
        import base64 as b64
        payload = f"{MEMBER_TAG}:{DEVICE_ID}"
        old_encoded = b64.b32encode(payload.encode()).decode().rstrip("=")
        old_blocks = [old_encoded[i:i+4] for i in range(0, len(old_encoded), 4)]
        old_code = "-".join(old_blocks)
        info = service.validate_code(old_code)
        assert info.member_tag == MEMBER_TAG
        assert info.device_id == DEVICE_ID

    def test_different_members_roundtrip(self, service):
        members = [
            ("alice.laptop", "AAAAAAA-BBBBBBB-CCCCCCC-DDDDDDD-EEEEEEE-FFFFFFF-GGGGGGG-HHHHHHH"),
            ("bob.desktop", "ZZZZZZZ-YYYYYYY-XXXXXXX-WWWWWWW-VVVVVVV-UUUUUUU-TTTTTTT-SSSSSSS"),
            ("carol.server", "1111111-2222222-3333333-4444444-5555555-6666666-7777777-8888888"),
        ]
        for member_tag, device_id in members:
            code = service.generate_code(member_tag, device_id)
            info = service.validate_code(code)
            assert info.member_tag == member_tag
            assert info.device_id == device_id


class TestMemberGeneratesLeaderDecodes:
    """End-to-end: member generates code on their machine, leader decodes on theirs.

    This simulates the real v4 flow:
    1. Member runs `GET /sync/pairing/code` → gets their pairing code
    2. Member shares code out-of-band (Slack, text, etc.)
    3. Leader pastes code into `POST /sync/teams/{name}/members` → decoded to PairingInfo
    4. Leader's TeamService uses PairingInfo to add the member
    """

    def test_member_code_decoded_by_separate_service_instance(self):
        """Simulates member and leader having separate PairingService instances."""
        member_svc = PairingService()  # member's machine
        leader_svc = PairingService()  # leader's machine

        member_tag = "ayush.work-laptop"
        device_id = "VRE7WLU-CXIVLS5-ARODGO7-22PNRQ3-7AAQ3ET-5CHXGA4-T5FKVKU-UM5QLQW"

        # Member generates
        code = member_svc.generate_code(member_tag, device_id)

        # Leader decodes
        info = leader_svc.validate_code(code)
        assert info.member_tag == member_tag
        assert info.device_id == device_id

    def test_verbose_hostname_member_tag(self):
        """Real-world case: auto-derived hostname creates long member_tag."""
        svc = PairingService()
        member_tag = "jay-macbook.jayants-macbook-pro-local"
        device_id = "VRE7WLU-CXIVLS5-ARODGO7-22PNRQ3-7AAQ3ET-5CHXGA4-T5FKVKU-UM5QLQW"

        code = svc.generate_code(member_tag, device_id)
        info = svc.validate_code(code)

        assert info.member_tag == member_tag
        assert info.device_id == device_id
        # Code should be manageable size (< 200 chars with base64url)
        assert len(code) < 200, f"Pairing code too long: {len(code)} chars"

    def test_code_survives_copy_paste_artifacts(self):
        """Code should decode even with trailing whitespace or newlines from paste."""
        svc = PairingService()
        code = svc.generate_code("alice.laptop", "MFZWI3D-BONSGYC-YLTMRWG-C43ENR5-QXGZDMM-FZWI3DP-BONSGYC-YLTMRWA")

        # Simulate sloppy paste with whitespace/newlines
        sloppy = f"\n  {code}  \n"
        info = svc.validate_code(sloppy)
        assert info.member_tag == "alice.laptop"

    def test_multiple_members_same_team(self):
        """Leader can decode codes from multiple different members."""
        leader_svc = PairingService()

        members = [
            ("alice.laptop", "MFZWI3D-BONSGYC-YLTMRWG-C43ENR5-QXGZDMM-FZWI3DP-BONSGYC-YLTMRWA"),
            ("bob.desktop", "VRE7WLU-CXIVLS5-ARODGO7-22PNRQ3-7AAQ3ET-5CHXGA4-T5FKVKU-UM5QLQW"),
            ("carol.server-rack-01", "XYZAAAA-BBBCCCC-DDDEEEE-FFFGGGG-HHHIIII-JJJKKKK-LLLMMMM-NNNOOOO"),
        ]

        for member_tag, device_id in members:
            member_svc = PairingService()  # each member has own instance
            code = member_svc.generate_code(member_tag, device_id)

            # Leader decodes each
            info = leader_svc.validate_code(code)
            assert info.member_tag == member_tag
            assert info.device_id == device_id

    def test_member_tag_with_special_characters(self):
        """Member tags derived from hostnames may have dashes and dots."""
        svc = PairingService()
        member_tag = "dev-user.my-machine-name"
        device_id = "ABCDEFG-HIJKLMN-OPQRSTU-VWXYZ23-4567ABC-DEFGHIJ-KLMNOPQ-RSTUVWX"

        code = svc.generate_code(member_tag, device_id)
        info = svc.validate_code(code)
        assert info.member_tag == member_tag
        assert info.device_id == device_id

    def test_same_member_different_teams_same_code(self):
        """A member's pairing code is permanent — works for any team."""
        svc = PairingService()
        member_tag = "alice.laptop"
        device_id = "MFZWI3D-BONSGYC-YLTMRWG-C43ENR5-QXGZDMM-FZWI3DP-BONSGYC-YLTMRWA"

        code1 = svc.generate_code(member_tag, device_id)
        code2 = svc.generate_code(member_tag, device_id)

        # Deterministic — same code every time (permanent, not per-team)
        assert code1 == code2

        # Leader of team A and leader of team B both decode the same identity
        info = svc.validate_code(code1)
        assert info.member_tag == member_tag
        assert info.device_id == device_id

    def test_legacy_v1_code_from_member_decoded_by_leader(self):
        """Member who generated a v1 (base32) code can still be added by a leader."""
        import base64 as b64

        member_tag = "old-user.old-machine"
        device_id = "MFZWI3D-BONSGYC-YLTMRWG-C43ENR5-QXGZDMM-FZWI3DP-BONSGYC-YLTMRWA"

        # Simulate old v1 code generation (base32, 4-char blocks)
        payload = f"{member_tag}:{device_id}"
        encoded = b64.b32encode(payload.encode()).decode().rstrip("=")
        blocks = [encoded[i:i+4] for i in range(0, len(encoded), 4)]
        v1_code = "-".join(blocks)

        # Leader with current service can still decode it
        leader_svc = PairingService()
        info = leader_svc.validate_code(v1_code)
        assert info.member_tag == member_tag
        assert info.device_id == device_id


class TestPairingInfo:
    def test_is_pydantic_model(self):
        info = PairingInfo(member_tag="alice.laptop", device_id="DEV-123")
        assert info.member_tag == "alice.laptop"
        assert info.device_id == "DEV-123"

    def test_immutable(self):
        info = PairingInfo(member_tag="alice.laptop", device_id="DEV-123")
        with pytest.raises(Exception):
            info.member_tag = "modified"
