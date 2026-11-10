"""Integration tests for Ocean Event server-owned state.
Run with: python -m unittest discover -s tests -v
Requires the project's requirements.txt dependencies.
"""
import unittest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
import app as game


class OceanStateMachineTests(unittest.TestCase):
    def setUp(self):
        self.player = {"name": "Test", "best": 0}
        game._defaults(self.player)

    def test_client_cannot_start_session_without_server_authority(self):
        with self.assertRaises(PermissionError):
            game._ocean_start_session(self.player, object())
        self.assertIsNone(self.player["oceanEventSession"])

    def test_stages_must_be_defeated_in_order(self):
        event = game._ocean_start_session(self.player, game._OCEAN_SERVER_AUTHORITY)
        with self.assertRaises(ValueError):
            game._ocean_confirm_boss_defeat(
                self.player, event["eventId"], "long_vuong", game._OCEAN_SERVER_AUTHORITY
            )
        self.assertEqual(event["stage"], 1)
        for stage in game.OCEAN_STAGES:
            game._ocean_confirm_boss_defeat(
                self.player, event["eventId"], stage["bossId"], game._OCEAN_SERVER_AUTHORITY
            )
        self.assertEqual(event["status"], "EVENT_COMPLETED")
        self.assertEqual(self.player["oceanEventStage"], 5)
        self.assertTrue(self.player["oceanEventCompleted"])

    def test_duplicate_boss_defeat_is_rejected(self):
        event = game._ocean_start_session(self.player, game._OCEAN_SERVER_AUTHORITY)
        game._ocean_confirm_boss_defeat(
            self.player, event["eventId"], "hai_yeu_co_dai", game._OCEAN_SERVER_AUTHORITY
        )
        with self.assertRaises(ValueError):
            game._ocean_confirm_boss_defeat(
                self.player, event["eventId"], "hai_yeu_co_dai", game._OCEAN_SERVER_AUTHORITY
            )

    def test_dialogue_requires_completed_event_and_server_authority(self):
        event = game._ocean_start_session(self.player, game._OCEAN_SERVER_AUTHORITY)
        with self.assertRaises(ValueError):
            game._ocean_confirm_dialogue(self.player, event["eventId"], game._OCEAN_SERVER_AUTHORITY)
        for stage in game.OCEAN_STAGES:
            game._ocean_confirm_boss_defeat(
                self.player, event["eventId"], stage["bossId"], game._OCEAN_SERVER_AUTHORITY
            )
        with self.assertRaises(PermissionError):
            game._ocean_confirm_dialogue(self.player, event["eventId"], object())
        game._ocean_confirm_dialogue(self.player, event["eventId"], game._OCEAN_SERVER_AUTHORITY)
        self.assertTrue(event["dialogueComplete"])

    def test_ocean_battle_is_server_initialized_and_has_bounded_resources(self):
        battle = game._ocean_new_battle(self.player, 1)
        self.assertGreater(battle["bossHp"], 0)
        self.assertEqual(battle["playerHp"], battle["playerMaxHp"])
        self.assertEqual(battle["potions"], 3)
        self.assertEqual(battle["turn"], 0)
        next_battle = game._ocean_new_battle(self.player, 2, turn=7)
        self.assertEqual(next_battle["turn"], 7)

    def test_ocean_battle_public_projection_hides_internal_fields(self):
        event = game._ocean_start_session(self.player, game._OCEAN_SERVER_AUTHORITY)
        event["battle"] = game._ocean_new_battle(self.player, 1)
        public = game._ocean_battle_public(event)
        self.assertIn("bossHp", public)
        self.assertNotIn("guard", public)
        self.assertNotIn("lastActionAt", public)

    def test_public_status_does_not_expose_expiry_or_secret(self):
        event = game._ocean_start_session(self.player, game._OCEAN_SERVER_AUTHORITY)
        status = game._ocean_public_status(self.player)
        self.assertEqual(status["eventId"], event["eventId"])
        self.assertNotIn("expiresAt", status)
        self.assertNotIn("rewardClaimed", status)


    def test_trusted_transitions_are_persisted_before_return(self):
        players = {"test": self.player}
        with patch.object(game, "read_players", return_value=players), patch.object(game, "write_players") as save:
            event = game._ocean_start_for_player("test")
            self.assertEqual(save.call_count, 1)
            game._ocean_confirm_boss_for_player("test", event["eventId"], "hai_yeu_co_dai")
            self.assertEqual(save.call_count, 2)
            self.assertEqual(players["test"]["oceanEventSession"]["stage"], 2)

    def test_storage_failure_is_not_reported_as_success(self):
        players = {"test": self.player}
        with patch.object(game, "read_players", return_value=players), patch.object(game, "write_players", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                game._ocean_start_for_player("test")

    def test_expired_session_is_marked_expired(self):
        event = game._ocean_start_session(self.player, game._OCEAN_SERVER_AUTHORITY)
        past = datetime.now(timezone.utc) + timedelta(hours=7)
        self.assertTrue(game._ocean_expire_if_needed(self.player, now=past))
        self.assertEqual(event["status"], "EXPIRED")
        self.assertFalse(game._ocean_public_status(self.player)["active"])

    def test_claim_and_progress_routes_fail_closed(self):
        client = game.app.test_client()
        with client.session_transaction() as sess:
            sess["key"] = "not-a-real-account"
        self.assertEqual(client.post("/api/ocean/claim", json={"dialogueComplete": True}).status_code, 409)
        self.assertEqual(client.post("/api/ocean/progress", json={"stage": 5}).status_code, 409)
        self.assertEqual(client.get("/api/ocean/progress").status_code, 404)


if __name__ == "__main__":
    unittest.main()
