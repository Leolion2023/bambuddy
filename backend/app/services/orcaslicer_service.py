"""Service for integrating with OrcaSlicer CLI for slicing 3D models.

This service provides a Python wrapper around OrcaSlicer's command-line interface
or external OrcaSlicer API, allowing BambuDddy to slice STL/3MF files using configured slicer presets.

Supports two modes:
1. Local CLI mode - Direct OrcaSlicer executable invocation
2. External API mode - HTTP API (https://github.com/AFKFelix/orca-slicer-api)
"""

import asyncio
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.slicing_job import SlicingJob

logger = logging.getLogger(__name__)


class OrcaSlicerExternalAPI:
    """Client for external OrcaSlicer API (https://github.com/AFKFelix/orca-slicer-api)."""

    def __init__(self, api_url: str):
        """Initialize external API client.

        Args:
            api_url: Base URL of the OrcaSlicer API
        """
        self.api_url = api_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=300.0)  # 5 minute timeout for slicing

    async def health_check(self) -> bool:
        """Check if the API is available.

        Returns:
            True if API is reachable, False otherwise
        """
        try:
            response = await self.client.get(f"{self.api_url}/health")
            return response.status_code == 200
        except Exception as e:
            logger.debug("External API health check failed: %s", e)
            return False

    async def slice_file(
        self,
        input_file_path: str,
        output_file_path: str,
        filament_config: dict | None = None,
        printer_config: dict | None = None,
        process_config: dict | None = None,
    ) -> bool:
        """Submit a slicing job to the external API.

        Args:
            input_file_path: Path to input STL/3MF file
            output_file_path: Path where output gcode should be saved
            filament_config: Filament configuration JSON
            printer_config: Printer configuration JSON
            process_config: Process configuration JSON

        Returns:
            True if slicing succeeded, False otherwise
        """
        try:
            # Upload file
            with open(input_file_path, "rb") as f:
                files = {"file": (Path(input_file_path).name, f, "application/octet-stream")}
                data = {}

                if filament_config:
                    data["filament_config"] = filament_config
                if printer_config:
                    data["printer_config"] = printer_config
                if process_config:
                    data["process_config"] = process_config

                response = await self.client.post(
                    f"{self.api_url}/slice",
                    files=files,
                    data=data,
                )

            if response.status_code != 200:
                logger.error("External API slice failed: %s", response.text)
                return False

            # Save the output
            with open(output_file_path, "wb") as f:
                f.write(response.content)

            return True

        except Exception as e:
            logger.error("External API slice error: %s", e)
            return False

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class OrcaSlicerService:
    """Service for managing OrcaSlicer slicing operations.

    Supports both local CLI and external API modes.
    """

    def __init__(
        self,
        orcaslicer_path: str | None = None,
        use_external_api: bool = False,
        api_url: str | None = None,
    ):
        """Initialize the OrcaSlicer service.

        Args:
            orcaslicer_path: Path to OrcaSlicer executable. If None, will search in PATH.
            use_external_api: Whether to use external API instead of local CLI
            api_url: URL of external OrcaSlicer API
        """
        self.use_external_api = use_external_api
        self.api_url = api_url
        self.external_api: OrcaSlicerExternalAPI | None = None

        if use_external_api and api_url:
            self.external_api = OrcaSlicerExternalAPI(api_url)
            self.orcaslicer_path = None
            logger.info("Initialized OrcaSlicer service with external API: %s", api_url)
        else:
            self.orcaslicer_path = self._sanitize_path(orcaslicer_path) or self._find_orcaslicer()
            logger.info("Initialized OrcaSlicer service with local CLI: %s", self.orcaslicer_path)

        self.active_jobs: dict[str, asyncio.Task] = {}

    def update_config(
        self,
        orcaslicer_path: str | None = None,
        use_external_api: bool = False,
        api_url: str | None = None,
    ) -> None:
        """Update the OrcaSlicer configuration.

        Args:
            orcaslicer_path: New path to OrcaSlicer executable
            use_external_api: Whether to use external API
            api_url: URL of external OrcaSlicer API
        """
        self.use_external_api = use_external_api
        self.api_url = api_url

        if use_external_api and api_url:
            # Switch to external API mode
            if self.external_api:
                # Close old client if exists
                asyncio.create_task(self.external_api.close())
            self.external_api = OrcaSlicerExternalAPI(api_url)
            self.orcaslicer_path = None
            logger.info("Switched to external API mode: %s", api_url)
        else:
            # Switch to local CLI mode
            if self.external_api:
                asyncio.create_task(self.external_api.close())
                self.external_api = None
            sanitized_path = self._sanitize_path(orcaslicer_path)
            if sanitized_path:
                self.orcaslicer_path = sanitized_path
                logger.info("Updated OrcaSlicer path to: %s", sanitized_path)
            else:
                self.orcaslicer_path = self._find_orcaslicer()
                logger.info("Auto-detected OrcaSlicer path: %s", self.orcaslicer_path)

    def _sanitize_path(self, path: str | None) -> str | None:
        """Sanitize the OrcaSlicer path by removing whitespace.

        Args:
            path: Path to sanitize

        Returns:
            Sanitized path or None if empty
        """
        if not path:
            return None
        # Strip whitespace from both ends
        sanitized = path.strip()
        return sanitized if sanitized else None

    def _find_orcaslicer(self) -> str | None:
        """Find OrcaSlicer executable in system PATH."""
        # Try common executable names
        for name in ["orca-slicer", "orcaslicer", "OrcaSlicer"]:
            path = shutil.which(name)
            if path:
                logger.info("Found OrcaSlicer at: %s", path)
                return path

        # Try common installation paths
        common_paths = [
            "/usr/bin/orca-slicer",
            "/usr/local/bin/orca-slicer",
            "/opt/OrcaSlicer/orca-slicer",
            "C:\\Program Files\\OrcaSlicer\\orca-slicer.exe",
            "C:\\Program Files (x86)\\OrcaSlicer\\orca-slicer.exe",
        ]

        for path in common_paths:
            if os.path.isfile(path):
                logger.info("Found OrcaSlicer at: %s", path)
                return path

        logger.warning("OrcaSlicer executable not found in PATH or common locations")
        return None

    def is_available(self) -> bool:
        """Check if OrcaSlicer is available.

        For local mode, checks if executable exists.
        For external API mode, this is a synchronous check - use async health_check for proper check.
        """
        if self.use_external_api and self.external_api:
            # For external API, we assume it's available
            # Actual check should be done with async health_check
            return self.api_url is not None
        if not self.orcaslicer_path:
            return False
        return os.path.isfile(self.orcaslicer_path)

    async def health_check(self) -> bool:
        """Async health check for OrcaSlicer availability.

        Returns:
            True if OrcaSlicer is available and healthy
        """
        if self.use_external_api and self.external_api:
            return await self.external_api.health_check()
        return self.is_available()

    async def create_slice_job(
        self,
        db: AsyncSession,
        input_file_path: str,
        filament_preset_id: int | None = None,
        printer_preset_id: int | None = None,
        process_preset_id: int | None = None,
        auto_push_to_archive: bool = True,
        user_id: int | None = None,
    ) -> SlicingJob:
        """Create a new slicing job in the database.

        Args:
            db: Database session
            input_file_path: Path to input STL/3MF file
            filament_preset_id: ID of filament preset to use
            printer_preset_id: ID of printer preset to use
            process_preset_id: ID of process preset to use
            auto_push_to_archive: Whether to automatically push result to archive
            user_id: ID of user creating the job

        Returns:
            Created SlicingJob instance
        """
        job_id = str(uuid.uuid4())
        input_filename = Path(input_file_path).name

        job = SlicingJob(
            job_id=job_id,
            user_id=user_id,
            input_filename=input_filename,
            input_file_path=input_file_path,
            filament_preset_id=filament_preset_id,
            printer_preset_id=printer_preset_id,
            process_preset_id=process_preset_id,
            auto_push_to_archive=auto_push_to_archive,
            status="queued",
            progress=0,
        )

        db.add(job)
        await db.flush()
        await db.refresh(job)

        return job

    async def start_slicing(self, job: SlicingJob, db: AsyncSession) -> None:
        """Start slicing a job asynchronously.

        Args:
            job: SlicingJob instance
            db: Database session
        """
        # Update job status
        job.status = "processing"
        job.started_at = datetime.now(timezone.utc)
        job.progress = 10
        await db.commit()

        # Start async slicing task
        task = asyncio.create_task(self._slice_file_async(job, db))
        self.active_jobs[job.job_id] = task

    async def _slice_file_async(self, job: SlicingJob, db: AsyncSession) -> None:
        """Asynchronously slice a file using OrcaSlicer CLI.

        Args:
            job: SlicingJob instance
            db: Database session
        """
        try:
            if not self.is_available():
                raise RuntimeError("OrcaSlicer is not available")

            # Create temporary output directory
            with tempfile.TemporaryDirectory() as temp_dir:
                output_path = Path(temp_dir) / f"{Path(job.input_filename).stem}.gcode"

                # Build OrcaSlicer command
                cmd = [
                    self.orcaslicer_path,
                    "--slice",
                    job.input_file_path,
                    "--output",
                    str(output_path),
                ]

                # Add preset configurations if provided
                # Note: This is a simplified implementation
                # In production, you'd load preset JSON files and pass them to OrcaSlicer

                job.progress = 30
                await db.commit()

                # Execute OrcaSlicer
                logger.info("Starting OrcaSlicer: %s", " ".join(cmd))
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                job.progress = 50
                await db.commit()

                # Wait for completion
                stdout, stderr = await process.communicate()

                if process.returncode != 0:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    logger.error("OrcaSlicer failed: %s", error_msg)
                    raise RuntimeError(f"Slicing failed: {error_msg}")

                job.progress = 90
                await db.commit()

                # Check if output file was created
                if not output_path.exists():
                    raise RuntimeError("Output file was not created")

                # Store output file path (in production, copy to permanent location)
                job.output_filename = output_path.name
                job.output_file_path = str(output_path)

                # Mark as completed
                job.status = "completed"
                job.progress = 100
                job.completed_at = datetime.now(timezone.utc)

                logger.info("Slicing job %s completed successfully", job.job_id)

        except Exception as e:
            logger.exception("Slicing job %s failed", job.job_id)
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.now(timezone.utc)

        finally:
            await db.commit()
            # Remove from active jobs
            self.active_jobs.pop(job.job_id, None)

    async def get_job_status(self, job_id: str, db: AsyncSession) -> SlicingJob | None:
        """Get the status of a slicing job.

        Args:
            job_id: Job ID
            db: Database session

        Returns:
            SlicingJob instance or None if not found
        """
        result = await db.execute(select(SlicingJob).where(SlicingJob.job_id == job_id))
        return result.scalar_one_or_none()

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a running slicing job.

        Args:
            job_id: Job ID

        Returns:
            True if job was cancelled, False if not found or not running
        """
        task = self.active_jobs.get(job_id)
        if task and not task.done():
            task.cancel()
            self.active_jobs.pop(job_id, None)
            return True
        return False


# Global service instance
_orcaslicer_service: OrcaSlicerService | None = None


def get_orcaslicer_service(
    orcaslicer_path: str | None = None,
    use_external_api: bool = False,
    api_url: str | None = None,
) -> OrcaSlicerService:
    """Get or create the global OrcaSlicer service instance.

    If configuration has changed, updates the existing service instance.

    Args:
        orcaslicer_path: Path to OrcaSlicer executable
        use_external_api: Whether to use external API mode
        api_url: URL of external OrcaSlicer API

    Returns:
        OrcaSlicerService instance
    """
    global _orcaslicer_service
    if _orcaslicer_service is None:
        _orcaslicer_service = OrcaSlicerService(
            orcaslicer_path=orcaslicer_path,
            use_external_api=use_external_api,
            api_url=api_url,
        )
    else:
        # Update configuration if any parameters provided
        if orcaslicer_path is not None or use_external_api or api_url is not None:
            _orcaslicer_service.update_config(
                orcaslicer_path=orcaslicer_path,
                use_external_api=use_external_api,
                api_url=api_url,
            )
    return _orcaslicer_service


def reset_orcaslicer_service() -> None:
    """Reset the global OrcaSlicer service instance.

    Used when settings are updated to force re-initialization.
    """
    global _orcaslicer_service
    _orcaslicer_service = None
