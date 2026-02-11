"""Service for integrating with OrcaSlicer CLI for slicing 3D models.

This service provides a Python wrapper around OrcaSlicer's command-line interface,
allowing BambuDddy to slice STL/3MF files using configured slicer presets.
"""

import asyncio
import logging
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.slicing_job import SlicingJob

logger = logging.getLogger(__name__)


class OrcaSlicerService:
    """Service for managing OrcaSlicer slicing operations."""

    def __init__(self, orcaslicer_path: str | None = None):
        """Initialize the OrcaSlicer service.

        Args:
            orcaslicer_path: Path to OrcaSlicer executable. If None, will search in PATH.
        """
        self.orcaslicer_path = orcaslicer_path or self._find_orcaslicer()
        self.active_jobs: dict[str, asyncio.Task] = {}

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
        """Check if OrcaSlicer is available."""
        if not self.orcaslicer_path:
            return False
        return os.path.isfile(self.orcaslicer_path)

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


def get_orcaslicer_service(orcaslicer_path: str | None = None) -> OrcaSlicerService:
    """Get or create the global OrcaSlicer service instance.

    Args:
        orcaslicer_path: Path to OrcaSlicer executable

    Returns:
        OrcaSlicerService instance
    """
    global _orcaslicer_service
    if _orcaslicer_service is None:
        _orcaslicer_service = OrcaSlicerService(orcaslicer_path)
    return _orcaslicer_service
