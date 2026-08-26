"""services/session_glossary_lifecycle.py
=========================================
Track 2 — Dual-Tier Glossary Sync & Persistent User Vocabulary Store
Traceability: FR-14, NFR-03

Provides :class:`SessionGlossaryLifecycleManager`, managing the lifecycle, quota
monitoring, and automatic cleanup of transient Tier 2 GCP Translation glossaries and
staging TSV files in GCS.

Design invariants:
- **Regional Quota Enforcement** — Audits glossaries against regional limit of 1,000 in `us-central1`.
- **Automatic Pruning** — Deletes transient GCP glossary resources and GCS TSVs upon job completion or expiration.
- **Persistent Session Tracking** — Stores session glossary metadata on Modal Volume to survive restarts.
- **Graceful Deletion Handling** — Idempotent deletion handling with tolerance for already-deleted resources.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google.api_core import exceptions as gcp_exceptions
from google.cloud import storage
from google.cloud import translate_v3 as translate

from config.settings import gcp_settings
from services.byok_credentials_manager import BYOKCredentialsManager

logger = logging.getLogger(__name__)


@dataclass
class SessionGlossaryRecord:
    """Metadata tracking an active transient Tier 2 session glossary."""

    user_id: str
    session_id: str
    glossary_resource_name: str
    gcs_tsv_uri: str
    created_at: float = field(default_factory=time.time)
    status: str = "active"  # "active", "cleaned_up", "expired"

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "glossary_resource_name": self.glossary_resource_name,
            "gcs_tsv_uri": self.gcs_tsv_uri,
            "created_at": self.created_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionGlossaryRecord:
        return cls(
            user_id=data["user_id"],
            session_id=data["session_id"],
            glossary_resource_name=data["glossary_resource_name"],
            gcs_tsv_uri=data["gcs_tsv_uri"],
            created_at=float(data.get("created_at", time.time())),
            status=data.get("status", "active"),
        )


class SessionGlossaryLifecycleManager:
    """Coordinates lifecycle tracking, quota auditing, and cleanup of transient session glossaries."""

    def __init__(
        self,
        credentials_manager: BYOKCredentialsManager,
        storage_dir: Path | str | None = None,
        location: str = "us-central1",
    ) -> None:
        """Initialize SessionGlossaryLifecycleManager.

        Parameters
        ----------
        credentials_manager:
            BYOKCredentialsManager vending authenticated GCP clients for users.
        storage_dir:
            Directory where session tracking metadata is persisted.
            Defaults to `{gcp_settings.modal_volume_path}/glossary_sessions`.
        location:
            GCP regional endpoint for translation and glossaries.
        """
        self._creds_manager = credentials_manager
        self._location = location or gcp_settings.gcp_location

        if storage_dir is not None:
            self.storage_dir = Path(storage_dir)
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        else:
            default_path = Path(gcp_settings.modal_volume_path) / "glossary_sessions"
            try:
                default_path.mkdir(parents=True, exist_ok=True)
                self.storage_dir = default_path
            except (OSError, PermissionError):
                fallback_path = Path("data/glossary_sessions")
                fallback_path.mkdir(parents=True, exist_ok=True)
                self.storage_dir = fallback_path

        self._lock = threading.RLock()
        self._cache: dict[str, dict[str, SessionGlossaryRecord]] = {}
        logger.debug("SessionGlossaryLifecycleManager initialized at %s", self.storage_dir)

    def _get_meta_file(self, user_id: str) -> Path:
        clean_user_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", user_id.strip())
        return self.storage_dir / f"{clean_user_id}.json"

    def _load_user_sessions(self, user_id: str) -> dict[str, SessionGlossaryRecord]:
        with self._lock:
            if user_id in self._cache:
                return self._cache[user_id]

            meta_file = self._get_meta_file(user_id)
            sessions: dict[str, SessionGlossaryRecord] = {}
            if meta_file.exists():
                try:
                    content = meta_file.read_text(encoding="utf-8")
                    data = json.loads(content)
                    if isinstance(data, dict):
                        for sess_id, s_data in data.items():
                            sessions[sess_id] = SessionGlossaryRecord.from_dict(s_data)
                except Exception:
                    logger.exception("Failed to load session glossary metadata for %s", user_id)

            self._cache[user_id] = sessions
            return sessions

    def _save_user_sessions(self, user_id: str) -> None:
        with self._lock:
            sessions = self._cache.get(user_id, {})
            meta_file = self._get_meta_file(user_id)
            try:
                data = {sess_id: rec.to_dict() for sess_id, rec in sessions.items()}
                meta_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except Exception:
                logger.exception("Failed to persist session glossary metadata for %s", user_id)

    def register_session_glossary(
        self,
        user_id: str,
        session_id: str,
        glossary_resource_name: str,
        gcs_tsv_uri: str,
    ) -> SessionGlossaryRecord:
        """Register and track a new transient Tier 2 session glossary."""
        with self._lock:
            sessions = self._load_user_sessions(user_id)
            record = SessionGlossaryRecord(
                user_id=user_id,
                session_id=session_id,
                glossary_resource_name=glossary_resource_name,
                gcs_tsv_uri=gcs_tsv_uri,
                created_at=time.time(),
                status="active",
            )
            sessions[session_id] = record
            self._save_user_sessions(user_id)
            logger.info("Registered session glossary: %s for user %s", glossary_resource_name, user_id)
            return record

    def list_active_sessions(self, user_id: str) -> list[SessionGlossaryRecord]:
        """List currently active session glossaries for *user_id*."""
        with self._lock:
            sessions = self._load_user_sessions(user_id)
            return [s for s in sessions.values() if s.status == "active"]

    def cleanup_session_glossary(self, user_id: str, session_id: str) -> bool:
        """Delete GCP glossary resource and remove staged TSV from GCS for *session_id*."""
        with self._lock:
            sessions = self._load_user_sessions(user_id)
            record = sessions.get(session_id)
            if not record or record.status != "active":
                logger.debug("Session glossary %s not found or already inactive", session_id)
                return False

        logger.info("Starting cleanup for session glossary: %s", record.glossary_resource_name)

        # 1. Delete GCP Translation v3 glossary
        try:
            translate_client = self._creds_manager.get_translation_client(user_id)
            op = translate_client.delete_glossary(name=record.glossary_resource_name)
            op.result(timeout=60.0)
            logger.info("Successfully deleted GCP glossary resource: %s", record.glossary_resource_name)
        except gcp_exceptions.NotFound:
            logger.info("GCP glossary resource already removed: %s", record.glossary_resource_name)
        except Exception:
            logger.exception(
                "Error deleting GCP glossary %s during cleanup",
                record.glossary_resource_name,
            )

        # 2. Delete GCS TSV staging object
        if record.gcs_tsv_uri and record.gcs_tsv_uri.startswith("gs://"):
            try:
                parts = record.gcs_tsv_uri[5:].split("/", 1)
                if len(parts) == 2:
                    bucket_name, blob_name = parts[0], parts[1]
                    storage_client = self._creds_manager.get_storage_client(user_id)
                    bucket = storage_client.bucket(bucket_name)
                    blob = bucket.blob(blob_name)
                    blob.delete()
                    logger.info("Deleted staged GCS TSV file: %s", record.gcs_tsv_uri)
            except gcp_exceptions.NotFound:
                logger.info("GCS TSV blob already removed: %s", record.gcs_tsv_uri)
            except Exception:
                logger.exception("Error deleting GCS TSV blob %s during cleanup", record.gcs_tsv_uri)

        # 3. Update record status
        with self._lock:
            record.status = "cleaned_up"
            self._save_user_sessions(user_id)

        return True

    def audit_project_glossaries(self, user_id: str) -> dict[str, Any]:
        """Audit regional glossaries in the user's GCP project against quota limits."""
        project_id = self._creds_manager.get_project_id(user_id)
        translate_client = self._creds_manager.get_translation_client(user_id)
        parent = f"projects/{project_id}/locations/{self._location}"

        try:
            glossaries_iterator = translate_client.list_glossaries(parent=parent)
            glossary_list = list(glossaries_iterator)
        except Exception:
            logger.exception("Failed to list regional glossaries for project %s", project_id)
            glossary_list = []

        total_count = len(glossary_list)
        quota_limit = gcp_settings.gcp_glossary_quota_limit
        warning_threshold = gcp_settings.gcp_glossary_warning_threshold
        approaching_quota = total_count >= warning_threshold

        if approaching_quota:
            logger.warning(
                "GCP Glossary Quota Alert: Project %s has %d glossaries in region %s "
                "(threshold: %d, limit: %d). Automated cleanup recommended.",
                project_id,
                total_count,
                self._location,
                warning_threshold,
                quota_limit,
            )

        summaries = [
            {
                "name": getattr(g, "name", str(g)),
                "entry_count": getattr(g, "entry_count", 0),
            }
            for g in glossary_list
        ]

        return {
            "glossaries": summaries,
            "total_count": total_count,
            "quota_limit": quota_limit,
            "warning_threshold": warning_threshold,
            "approaching_quota": approaching_quota,
        }

    def cleanup_expired_glossaries(self, user_id: str, max_age_hours: int = 24) -> int:
        """Prune active session glossaries older than *max_age_hours*."""
        now = time.time()
        max_age_sec = max_age_hours * 3600
        active_sessions = self.list_active_sessions(user_id)

        cleaned_count = 0
        for rec in active_sessions:
            if (now - rec.created_at) >= max_age_sec:
                logger.info(
                    "Pruning expired session glossary: %s (age: %.1f hours)",
                    rec.session_id,
                    (now - rec.created_at) / 3600,
                )
                if self.cleanup_session_glossary(user_id, rec.session_id):
                    cleaned_count += 1

        return cleaned_count
