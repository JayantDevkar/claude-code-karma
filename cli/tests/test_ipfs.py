"""Tests for IPFS subprocess wrapper."""

import subprocess
from unittest.mock import patch, MagicMock

import pytest

from karma.ipfs import IPFSClient


class TestIPFSClient:
    def test_init_default_api(self):
        client = IPFSClient()
        assert client.api_url == "http://127.0.0.1:5001"

    @patch("karma.ipfs.subprocess.run")
    def test_is_running_true(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="0.28.0\n")
        client = IPFSClient()
        assert client.is_running() is True

    @patch("karma.ipfs.subprocess.run")
    def test_is_running_false(self, mock_run):
        mock_run.side_effect = FileNotFoundError("ipfs not found")
        client = IPFSClient()
        assert client.is_running() is False

    @patch("karma.ipfs.subprocess.run")
    def test_add_directory(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="QmTestHash123\n", stderr=""
        )
        client = IPFSClient()
        cid = client.add("/tmp/test-dir", recursive=True)
        assert cid == "QmTestHash123"
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "add" in cmd
        assert "-r" in cmd
        assert "-Q" in cmd

    @patch("karma.ipfs.subprocess.run")
    def test_add_raises_on_failure(self, mock_run):
        mock_run.side_effect = subprocess.CalledProcessError(1, "ipfs add")
        client = IPFSClient()
        with pytest.raises(subprocess.CalledProcessError):
            client.add("/tmp/nonexistent")

    @patch("karma.ipfs.subprocess.run")
    def test_get(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        client = IPFSClient()
        client.get("QmTestHash123", "/tmp/output")
        cmd = mock_run.call_args[0][0]
        assert "get" in cmd
        assert "QmTestHash123" in cmd

    @patch("karma.ipfs.subprocess.run")
    def test_name_publish(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Published to k51...: /ipfs/QmTest\n"
        )
        client = IPFSClient()
        result = client.name_publish("QmTestHash123")
        assert "Published" in result

    @patch("karma.ipfs.subprocess.run")
    def test_name_resolve(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="/ipfs/QmResolvedHash\n"
        )
        client = IPFSClient()
        cid = client.name_resolve("k51testkey")
        assert cid == "/ipfs/QmResolvedHash"

    @patch("karma.ipfs.subprocess.run")
    def test_pin_ls(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"Keys":{"QmHash1":{"Type":"recursive"},"QmHash2":{"Type":"recursive"}}}\n',
        )
        client = IPFSClient()
        pins = client.pin_ls()
        assert "QmHash1" in pins
        assert "QmHash2" in pins

    @patch("karma.ipfs.subprocess.run")
    def test_id_returns_peer_info(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"ID":"12D3KooW...","Addresses":["/ip4/127.0.0.1/tcp/4001"]}\n',
        )
        client = IPFSClient()
        info = client.id()
        assert info["ID"].startswith("12D3")
