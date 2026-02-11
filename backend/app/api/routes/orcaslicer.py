"""API routes for OrcaSlicer integration."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled, get_current_user_optional
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.archive import PrintArchive
from backend.app.models.library import LibraryFile
from backend.app.models.local_preset import LocalPreset
from backend.app.models.settings import Settings
from backend.app.models.slicing_job import SlicingJob
from backend.app.models.user import User
from backend.app.schemas.slicing import (
    OrcaSlicerStatus,
    SliceJobList,
    SliceJobResponse,
    SliceJobStatus,
    SliceRequest,
)
from backend.app.services.orcaslicer_service import get_orcaslicer_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orcaslicer", tags=["OrcaSlicer"])


async def get_orcaslicer_settings(db: AsyncSession) -> dict:
    """Get OrcaSlicer settings from database.

    Returns:
        Dict with keys: enabled, orcaslicer_path, auto_push_to_archive, use_external_api, api_url
    """
    settings = {
        "enabled": False,
        "orcaslicer_path": "",
        "auto_push_to_archive": True,
        "use_external_api": False,
        "api_url": "",
    }

    result = await db.execute(select(Settings))
    for setting in result.scalars().all():
        if setting.key == "orcaslicer_enabled":
            settings["enabled"] = setting.value.lower() == "true"
        elif setting.key == "orcaslicer_path":
            settings["orcaslicer_path"] = setting.value
        elif setting.key == "orcaslicer_auto_push_to_archive":
            settings["auto_push_to_archive"] = setting.value.lower() == "true"
        elif setting.key == "orcaslicer_use_external_api":
            settings["use_external_api"] = setting.value.lower() == "true"
        elif setting.key == "orcaslicer_api_url":
            settings["api_url"] = setting.value

    return settings


@router.get("/status", response_model=OrcaSlicerStatus)
async def get_orcaslicer_status(
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SLICER_PROFILES_READ),
):
    """Get OrcaSlicer integration status."""
    settings = await get_orcaslicer_settings(db)
    enabled = settings["enabled"]
    orcaslicer_path = settings["orcaslicer_path"]
    use_external_api = settings["use_external_api"]
    api_url = settings["api_url"]

    service = get_orcaslicer_service(
        orcaslicer_path=orcaslicer_path if orcaslicer_path else None,
        use_external_api=use_external_api,
        api_url=api_url if api_url else None,
    )

    # Use async health check for accurate availability
    try:
        available = await service.health_check()
    except Exception:
        available = False

    message = None
    if enabled and not available:
        if use_external_api:
            message = "OrcaSlicer external API is not reachable"
        else:
            message = "OrcaSlicer executable not found"
    elif not enabled:
        message = "OrcaSlicer integration is disabled"
    elif available:
        if use_external_api:
            message = f"OrcaSlicer external API is ready ({api_url})"
        else:
            message = "OrcaSlicer is ready"

    return OrcaSlicerStatus(
        enabled=enabled,
        available=available,
        message=message,
        orcaslicer_path=service.orcaslicer_path,
    )


@router.post("/slice", response_model=SliceJobResponse)
async def slice_file(
    request: SliceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SLICER_USE),
):
    """Submit a slicing job for a file from library or archive."""
    # Check if OrcaSlicer is enabled
    settings = await get_orcaslicer_settings(db)
    if not settings["enabled"]:
        raise HTTPException(status_code=400, detail="OrcaSlicer integration is not enabled")

    # Get the service with full configuration
    service = get_orcaslicer_service(
        orcaslicer_path=settings.get("orcaslicer_path"),
        use_external_api=settings.get("use_external_api", False),
        api_url=settings.get("api_url"),
    )

    # Check availability
    try:
        available = await service.health_check()
    except Exception:
        available = False

    if not available:
        raise HTTPException(status_code=503, detail="OrcaSlicer is not available")

    # Determine input file path
    input_file_path = None
    if request.file_id:
        # Get file from library
        result = await db.execute(select(LibraryFile).where(LibraryFile.id == request.file_id))
        file = result.scalar_one_or_none()
        if not file:
            raise HTTPException(status_code=404, detail="Library file not found")
        input_file_path = file.path
    elif request.archive_id:
        # Get file from archive
        result = await db.execute(select(PrintArchive).where(PrintArchive.id == request.archive_id))
        archive = result.scalar_one_or_none()
        if not archive:
            raise HTTPException(status_code=404, detail="Archive not found")
        # Note: In production, you'd need to get the actual file path from archive
        # This is a simplified implementation
        input_file_path = f"/tmp/archive_{archive.id}.3mf"  # Placeholder
    else:
        raise HTTPException(status_code=400, detail="Either file_id or archive_id must be provided")

    # Validate presets if provided
    if request.filament_preset_id:
        result = await db.execute(select(LocalPreset).where(LocalPreset.id == request.filament_preset_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Filament preset not found")

    if request.printer_preset_id:
        result = await db.execute(select(LocalPreset).where(LocalPreset.id == request.printer_preset_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Printer preset not found")

    if request.process_preset_id:
        result = await db.execute(select(LocalPreset).where(LocalPreset.id == request.process_preset_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Process preset not found")

    # Create slicing job
    user_id = current_user.id if current_user else None
    job = await service.create_slice_job(
        db=db,
        input_file_path=input_file_path,
        filament_preset_id=request.filament_preset_id,
        printer_preset_id=request.printer_preset_id,
        process_preset_id=request.process_preset_id,
        auto_push_to_archive=request.auto_push_to_archive,
        user_id=user_id,
    )

    await db.commit()

    # Start slicing asynchronously
    await service.start_slicing(job, db)

    return SliceJobResponse(
        success=True,
        job_id=job.job_id,
        message=f"Slicing job {job.job_id} created and started",
    )


@router.get("/jobs/{job_id}", response_model=SliceJobStatus)
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SLICER_USE),
):
    """Get the status of a slicing job."""
    service = get_orcaslicer_service()
    job = await service.get_job_status(job_id, db)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return SliceJobStatus(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        error_message=job.error_message,
        input_filename=job.input_filename,
        output_filename=job.output_filename,
        archive_id=job.archive_id,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.get("/jobs", response_model=SliceJobList)
async def list_jobs(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SLICER_USE),
):
    """List slicing jobs for the current user."""
    query = select(SlicingJob).order_by(SlicingJob.created_at.desc()).limit(limit)

    # If auth is enabled and user is not admin, filter by user
    if current_user:
        query = query.where(SlicingJob.user_id == current_user.id)

    result = await db.execute(query)
    jobs = result.scalars().all()

    job_statuses = [
        SliceJobStatus(
            job_id=job.job_id,
            status=job.status,
            progress=job.progress,
            error_message=job.error_message,
            input_filename=job.input_filename,
            output_filename=job.output_filename,
            archive_id=job.archive_id,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
        for job in jobs
    ]

    return SliceJobList(jobs=job_statuses, total=len(job_statuses))


@router.delete("/jobs/{job_id}")
async def cancel_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SLICER_USE),
):
    """Cancel a running slicing job."""
    service = get_orcaslicer_service()

    # Check if job exists
    job = await service.get_job_status(job_id, db)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Try to cancel
    cancelled = await service.cancel_job(job_id)

    if cancelled:
        # Update job status in database
        job.status = "cancelled"
        await db.commit()
        return {"success": True, "message": "Job cancelled"}
    else:
        return {"success": False, "message": "Job is not running or already completed"}


@router.get("/profiles")
async def list_profiles(
    db: AsyncSession = Depends(get_db),
    _: User | None = RequirePermissionIfAuthEnabled(Permission.SLICER_PROFILES_READ),
):
    """List available slicer profiles grouped by type."""
    result = await db.execute(select(LocalPreset).order_by(LocalPreset.name))
    presets = result.scalars().all()

    grouped = {
        "filament": [],
        "printer": [],
        "process": [],
    }

    for preset in presets:
        profile_data = {
            "id": preset.id,
            "name": preset.name,
            "filament_type": preset.filament_type,
            "filament_vendor": preset.filament_vendor,
            "source": preset.source,
        }

        if preset.preset_type in grouped:
            grouped[preset.preset_type].append(profile_data)

    return grouped
